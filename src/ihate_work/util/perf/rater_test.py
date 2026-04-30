import datetime as dt

from .rater import Rater


def test_initial_state():
    r = Rater()
    assert r.total == 0
    assert r.start is not None


def test_tick_accumulates():
    r = Rater()
    r = r.tick(10)
    assert r.total == 10
    r = r.tick(5)
    assert r.total == 15


def test_elapsed_increases():
    r = Rater()
    r = r.tick(1)
    assert r.elapsed >= dt.timedelta(0)


def test_rate_zero_when_single_pair():
    r = Rater()
    assert r.rate == 0.0


def test_rate_after_ticks():
    now = dt.datetime.now()
    r = Rater(
        _pairs=[
            (0, now),
            (100, now + dt.timedelta(seconds=1)),
            (200, now + dt.timedelta(seconds=2)),
        ]
    )
    # last segment: 100 items in 1 second
    assert r.rate == 100.0


def test_avg_rate():
    now = dt.datetime.now()
    r = Rater(
        _pairs=[
            (0, now),
            (50, now + dt.timedelta(seconds=1)),
            (100, now + dt.timedelta(seconds=2)),
        ]
    )
    # 100 items over 2 seconds
    assert r.avg_rate == 50.0
