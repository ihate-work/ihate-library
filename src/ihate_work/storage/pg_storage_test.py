import os

import pytest

_CONN = os.environ.get("IHATE_WORK_TEST_PGSTORAGE_CONN")
_skip = pytest.mark.skipif(_CONN is None, reason="IHATE_WORK_TEST_PGSTORAGE_CONN not set")


@pytest.fixture()
def pg():
    from .pg_storage import PgStorage

    storage = PgStorage(_CONN)
    storage.execute("DROP TABLE IF EXISTS _test_storage")
    storage.execute("CREATE TABLE _test_storage (id INTEGER, name VARCHAR)")
    yield storage
    storage.execute("DROP TABLE IF EXISTS _test_storage")
    storage.close()


@_skip
def test_execute_and_query_tuple(pg):
    pg.execute("INSERT INTO _test_storage VALUES (1, 'alice'), (2, 'bob')")
    rows = pg.query_tuple("SELECT * FROM _test_storage ORDER BY id")
    assert rows == [(1, "alice"), (2, "bob")]


@_skip
def test_query_dict(pg):
    pg.execute("INSERT INTO _test_storage VALUES (1, 'alice')")
    rows = pg.query_dict("SELECT * FROM _test_storage")
    assert rows == [{"id": 1, "name": "alice"}]


@_skip
def test_query_df(pg):
    pg.execute("INSERT INTO _test_storage VALUES (1, 'alice')")
    df = pg.query_df("SELECT * FROM _test_storage")
    assert len(df) == 1
    assert df.iloc[0]["id"] == 1


@_skip
def test_query_tuple_stream(pg):
    pg.execute("INSERT INTO _test_storage SELECT g, 'row' FROM generate_series(1,10) g")
    rows = list(pg.query_tuple_stream("SELECT * FROM _test_storage ORDER BY id", chunk_size=3))
    assert len(rows) == 10
    assert rows[0] == (1, "row")


@_skip
def test_query_dict_stream(pg):
    pg.execute("INSERT INTO _test_storage VALUES (1, 'alice'), (2, 'bob')")
    rows = list(pg.query_dict_stream("SELECT * FROM _test_storage ORDER BY id", chunk_size=1))
    assert len(rows) == 2
    assert rows[0] == {"id": 1, "name": "alice"}


@_skip
def test_query_df_chunk(pg):
    pg.execute("INSERT INTO _test_storage SELECT g, 'row' FROM generate_series(1,5) g")
    chunks = list(pg.query_df_chunk("SELECT * FROM _test_storage ORDER BY id", chunk_size=2))
    assert len(chunks) >= 1
    total_rows = sum(len(c) for c in chunks)
    assert total_rows == 5


@_skip
def test_list_tables(pg):
    tables = pg.list_tables_as_tuple()
    names = [t[0] for t in tables]
    assert "_test_storage" in names


@_skip
def test_context_manager():
    from .pg_storage import PgStorage

    with PgStorage(_CONN) as storage:
        storage.execute("SELECT 1")
