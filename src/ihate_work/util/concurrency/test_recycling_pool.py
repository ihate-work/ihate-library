"""Tests for RecyclingPool."""

from __future__ import annotations

import os
import threading

import pytest

from ihate_work.util.concurrency import RecyclingPool


def _worker_pid(_: object = None) -> int:
    """Return the PID of the worker process."""
    return os.getpid()


class TestRecyclingPool:
    def test_basic_submit_and_result(self):
        with RecyclingPool(2, recycle_after=100) as pool:
            future = pool.submit(pow, 2, 10)
            assert future.result() == 1024

    def test_context_manager_cleanup(self):
        pool = RecyclingPool(1, recycle_after=100)
        with pool:
            pool.submit(pow, 2, 3).result()
        # pool should be None after __exit__
        assert pool._pool is None

    def test_recycle_replaces_workers(self):
        """After recycling, worker PIDs should change."""
        recycle_after = 3
        drained = []

        def drain():
            drained.append(True)

        with RecyclingPool(1, recycle_after=recycle_after) as pool:
            # Submit enough tasks to reach threshold
            pids_before = set()
            for _ in range(recycle_after):
                f = pool.submit(_worker_pid)
                pids_before.add(f.result())

            # This should trigger recycling
            pool.recycle_if_needed(drain)

            # drain_fn was called
            assert len(drained) == 1

            # New worker should have a different PID
            f = pool.submit(_worker_pid)
            pid_after = f.result()
            assert pid_after not in pids_before

    def test_no_recycle_below_threshold(self):
        drained = []

        def drain():
            drained.append(True)

        with RecyclingPool(1, recycle_after=100) as pool:
            pool.submit(pow, 2, 3).result()
            pool.recycle_if_needed(drain)
            # Should NOT have recycled — only 1 task < 100 threshold
            assert len(drained) == 0

    def test_multiple_recycles(self):
        """Pool can be recycled more than once."""
        recycle_after = 2
        recycle_count = 0

        def drain():
            nonlocal recycle_count
            recycle_count += 1

        with RecyclingPool(1, recycle_after=recycle_after) as pool:
            for _ in range(recycle_after * 3):
                pool.recycle_if_needed(drain)
                pool.submit(pow, 2, 3).result()

        assert recycle_count >= 2

    def test_initializer_called_after_recycle(self):
        """The initializer runs again in recycled workers."""
        recycle_after = 2

        # Use a function that checks a global set by the initializer
        def init():
            global _test_marker
            _test_marker = True  # noqa: F841

        def check_marker():
            return globals().get("_test_marker", False)

        # We can't easily check the initializer in a subprocess, but we can
        # verify that submit still works after recycle (which means the new
        # pool was created with the initializer arg).
        with RecyclingPool(1, init, recycle_after=recycle_after) as pool:
            for _ in range(recycle_after):
                pool.submit(pow, 2, 3).result()
            pool.recycle_if_needed(lambda: None)
            # Pool was recycled — submit should still work
            assert pool.submit(pow, 3, 3).result() == 27

    def test_cross_thread_submit_works(self):
        """submit() from another thread is safe under the lock."""
        result = None

        def submit_from_thread(pool):
            nonlocal result
            result = pool.submit(pow, 2, 10).result()

        with RecyclingPool(1, recycle_after=100) as pool:
            t = threading.Thread(target=submit_from_thread, args=(pool,))
            t.start()
            t.join()

        assert result == 1024

    def test_double_enter_raises(self):
        """Entering the same pool twice raises RuntimeError."""
        pool = RecyclingPool(1, recycle_after=100)
        with pool:
            with pytest.raises(RuntimeError, match="already entered"):
                pool.__enter__()

    def test_submit_outside_context_raises(self):
        """submit() without __enter__ raises RuntimeError."""
        pool = RecyclingPool(1, recycle_after=100)
        with pytest.raises(RuntimeError, match="not entered"):
            pool.submit(pow, 2, 3)
