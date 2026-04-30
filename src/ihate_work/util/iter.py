from collections import defaultdict
from collections.abc import Callable, Generator, Hashable, Iterable, Iterator
from itertools import islice
from typing import (
    Any,
    Generic,
    TypeVar,
)

T = TypeVar("T")
T2 = TypeVar("T2")


# polyfill for itertools.batched
def batched(
    iterable: Iterable[T], batch_size: int, *, strict=False
) -> Generator[tuple[T, ...], None, None]:
    # batched('ABCDEFG', 3) → ABC DEF G
    if batch_size < 1:
        raise ValueError("n must be at least one")
    iterator = iter(iterable)
    while batch := tuple(islice(iterator, batch_size)):
        if strict and len(batch) != batch_size:
            raise ValueError("batched(): incomplete batch")
        yield batch


class IteratorChain(Generic[T], Iterator[T]):
    def __init__(self, maybe_iterator: Iterable[T] | Iterator[T]):
        if isinstance(maybe_iterator, Iterator):
            self._inner = maybe_iterator
        else:
            self._inner = iter(maybe_iterator)
            assert isinstance(self._inner, Iterator), (
                "input must be Iterable or Iterator"
            )
        self._moved = False

    def take(self, n: int) -> "IteratorChain[T]":
        def yielder():
            count = 0
            for v in self._inner:
                if count == n:
                    break
                yield v
                count += 1

        return self._replace(yielder())

    def uniq_by(self, keyer: Callable[[T], T2]) -> "IteratorChain[T]":
        seen = set()

        def yielder():
            for v in self._inner:
                key = keyer(v)
                if key in seen:
                    continue
                seen.add(key)
                yield v

        return self._replace(yielder())

    def skip(self, n: int) -> "IteratorChain[T]":
        def yielder():
            count = 0
            for v in self._inner:
                if count < n:
                    count += 1
                    continue
                yield v

        return self._replace(yielder())

    def chunk(self, n: int) -> "IteratorChain[tuple[T, ...]]":
        def yielder():
            count = 0
            buffer = []
            for v in self._inner:
                buffer.append(v)
                count += 1
                if count == n:
                    yield tuple(buffer)
                    buffer.clear()
                    count = 0
            if buffer:
                yield tuple(buffer)

        return self._replace(yielder())

    def uniq(self):
        # TODO: support a keyer function
        def yielder():
            seen = set()
            for v in self._inner:
                if v in seen:
                    continue
                seen.add(v)
                yield v

        return self._replace(yielder())

    def map(self, f: Callable[[T], T2]) -> "IteratorChain[T2]":
        assert callable(f), "f must be a callable"
        assert not self._moved, "Cannot reuse a dropped lift"

        def yielder():
            for v in self._inner:
                yield f(v)

        return self._replace(yielder())

    def flatmap(
        self, f: Callable[[T], Iterator[T2] | Iterable[T2]]
    ) -> "IteratorChain[T2]":
        assert callable(f), "f must be a callable"
        assert not self._moved, "Cannot reuse a dropped lift"

        def yielder():
            for v in self._inner:
                yield from f(v)

        return self._replace(yielder())

    def filter(self, pred: Callable[[T], Any]):
        def yielder():
            for v in self._inner:
                if pred(v):
                    yield v

        return self._replace(yielder())

    def group_into_dict(self, keyer: Callable[[T], T2]) -> dict[T2, list[T]]:
        grouped = defaultdict(list)
        for v in self._inner:
            key = keyer(v)
            grouped[key].append(v)
        return grouped

    def to_list(self) -> list[T]:
        return list(self._inner)

    def __next__(self):
        assert not self._moved, "Cannot reuse a dropped lift"
        return next(self._inner)

    def __iter__(self):
        return self

    def _replace(self, new_inner: Iterator[T]):
        assert not self._moved, "Cannot reuse a dropped lift"
        self._moved = True
        return IteratorChain(new_inner)


iter_chain = IteratorChain


def count(values: Iterable[Hashable]) -> dict[Hashable, int]:
    counts: dict[Hashable, int] = defaultdict(int)
    for v in values:
        counts[v] += 1
    return counts
