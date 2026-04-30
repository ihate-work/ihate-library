import concurrent.futures as cf

from .workers import run_in_workers, wait_pending


def test_wait_pending_returns_when_below_target():
    f1 = cf.Future()
    f1.set_result(42)
    f2 = cf.Future()
    f2.set_result(43)

    all_futures = [f1, f2]
    pending = {f1, f2}
    result = wait_pending(all_futures, pending, 2)
    assert len(result) <= 2


def _double(x):
    return x * 2


def test_run_in_workers_collects_futures():
    def create_tasks(executor: cf.Executor):
        for i in range(5):
            yield executor.submit(_double, i)

    futures = run_in_workers(create_tasks, num_worker=2, task_queue_length=3)
    assert len(futures) == 5
    results = sorted(f.result() for f in futures)
    assert results == [0, 2, 4, 6, 8]


def _divide_by_zero():
    return 1 / 0


def test_run_in_workers_raises_on_exception():
    def create_tasks(executor: cf.Executor):
        yield executor.submit(_divide_by_zero)

    try:
        run_in_workers(create_tasks, num_worker=1, raise_on_exception=True)
        assert False, "should have raised"
    except ZeroDivisionError:
        pass
