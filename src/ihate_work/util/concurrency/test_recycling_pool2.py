"""Tests for RecyclingPool2."""

from __future__ import annotations

import os
import threading
import time

import pytest

from ihate_work.util.concurrency.recycling_pool2 import RecyclingPool2


def _worker_pid(_: object = None) -> int:
    """Return the PID of the worker process."""
    return os.getpid()


def _slow_pid(seconds: float) -> int:
    """Sleep then return PID."""
    time.sleep(seconds)
    return os.getpid()


class TestRecyclingPool2:
    # ── Ported from RecyclingPool tests ──

    def test_basic_submit_and_result(self):
        with RecyclingPool2(2, recycle_after=100) as pool:
            future = pool.submit(pow, 2, 10)
            assert future.result() == 1024

    def test_context_manager_cleanup(self):
        pool = RecyclingPool2(1, recycle_after=100)
        with pool:
            pool.submit(pow, 2, 3).result()
        assert pool._pool is None

    def test_recycle_replaces_workers(self):
        """After recycling, worker PIDs should change."""
        recycle_after = 3
        with RecyclingPool2(1, recycle_after=recycle_after) as pool:
            pids_before = set()
            for _ in range(recycle_after):
                f = pool.submit(_worker_pid)
                pids_before.add(f.result())

            pool.recycle_if_needed()

            f = pool.submit(_worker_pid)
            pid_after = f.result()
            assert pid_after not in pids_before

    def test_no_recycle_below_threshold(self):
        with RecyclingPool2(1, recycle_after=100) as pool:
            pool.submit(pow, 2, 3).result()
            pool_before = pool._pool
            pool.recycle_if_needed()
            # Pool should not have been swapped.
            assert pool._pool is pool_before

    def test_multiple_recycles(self):
        """Pool can be recycled more than once."""
        recycle_after = 2
        pids_seen = set()
        with RecyclingPool2(1, recycle_after=recycle_after) as pool:
            for _ in range(3):
                for _ in range(recycle_after):
                    f = pool.submit(_worker_pid)
                    pids_seen.add(f.result())
                pool.recycle_if_needed()
        assert len(pids_seen) >= 2

    def test_initializer_called_after_recycle(self):
        """The initializer runs again in recycled workers."""
        recycle_after = 2

        def init():
            global _test_marker
            _test_marker = True  # noqa: F841

        with RecyclingPool2(1, init, recycle_after=recycle_after) as pool:
            for _ in range(recycle_after):
                pool.submit(pow, 2, 3).result()
            pool.recycle_if_needed()
            # Pool was recycled — submit should still work.
            assert pool.submit(pow, 3, 3).result() == 27

    def test_cross_thread_submit_works(self):
        """submit() from another thread is safe under the lock."""
        result = None

        def submit_from_thread(p):
            nonlocal result
            result = p.submit(pow, 2, 10).result()

        with RecyclingPool2(1, recycle_after=100) as pool:
            t = threading.Thread(target=submit_from_thread, args=(pool,))
            t.start()
            t.join()

        assert result == 1024

    def test_double_enter_raises(self):
        """Entering the same pool twice raises RuntimeError."""
        pool = RecyclingPool2(1, recycle_after=100)
        with pool:
            with pytest.raises(RuntimeError, match="already entered"):
                pool.__enter__()

    def test_submit_outside_context_raises(self):
        """submit() without __enter__ raises RuntimeError."""
        pool = RecyclingPool2(1, recycle_after=100)
        with pytest.raises(RuntimeError, match="not entered"):
            pool.submit(pow, 2, 3)

    # ── New tests: non-blocking recycle behaviour ──

    def test_recycle_does_not_block_new_submissions(self):
        """New submissions proceed immediately; they don't wait for the
        old pool's in-flight tasks to finish."""
        recycle_after = 1
        with RecyclingPool2(1, recycle_after=recycle_after) as pool:
            # Submit a slow task — this is the only task, hitting threshold.
            slow_future = pool.submit(time.sleep, 3)

            # Recycle: new pool is swapped in, old pool drains in background.
            pool.recycle_if_needed()

            # A fast task on the new pool should complete quickly.
            start = time.monotonic()
            fast_future = pool.submit(pow, 2, 10)
            result = fast_future.result(timeout=5)
            elapsed = time.monotonic() - start

            assert result == 1024
            assert elapsed < 2.0, (
                f"fast task took {elapsed:.1f}s — should not have waited "
                "for old pool's 3s sleep"
            )

            # Clean up the slow task.
            slow_future.result(timeout=10)

    def test_old_pool_futures_resolve_after_recycle(self):
        """Futures submitted before recycle still complete normally."""
        recycle_after = 2
        with RecyclingPool2(1, recycle_after=recycle_after) as pool:
            futures = []
            for i in range(recycle_after):
                futures.append(pool.submit(pow, 2, i))

            pool.recycle_if_needed()

            results = [f.result(timeout=5) for f in futures]
            assert results == [1, 2]

    def test_exit_waits_for_retiring_pools(self):
        """__exit__ blocks until all retiring pools finish draining."""
        recycle_after = 1
        with RecyclingPool2(1, recycle_after=recycle_after) as pool:
            future = pool.submit(_slow_pid, 0.5)
            pool.recycle_if_needed()
        # After __exit__, the slow task must have completed.
        assert future.done()
        assert isinstance(future.result(), int)

    def test_concurrent_submit_and_recycle(self):
        """submit() from one thread while another triggers recycle."""
        recycle_after = 4
        results = []
        errors = []

        def submitter(p, count):
            for _ in range(count):
                try:
                    f = p.submit(pow, 2, 3)
                    results.append(f.result(timeout=5))
                except Exception as exc:
                    errors.append(exc)

        with RecyclingPool2(2, recycle_after=recycle_after) as pool:
            t = threading.Thread(target=submitter, args=(pool, 10))
            t.start()
            # Meanwhile, trigger recycles from the main thread.
            for _ in range(20):
                pool.recycle_if_needed()
                time.sleep(0.01)
            t.join()

        assert not errors, f"errors during concurrent submit/recycle: {errors}"
        assert all(r == 8 for r in results)
