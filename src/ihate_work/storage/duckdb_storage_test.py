import json
import subprocess
import sys
import textwrap

import duckdb
import pytest

from .duckdb_storage import DuckdbStorage


def test_execute_and_query(tmp_path):
    db = DuckdbStorage(tmp_path / "test.duckdb")
    db.execute("CREATE TABLE t (id INTEGER, name VARCHAR)")
    db.execute("INSERT INTO t VALUES (1, 'alice'), (2, 'bob')")
    rows = db.query_tuple("SELECT * FROM t ORDER BY id")
    assert rows == [(1, "alice"), (2, "bob")]


def test_query_dict(tmp_path):
    db = DuckdbStorage(tmp_path / "test.duckdb")
    db.execute("CREATE TABLE t (id INTEGER, name VARCHAR)")
    db.execute("INSERT INTO t VALUES (1, 'alice')")
    result = db.query_dict("SELECT * FROM t")
    assert result == [{"id": 1, "name": "alice"}]


def test_query_df(tmp_path):
    db = DuckdbStorage(tmp_path / "test.duckdb")
    db.execute("CREATE TABLE t (id INTEGER, val FLOAT)")
    db.execute("INSERT INTO t VALUES (1, 3.14)")
    df = db.query_df("SELECT * FROM t")
    assert len(df) == 1
    assert df.iloc[0]["id"] == 1


def test_import_jsonl(tmp_path):
    db = DuckdbStorage(tmp_path / "test.duckdb")
    db.execute("CREATE TABLE t (id INTEGER, name VARCHAR)")
    lines = [
        json.dumps({"id": 1, "name": "alice"}),
        json.dumps({"id": 2, "name": "bob"}),
    ]
    count = db.import_jsonl("t", iter(lines))
    assert count == 2


def test_import_jsonl_reencode(tmp_path):
    db = DuckdbStorage(tmp_path / "test.duckdb")
    db.execute("CREATE TABLE t (id INTEGER, name VARCHAR)")
    # pretty-printed JSON that needs re-encoding
    lines = ['{\n  "id": 1,\n  "name": "alice"\n}']
    count = db.import_jsonl("t", iter(lines), reencode=True)
    assert count == 1


def test_list_tables(tmp_path):
    db = DuckdbStorage(tmp_path / "test.duckdb")
    db.execute("CREATE TABLE foo (id INTEGER)")
    db.execute("CREATE TABLE bar (id INTEGER)")
    tables = db.list_tables_as_tuple()
    table_names = sorted(t[0] for t in tables)
    assert table_names == ["bar", "foo"]


def test_query_tuple_stream(tmp_path):
    db = DuckdbStorage(tmp_path / "test.duckdb")
    db.execute("CREATE TABLE t (id INTEGER)")
    db.execute("INSERT INTO t SELECT unnest(range(10))")
    rows = list(db.query_tuple_stream("SELECT * FROM t ORDER BY id", chunk_size=3))
    assert len(rows) == 10
    assert rows[0] == (0,)


def test_exists(tmp_path):
    path = tmp_path / "test.duckdb"
    assert not path.exists()
    db = DuckdbStorage(path)
    # connect() eagerly creates the file
    assert db.exists()


def test_exists_memory():
    db = DuckdbStorage(":memory:")
    assert db.exists()


def test_memory(tmp_path):
    db = DuckdbStorage(":memory:")
    db.execute("CREATE TABLE t (id INTEGER)")
    db.execute("INSERT INTO t VALUES (1), (2)")
    # State persists across method calls (same root connection)
    assert db.query_tuple("SELECT count(*) FROM t") == [(2,)]
    # Cursors see the same data
    cur = db.cursor()
    assert cur.execute("SELECT id FROM t ORDER BY id").fetchall() == [(1,), (2,)]


def test_is_newly_created_memory():
    db = DuckdbStorage(":memory:")
    assert db.is_newly_created is True


def test_is_newly_created_new_file(tmp_path):
    db = DuckdbStorage(tmp_path / "new.duckdb")
    assert db.is_newly_created is True


def test_is_newly_created_existing_file(tmp_path):
    path = tmp_path / "existing.duckdb"
    # Create the db file first
    db1 = DuckdbStorage(path)
    db1.execute("CREATE TABLE t (id INTEGER)")
    del db1
    # Re-open — file already exists
    db2 = DuckdbStorage(path)
    assert db2.is_newly_created is False


def test_query_dict_stream(tmp_path):
    db = DuckdbStorage(tmp_path / "test.duckdb")
    db.execute("CREATE TABLE t (id INTEGER, name VARCHAR)")
    db.execute("INSERT INTO t VALUES (1, 'alice'), (2, 'bob'), (3, 'carol')")
    rows = list(db.query_dict_stream("SELECT * FROM t ORDER BY id", chunk_size=2))
    assert len(rows) == 3
    assert rows[0] == {"id": 1, "name": "alice"}
    assert rows[2] == {"id": 3, "name": "carol"}


def test_query_df_chunk_with_parameters(tmp_path):
    db = DuckdbStorage(tmp_path / "test.duckdb")
    db.execute("CREATE TABLE t (id INTEGER, val FLOAT)")
    db.execute("INSERT INTO t VALUES (1, 1.0), (2, 2.0), (3, 3.0)")
    chunks = list(db.query_df_chunk(
        "SELECT * FROM t WHERE id > $1 ORDER BY id",
        parameters=(1,),
        chunk_size=1,
    ))
    assert len(chunks) >= 1
    all_ids = sorted(int(row) for chunk in chunks for row in chunk["id"])
    assert all_ids == [2, 3]


# ── Multi-process concurrency model tests ──


def _seed_db(path):
    """Create a small table so readers have something to query."""
    db = DuckdbStorage(path)
    db.execute("CREATE TABLE t (id INTEGER, name VARCHAR)")
    db.execute("INSERT INTO t VALUES (1, 'alice'), (2, 'bob')")
    del db  # close connection


def test_multiple_readonly_opens_same_process(tmp_path):
    """Multiple read-only connections in the same process share the instance."""
    db_path = tmp_path / "test.duckdb"
    _seed_db(db_path)

    r1 = DuckdbStorage(db_path, read_only=True)
    r2 = DuckdbStorage(db_path, read_only=True)
    r3 = DuckdbStorage(db_path, read_only=True)

    for r in (r1, r2, r3):
        rows: list[tuple[int, str]] = r.query_typed_tuple(
            "SELECT * FROM t ORDER BY id"
        )
        assert rows == [(1, "alice"), (2, "bob")]


def test_mixed_config_same_process_fails(tmp_path):
    """Same process, different access_mode → ConnectionException (shared instance
    can't have two configs)."""
    db_path = tmp_path / "test.duckdb"
    _seed_db(db_path)

    _ro = DuckdbStorage(db_path, read_only=True)  # noqa: F841 — kept alive

    with pytest.raises(duckdb.ConnectionException):
        DuckdbStorage(db_path, read_only=False)


def test_second_rw_same_process_ok(tmp_path):
    """Same process, two RW opens → works (DuckDB shares the instance)."""
    db_path = tmp_path / "test.duckdb"
    _seed_db(db_path)

    rw1 = DuckdbStorage(db_path, read_only=False)
    rw2 = DuckdbStorage(db_path, read_only=False)

    rows: list[tuple[int, str]] = rw2.query_typed_tuple(
        "SELECT * FROM t ORDER BY id"
    )
    assert rows == [(1, "alice"), (2, "bob")]
    del rw1  # just proving both coexist


# ── Multi-process tests (actual OS-level lock contention) ──

def _run_duckdb_subprocess(db_path: str, read_only: bool) -> subprocess.Popen:
    """Spawn a child that opens the db, prints READY, then waits for EOF on stdin."""
    script = textwrap.dedent(f"""\
        import duckdb, sys
        try:
            conn = duckdb.connect({db_path!r}, read_only={read_only!r})
            print("READY", flush=True)
            sys.stdin.readline()  # block until parent closes stdin
        except Exception as e:
            print(f"ERROR:{{type(e).__name__}}:{{e}}", flush=True)
            sys.exit(1)
    """)
    return subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_multiple_readonly_opens_multi_process(tmp_path):
    """Multiple processes can open the same file read-only concurrently."""
    db_path = tmp_path / "test.duckdb"
    _seed_db(db_path)
    db_str = str(db_path)

    procs = [_run_duckdb_subprocess(db_str, read_only=True) for _ in range(3)]
    try:
        for p in procs:
            line = p.stdout.readline().strip()
            assert line == "READY", f"subprocess failed: {line}"
    finally:
        for p in procs:
            p.stdin.close()
            p.wait(timeout=5)


def test_rw_while_readonly_open_multi_process(tmp_path):
    """A second process can't open RW while another holds a RO connection."""
    db_path = tmp_path / "test.duckdb"
    _seed_db(db_path)
    db_str = str(db_path)

    ro_proc = _run_duckdb_subprocess(db_str, read_only=True)
    try:
        line = ro_proc.stdout.readline().strip()
        assert line == "READY"

        rw_proc = _run_duckdb_subprocess(db_str, read_only=False)
        line = rw_proc.stdout.readline().strip()
        assert line.startswith("ERROR:"), f"expected error, got: {line}"
        rw_proc.wait(timeout=5)
        assert rw_proc.returncode != 0
    finally:
        ro_proc.stdin.close()
        ro_proc.wait(timeout=5)


def test_readonly_while_rw_open_multi_process(tmp_path):
    """A second process can't open RO while another holds a RW connection."""
    db_path = tmp_path / "test.duckdb"
    _seed_db(db_path)
    db_str = str(db_path)

    rw_proc = _run_duckdb_subprocess(db_str, read_only=False)
    try:
        line = rw_proc.stdout.readline().strip()
        assert line == "READY"

        ro_proc = _run_duckdb_subprocess(db_str, read_only=True)
        line = ro_proc.stdout.readline().strip()
        assert line.startswith("ERROR:"), f"expected error, got: {line}"
        ro_proc.wait(timeout=5)
        assert ro_proc.returncode != 0
    finally:
        rw_proc.stdin.close()
        rw_proc.wait(timeout=5)


def test_second_rw_multi_process(tmp_path):
    """A second process can't open RW while another already has RW."""
    db_path = tmp_path / "test.duckdb"
    _seed_db(db_path)
    db_str = str(db_path)

    rw1 = _run_duckdb_subprocess(db_str, read_only=False)
    try:
        line = rw1.stdout.readline().strip()
        assert line == "READY"

        rw2 = _run_duckdb_subprocess(db_str, read_only=False)
        line = rw2.stdout.readline().strip()
        assert line.startswith("ERROR:"), f"expected error, got: {line}"
        rw2.wait(timeout=5)
        assert rw2.returncode != 0
    finally:
        rw1.stdin.close()
        rw1.wait(timeout=5)
