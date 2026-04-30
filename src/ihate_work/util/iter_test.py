from pytest import raises

from .iter import batched, iter_chain


def test_batched():
    values = list(range(0, 15))
    assert list(batched(values, 4)) == [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (8, 9, 10, 11),
        (12, 13, 14),
    ]


def test_iter_chain():
    # inner = range(0, 100).__iter__()

    assert iter_chain(range(0, 100)).take(10).to_list() == list(range(0, 10))
    assert iter_chain(range(0, 100)).chunk(3).skip(1).take(2).to_list() == [
        # (0, 1, 2),
        (3, 4, 5),
        (6, 7, 8),
    ]

    assert iter_chain(range(0, 100)).filter(lambda x: x % 2 == 0).take(5).to_list() == [
        0,
        2,
        4,
        6,
        8,
    ]


def test_iter_chain_unlimited():
    def unlimited_range(start: int, stop: int):
        value = start
        while value < stop:
            yield value
            value += 1
        raise AssertionError("This should never be reached")

    assert iter_chain(unlimited_range(0, 100)).take(10).to_list() == list(range(0, 10))
    with raises(AssertionError):
        iter_chain(unlimited_range(0, 100)).take(101).to_list()


def test_iter_chain_dictvalue():
    d = {"a": 1, "b": 2, "c": 3}
    assert iter_chain(d.values()).to_list() == [1, 2, 3]
