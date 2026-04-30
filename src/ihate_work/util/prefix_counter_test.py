from .prefix_counter import PrefixCounter


def test_empty_counter():
    pc = PrefixCounter()
    assert pc.count == 0
    assert pc.is_leaf
    assert pc.depth == 0


def test_add_single_element():
    pc = PrefixCounter()
    pc.add(("a", "b", "leaf"))
    assert pc.count == 1
    assert not pc.is_leaf


def test_from_tuples():
    tuples = [
        ("a", "b", "x"),
        ("a", "b", "y"),
        ("a", "c", "z"),
    ]
    pc = PrefixCounter.from_tuples(iter(tuples))
    assert pc.count == 3


def test_own_count():
    pc = PrefixCounter()
    pc.add(("a", "b", "x"))
    pc.add(("a",))  # only reaches root + "a" level
    # root count = 2, child "a" count = 2
    assert pc.count == 2


def test_depth():
    pc = PrefixCounter()
    pc.add(("a", "b", "c", "leaf"))
    # depth = 3 (a -> b -> c)
    assert pc.depth == 3


def test_leaf_samples():
    pc = PrefixCounter()
    for i in range(5):
        pc.add(("a", f"item_{i}"))
    # leaf_samples are collected at the single-element level


def test_pprint():
    pc = PrefixCounter()
    pc.add(("a", "b", "x"))
    pc.add(("a", "c", "y"))
    lines = pc.pprint()
    assert len(lines) > 0
    assert "PrefixCounter" in lines[0]
