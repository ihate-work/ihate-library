"""ProcessPoolExecutor wrapper that periodically recycles workers."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor

from ihate_work.o11y import get_o11y

logger, *_ = get_o11y(__name__)


class RecyclingPool:
    """ProcessPoolExecutor that periodically kills and replaces workers.

    Useful for long-running workloads where workers leak memory (e.g. spaCy,
    sudachipy).  Avoids ``ProcessPoolExecutor.max_tasks_per_child`` which has
    hanging bugs on Python 3.11-3.12.

    The caller invokes :meth:`recycle_if_needed` with a *drain_fn* callback
    that flushes all pending futures; when the task threshold is reached the
    pool is shut down and a fresh one is created so the OS reclaims leaked
    memory.

    Must be used as a context manager.  All methods are thread-safe.

    Usage::

        with RecyclingPool(4, my_init, recycle_after=100) as pool:
            for work in work_items:
                pool.recycle_if_needed(drain_pending)
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
        self._pool: ProcessPoolExecutor | None = None
        self._lock = threading.Lock()

    def __enter__(self):
        with self._lock:
            if self._pool is not None:
                raise RuntimeError("RecyclingPool is already entered")
            self._pool = ProcessPoolExecutor(
                max_workers=self._max_workers,
                initializer=self._initializer,
            )
        return self

    def __exit__(self, *exc):
        with self._lock:
            if self._pool is not None:
                self._pool.shutdown(wait=True)
                self._pool = None

    def submit(self, *args, **kwargs):
        with self._lock:
            if self._pool is None:
                raise RuntimeError("RecyclingPool is not entered")
            self._tasks += 1
            return self._pool.submit(*args, **kwargs)

    def recycle_if_needed(self, drain_fn: Callable[[], None]):
        """Recycle workers if task threshold reached.

        *drain_fn* must flush all pending futures before the old pool can be
        shut down.
        """
        with self._lock:
            if self._tasks < self._recycle_after:
                return
            logger.info(
                "recycling worker pool to reclaim memory",
                tasks_completed=self._tasks,
            )
        # drain and restart outside the lock — drain_fn may block for a while
        # and callers must be able to collect futures concurrently.
        drain_fn()
        with self._lock:
            self._pool.shutdown(wait=True)
            self._pool = ProcessPoolExecutor(
                max_workers=self._max_workers,
                initializer=self._initializer,
            )
            self._tasks = 0
