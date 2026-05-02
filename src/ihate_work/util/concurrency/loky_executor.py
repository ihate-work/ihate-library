"""LokyExecutor — loky ProcessPoolExecutor with prefork and task-count retirement.

Extends :class:`loky.ProcessPoolExecutor` with two features:

1. **Prefork warm-up** — ``__enter__`` blocks until every worker has run its
   initializer and completed a dummy task, so the pool is fully warm before
   the caller submits real work.

2. **Per-worker task countdown** — each worker self-terminates after
   *retire_after_tasks* completions.  The manager thread detects the clean
   exit and spawns a replacement (using the same protocol loky already uses
   for memory-leak retirement).

loky's built-in RSS-based retirement (``_MAX_MEMORY_LEAK_SIZE``, requires
*psutil*) continues to work unchanged.

Backward-compat shim: ``recycle_if_needed()`` is a no-op so callers that
previously used :class:`RecyclingPool2` can switch with minimal edits.
"""

from __future__ import annotations

import gc
import multiprocessing as mp
import os
import queue
import sys
import traceback
import warnings
from collections.abc import Callable
from concurrent.futures._base import LOGGER
from time import time

from loky import ProcessPoolExecutor
from loky.process_executor import (
    _CURRENT_DEPTH,
    _MAX_MEMORY_LEAK_SIZE,
    _MEMORY_LEAK_CHECK_DELAY,
    _USE_PSUTIL,
    _enable_faulthandler_if_needed,
    _ExceptionWithTraceback,
    _python_exit,
    _RemoteTraceback,
    _ResultItem,
    _sendback_result,
)

from ihate_work.o11y import get_o11y

logger, *_ = get_o11y(__name__)

if _USE_PSUTIL:
    from loky.process_executor import _get_memory_usage


# ---------------------------------------------------------------------------
# Worker function — copy of loky's _process_worker with task-count retirement
# ---------------------------------------------------------------------------
# This MUST be module-level (picklable).  We copy _process_worker rather than
# wrapping it because the task loop has no hook points.


def _process_worker_countdown(
    call_queue,
    result_queue,
    initializer,
    initargs,
    processes_management_lock,
    timeout,
    worker_exit_lock,
    current_depth,
    max_tasks,  # ← added parameter
):
    """loky _process_worker with per-worker task-count retirement."""
    if initializer is not None:
        try:
            initializer(*initargs)
        except BaseException:
            LOGGER.critical("Exception in initializer:", exc_info=True)
            return

    global _CURRENT_DEPTH
    _CURRENT_DEPTH = current_depth
    _process_reference_size = None
    _last_memory_leak_check = None
    pid = os.getpid()
    tasks_completed = 0

    mp.util.debug(f"Worker started with timeout={timeout}, max_tasks={max_tasks}")
    _enable_faulthandler_if_needed()

    while True:
        try:
            call_item = call_queue.get(block=True, timeout=timeout)
            if call_item is None:
                mp.util.info("Shutting down worker on sentinel")
        except queue.Empty:
            mp.util.info(f"Shutting down worker after timeout {timeout:0.3f}s")
            if processes_management_lock.acquire(block=False):
                processes_management_lock.release()
                call_item = None
            else:
                mp.util.info("Could not acquire processes_management_lock")
                continue
        except BaseException:
            previous_tb = traceback.format_exc()
            try:
                result_queue.put(_RemoteTraceback(previous_tb))
            except BaseException:
                print(previous_tb)
            mp.util.debug("Exiting with code 1")
            sys.exit(1)

        if call_item is None:
            result_queue.put(pid)
            is_clean = worker_exit_lock.acquire(True, timeout=30)
            _python_exit()
            if is_clean:
                mp.util.debug("Exited cleanly")
            else:
                mp.util.info("Main process did not release worker_exit")
            return

        try:
            r = call_item()
        except BaseException as e:
            exc = _ExceptionWithTraceback(e)
            result_queue.put(_ResultItem(call_item.work_id, exception=exc))
        else:
            _sendback_result(result_queue, call_item.work_id, result=r)
            del r

        del call_item
        tasks_completed += 1

        # ── Task-count retirement ──
        if max_tasks is not None and tasks_completed >= max_tasks:
            mp.util.info(f"Worker {pid}: reached max_tasks={max_tasks}, retiring")
            result_queue.put(pid)
            with worker_exit_lock:
                mp.util.debug("Exit due to task-count retirement")
                return

        # ── RSS-based retirement (unchanged from loky) ──
        if _USE_PSUTIL:
            if _process_reference_size is None:
                _process_reference_size = _get_memory_usage(pid, force_gc=True)
                _last_memory_leak_check = time()
                continue
            if time() - _last_memory_leak_check > _MEMORY_LEAK_CHECK_DELAY:
                mem_usage = _get_memory_usage(pid)
                _last_memory_leak_check = time()
                if mem_usage - _process_reference_size < _MAX_MEMORY_LEAK_SIZE:
                    continue
                mem_usage = _get_memory_usage(pid, force_gc=True)
                _last_memory_leak_check = time()
                if mem_usage - _process_reference_size < _MAX_MEMORY_LEAK_SIZE:
                    continue
                mp.util.info("Memory leak detected: shutting down worker")
                result_queue.put(pid)
                with worker_exit_lock:
                    mp.util.debug("Exit due to memory leak")
                    return
        else:
            if _last_memory_leak_check is None or (time() - _last_memory_leak_check > _MEMORY_LEAK_CHECK_DELAY):
                gc.collect()
                _last_memory_leak_check = time()


# ---------------------------------------------------------------------------
# Worker o11y bootstrap (must be module-level for pickling)
# ---------------------------------------------------------------------------


def _init_worker_with_o11y(user_initializer, user_initargs):
    """Wraps the user initializer to set up o11y first.

    loky uses spawn, so workers start with a bare interpreter — no structlog
    config, no OTEL providers.  This wrapper restores console + OTEL logging
    before the user's initializer runs.
    """
    import ihate_work.o11y as o11y

    o11y.setup_otel()
    o11y.setup_structlog(enable_file_log=False)

    if user_initializer is not None:
        user_initializer(*user_initargs)


# ---------------------------------------------------------------------------
# Warm-up sentinel
# ---------------------------------------------------------------------------


def _warmup_noop():
    """Dummy callable submitted during prefork warm-up."""
    return True


# ---------------------------------------------------------------------------
# LokyExecutor
# ---------------------------------------------------------------------------


class LokyExecutor(ProcessPoolExecutor):
    """loky ProcessPoolExecutor with prefork warm-up and task-count retirement.

    Usage::

        with LokyExecutor(4, initializer=my_init, retire_after_tasks=500) as pool:
            future = pool.submit(do_work, item)
            result = future.result()

    The context-manager ``__enter__`` blocks until all workers are warm
    (initializer has run).  Each worker self-terminates after
    *retire_after_tasks* completions and is transparently replaced.

    ``recycle_if_needed()`` is a no-op for backward compat.
    """

    def __init__(
        self,
        max_workers: int | None = None,
        initializer: Callable | None = None,
        *,
        initargs: tuple = (),
        retire_after_tasks: int | None = None,
        timeout: float | None = None,
        prefork: bool = True,
        context=None,
        env=None,
    ):
        self._retire_after_tasks = retire_after_tasks
        self._prefork = prefork

        # loky warns "A worker stopped while some jobs were given to the
        # executor" on every clean task-count retirement.  Expected and noisy.
        if retire_after_tasks is not None:
            warnings.filterwarnings(
                "ignore",
                message="A worker stopped while some jobs were given",
                module="loky.process_executor",
            )

        # Wrap the user's initializer so workers get o11y setup.
        # loky uses spawn — workers start with a bare interpreter.
        super().__init__(
            max_workers=max_workers,
            initializer=_init_worker_with_o11y,
            initargs=(initializer, initargs),
            timeout=timeout,
            context=context,
            env=env,
        )

    # -- Override worker spawning to use countdown worker ----------------

    def _adjust_process_count(self):
        if self._retire_after_tasks is None:
            # No countdown needed — use stock loky worker.
            return super()._adjust_process_count()

        while len(self._processes) < self._max_workers:
            worker_exit_lock = self._context.BoundedSemaphore(1)
            args = (
                self._call_queue,
                self._result_queue,
                self._initializer,
                self._initargs,
                self._processes_management_lock,
                self._timeout,
                worker_exit_lock,
                _CURRENT_DEPTH + 1,
                self._retire_after_tasks,
            )
            worker_exit_lock.acquire()
            try:
                p = self._context.Process(
                    target=_process_worker_countdown,
                    args=args,
                    env=self._env,
                )
            except TypeError:
                p = self._context.Process(
                    target=_process_worker_countdown,
                    args=args,
                )
            p._worker_exit_lock = worker_exit_lock
            p.start()
            self._processes[p.pid] = p

        mp.util.debug(
            f"Adjusted process count to {self._max_workers}: {[(p.name, pid) for pid, p in self._processes.items()]}"
        )

    # -- Prefork warm-up ------------------------------------------------

    def __enter__(self):
        self._ensure_executor_running()
        if self._prefork:
            logger.info(
                "warming up workers",
                max_workers=self._max_workers,
            )
            futs = [super(LokyExecutor, self).submit(_warmup_noop) for _ in range(self._max_workers)]
            for f in futs:
                f.result(timeout=120)
            logger.info("all workers warm")
        return self

    # -- Backward-compat shim -------------------------------------------

    def recycle_if_needed(self):
        """No-op.  Per-worker retirement is automatic."""

    # -- Suppress loky's UserWarning on clean task-count retirement ------

    def _ensure_executor_running(self):
        """Ensure all workers and management thread are running.

        Same as super(), but wrapped so subclass __enter__ can call it
        before submit.
        """
        super()._ensure_executor_running()
