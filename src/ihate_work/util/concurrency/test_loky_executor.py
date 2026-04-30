"""Tests for LokyExecutor."""

from __future__ import annotations

import os
import threading
import time

from ihate_work.util.concurrency.loky_executor import LokyExecutor

# -- Helpers (module-level for picklability) --------------------------------

def _worker_pid(_: object = None) -> int:
    return os.getpid()


def _slow_pid(seconds: float) -> int:
    time.sleep(seconds)
    return os.getpid()


_INIT_MARKER_ATTR = "__loky_executor_test_init_marker__"


def _set_marker():
    """Initializer that sets a module-level marker in the worker."""
    import ihate_work.util.concurrency.test_loky_executor as mod

    setattr(mod, _INIT_MARKER_ATTR, os.getpid())


def _get_marker() -> int | None:
    import ihate_work.util.concurrency.test_loky_executor as mod

    return getattr(mod, _INIT_MARKER_ATTR, None)


# -- Tests ------------------------------------------------------------------


class TestLokyExecutor:

    def test_basic_submit_and_result(self):
        with LokyExecutor(2, retire_after_tasks=100, prefork=False) as pool:
            future = pool.submit(pow, 2, 10)
            assert future.result(timeout=10) == 1024

    def test_context_manager_cleanup(self):
        """After __exit__, executor is shut down."""
        pool = LokyExecutor(1, retire_after_tasks=100, prefork=False)
        with pool:
            pool.submit(pow, 2, 3).result(timeout=10)
        # The shutdown flag should be set.
        assert pool._flags.shutdown

    def test_prefork_workers_ready(self):
        """After __enter__ with prefork=True, submitting to N workers
        yields N distinct PIDs immediately (no init delay)."""
        n = 2
        with LokyExecutor(n, retire_after_tasks=100, prefork=True) as pool:
            start = time.monotonic()
            futs = [pool.submit(_worker_pid) for _ in range(n)]
            pids = {f.result(timeout=10) for f in futs}
            elapsed = time.monotonic() - start
            assert len(pids) == n
            # Should be fast since workers are already warm.
            assert elapsed < 5.0, f"took {elapsed:.1f}s, expected < 5s"

    def test_per_worker_retirement(self):
        """With retire_after_tasks=3, workers rotate but tasks still complete."""
        retire = 3
        n_tasks = 12
        pids = set()
        with LokyExecutor(2, retire_after_tasks=retire, prefork=True) as pool:
            for _ in range(n_tasks):
                f = pool.submit(_worker_pid)
                pids.add(f.result(timeout=10))
        # We should see more than 2 PIDs (workers were replaced).
        assert len(pids) > 2, f"expected >2 PIDs, got {pids}"

    def test_no_downtime_during_retirement(self):
        """A burst of tasks across retirement boundaries all complete."""
        retire = 3
        n_tasks = 20
        with LokyExecutor(2, retire_after_tasks=retire, prefork=True) as pool:
            futs = [pool.submit(pow, 2, i) for i in range(n_tasks)]
            results = [f.result(timeout=30) for f in futs]
        assert results == [2**i for i in range(n_tasks)]

    def test_initializer_runs_on_replacement(self):
        """Initializer is called for replacement workers too."""
        retire = 2
        with LokyExecutor(
            1,
            initializer=_set_marker,
            retire_after_tasks=retire,
            prefork=True,
        ) as pool:
            # First worker gets the initializer via prefork warm-up.
            pid1 = pool.submit(_get_marker).result(timeout=10)
            assert pid1 is not None

            # Force retirement.
            pool.submit(_worker_pid).result(timeout=10)

            # Third task goes to a replacement worker; it should also
            # have the marker set by the initializer.
            pid2 = pool.submit(_get_marker).result(timeout=10)
            assert pid2 is not None

    def test_cross_thread_submit(self):
        """submit() from another thread works."""
        result = None

        def submit_from_thread(p):
            nonlocal result
            result = p.submit(pow, 2, 10).result(timeout=10)

        with LokyExecutor(1, retire_after_tasks=100, prefork=False) as pool:
            t = threading.Thread(target=submit_from_thread, args=(pool,))
            t.start()
            t.join()

        assert result == 1024

    def test_submit_outside_context_raises(self):
        """submit() without __enter__ still works (loky API), but
        using it as a context manager is preferred."""
        # loky's ProcessPoolExecutor doesn't require __enter__ to submit.
        # LokyExecutor follows the same contract.
        pool = LokyExecutor(1, retire_after_tasks=100, prefork=False)
        f = pool.submit(pow, 2, 3)
        assert f.result(timeout=10) == 8
        pool.shutdown(wait=True)

    def test_recycle_if_needed_is_noop(self):
        """recycle_if_needed() exists and does nothing."""
        with LokyExecutor(1, retire_after_tasks=100, prefork=False) as pool:
            pool.recycle_if_needed()  # should not raise
            assert pool.submit(pow, 2, 3).result(timeout=10) == 8

    def test_no_retirement_without_config(self):
        """Without retire_after_tasks, workers persist."""
        n_tasks = 10
        pids = set()
        with LokyExecutor(1, prefork=False) as pool:
            for _ in range(n_tasks):
                f = pool.submit(_worker_pid)
                pids.add(f.result(timeout=10))
        # Single worker, no retirement — only 1 PID.
        assert len(pids) == 1

    def test_exit_waits_for_workers(self):
        """__exit__ blocks until in-flight tasks finish."""
        with LokyExecutor(1, retire_after_tasks=100, prefork=False) as pool:
            future = pool.submit(_slow_pid, 0.5)
        # After __exit__, the task must be done.
        assert future.done()
        assert isinstance(future.result(), int)

    def test_many_tasks_with_retirement(self):
        """Stress test: many tasks with aggressive retirement."""
        retire = 5
        n_tasks = 50
        with LokyExecutor(3, retire_after_tasks=retire, prefork=True) as pool:
            futs = [pool.submit(pow, 2, i % 20) for i in range(n_tasks)]
            results = [f.result(timeout=60) for f in futs]
        assert len(results) == n_tasks
        assert results == [2 ** (i % 20) for i in range(n_tasks)]
