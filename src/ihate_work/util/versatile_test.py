from .versatile import versatile


def test_versatile_passthrough():
    @versatile
    def add(a, b):
        return a + b

    assert add(1, 2) == 3


def test_versatile_with_global_cache():
    call_count = 0

    @versatile
    def expensive(x):
        nonlocal call_count
        call_count += 1
        return x * 2

    cached = expensive.with_global_cache
    assert cached(5) == 10
    assert cached(5) == 10
    assert call_count == 1  # only called once


def test_versatile_cache_different_args():
    call_count = 0

    @versatile
    def compute(x):
        nonlocal call_count
        call_count += 1
        return x + 1

    cached = compute.with_global_cache
    assert cached(1) == 2
    assert cached(2) == 3
    assert call_count == 2


def test_versatile_no_cache_calls_every_time():
    call_count = 0

    @versatile
    def greet(name):
        nonlocal call_count
        call_count += 1
        return f"hello {name}"

    assert greet("world") == "hello world"
    assert greet("world") == "hello world"
    assert call_count == 2
