from .sqlite_byte_store import SqliteByteStore


def test_sqlite_byte_store(tmp_path):
    store = SqliteByteStore(tmp_path / "test.db")

    # Test inserting a key-value pair
    store.set("key1", b"value1")
    assert store.get("key1") == b"value1"

    # Test getting a missing key
    assert store.get("key2") is None

    # Test updating a key-value pair
    store.set("key1", b"new_value")
    assert store.get("key1") == b"new_value"

    # Test deleting a key-value pair
    store.delete("key1")
    assert store.get("key1") is None

    # Test batch operations
    store.mset({"key2": b"value2", "key3": b"value3"}.items())
    assert store.mget(["key2", "key3"]) == [b"value2", b"value3"]

    # Test yield_keys
    keys = list(store.yield_keys())
    assert sorted(keys) == ["key2", "key3"]

    # Test yield_keys with prefix
    store.set("prefix_a", b"val_a")
    keys = list(store.yield_keys(prefix="prefix_"))
    assert keys == ["prefix_a"]

    store.close()
