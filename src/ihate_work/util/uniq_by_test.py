from .uniq_by import uniq_by


def test_uniq_by_identity():
    result = uniq_by([1, 2, 3, 2, 1], key=lambda x: x)
    assert result == [1, 2, 3]


def test_uniq_by_key():
    items = [{"name": "a", "v": 1}, {"name": "b", "v": 2}, {"name": "a", "v": 3}]
    result = uniq_by(items, key=lambda x: x["name"])
    assert len(result) == 2


def test_last_wins():
    items = [{"name": "a", "v": 1}, {"name": "a", "v": 2}]
    result = uniq_by(items, key=lambda x: x["name"])
    assert result[0]["v"] == 2


def test_empty_input():
    result = uniq_by([], key=lambda x: x)
    assert result == []
