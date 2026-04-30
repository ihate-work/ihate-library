from __future__ import annotations

import datetime as dt


class Rater:
    # (count, timestamp) pairs
    _pairs: list[tuple[int, dt.datetime]]

    def __init__(
        self,
        *,
        _pairs: list[tuple[int, dt.datetime]] | None = None,
    ) -> None:
        if _pairs is not None:
            self._pairs = _pairs
        else:
            self._pairs = [(0, dt.datetime.now())]

    def tick(self, count: int) -> Rater:
        _prev_sum, _ = self._pairs[-1]
        now = dt.datetime.now()

        return Rater(
            _pairs=self._pairs + [(_prev_sum + count, now)],
        )

    @property
    def avg_rate(self) -> float:
        _total, _now = self._pairs[-1]
        _, _start = self._pairs[0]
        return float(_total) / (_now - _start).total_seconds()

    @property
    def total(self) -> int:
        return self._pairs[-1][0]

    @property
    def start(self) -> dt.datetime:
        return self._pairs[0][1]

    @property
    def elapsed(self) -> dt.timedelta:
        _total, _end = self._pairs[-1]
        _, _start = self._pairs[0]
        return _end - _start

    @property
    def rate(self) -> float:
        if len(self._pairs) < 2:
            return 0.0
        _total, _now = self._pairs[-1]
        _prev_total, _prev_now = self._pairs[-2]
        return float(_total - _prev_total) / (_now - _prev_now).total_seconds()
