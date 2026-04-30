"""ProcessPoolExecutor wrapper that recycles workers without blocking."""

from __future__ import annotations

import functools
import os
import threading
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor

from ihate_work.o11y import get_o11y

logger, *_ = get_o11y(__name__)


# ── Worker lifecycle helpers (module-level for picklability) ──


def _worker_init_wrapper(user_init: Callable | None, gen: int):
    """Initializer that logs worker start, then delegates to user init."""
    pid = os.getpid()
    logger.info("worker process started", pid=pid, pool_gen=gen)
    if user_init is not None:
        user_init()


def _shutdown_pool(pool: ProcessPoolExecutor, gen: int):
    """Shut down *pool*, logging each worker PID on exit."""
    worker_pids = (
        list(pool._processes.keys())
        if hasattr(pool, "_processes") and pool._processes
        else []
    )
    pool.shutdown(wait=True)
    for pid in worker_pids:
        logger.info("worker process ended", pid=pid, pool_gen=gen)


class RecyclingPool2:
    """ProcessPoolExecutor that recycles workers without stopping submissions.

    Unlike :class:`RecyclingPool`, recycling is non-blocking: a fresh pool
    is swapped in immediately and the old pool drains in the background.
    No ``drain_fn`` is required — completed futures remain accessible to
    the caller and the old pool shuts down automatically once all its
    in-flight tasks finish.

    Must be used as a context manager.  All methods are thread-safe.

    Usage::

        with RecyclingPool2(4, my_init, recycle_after=100) as pool:
            for work in work_items:
                pool.recycle_if_needed()
                future = pool.submit(do_work, work)
    """

    def __init__(
        self,
        max_workers: int,
        initializer: Callable | None = None,
        *,
        recycle_after: int,
    ):
        self._max_workers = max_workers
        self._initializer = initializer
        self._recycle_after = recycle_after
        self._tasks = 0
        self._gen = 0
        self._pool: ProcessPoolExecutor | None = None
        self._lock = threading.Lock()
        self._cleanup_threads: list[threading.Thread] = []

    def _new_pool(self) -> ProcessPoolExecutor:
        self._gen += 1
        init = functools.partial(
            _worker_init_wrapper, self._initializer, self._gen,
        )
        return ProcessPoolExecutor(
            max_workers=self._max_workers, initializer=init,
        )

    def __enter__(self):
        with self._lock:
            if self._pool is not None:
                raise RuntimeError("RecyclingPool2 is already entered")
            self._pool = self._new_pool()
            self._tasks = 0
        return self

    def __exit__(self, *exc):
        with self._lock:
            pool = self._pool
            gen = self._gen
            self._pool = None
            threads = list(self._cleanup_threads)
            self._cleanup_threads.clear()
        # Wait for all retiring pools to finish draining.
        for t in threads:
            t.join()
        # Then shut down the active pool.
        if pool is not None:
            _shutdown_pool(pool, gen)

    def submit(self, *args, **kwargs):
        with self._lock:
            if self._pool is None:
                raise RuntimeError("RecyclingPool2 is not entered")
            self._tasks += 1
            return self._pool.submit(*args, **kwargs)

    def recycle_if_needed(self):
        """Recycle workers if the task threshold has been reached.

        A fresh pool is created immediately so new submissions are never
        blocked.  The old pool drains and shuts down in a background
        thread.
        """
        with self._lock:
            if self._tasks < self._recycle_after:
                return
            logger.info(
                "recycling worker pool (non-blocking)",
                tasks_completed=self._tasks,
                old_gen=self._gen,
            )
            old_pool = self._pool
            old_gen = self._gen
            self._pool = self._new_pool()
            self._tasks = 0
            # Prune finished cleanup threads.
            self._cleanup_threads = [
                t for t in self._cleanup_threads if t.is_alive()
            ]
            # Retire old pool in background — shutdown(wait=True) blocks
            # until all its in-flight futures complete, then frees OS
            # resources (worker processes).
            t = threading.Thread(
                target=_shutdown_pool,
                args=(old_pool, old_gen),
                daemon=True,
                name="pool-retire",
            )
            t.start()
            self._cleanup_threads.append(t)
