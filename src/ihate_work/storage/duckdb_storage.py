from __future__ import annotations

import json
import tempfile
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar
from warnings import deprecated

import duckdb

import ihate_work.o11y as o11y

if TYPE_CHECKING:
    import pandas as pd

logger, *_ = o11y.get_o11y(__name__)

T_Tuple = TypeVar("T_Tuple", bound=tuple)
T_NamedTuple = TypeVar("T_NamedTuple", bound=tuple)


def _quote_ident(name: str) -> str:
    """Quote a SQL identifier to prevent injection."""
    return '"' + name.replace('"', '""') + '"'


class DuckdbStorage:
    """DuckDB storage backed by a single root connection.

    Supports both file-backed and ``:memory:`` databases.
    The connection is opened eagerly in ``__init__``.

    ``cursor()`` returns a thread-safe cursor derived from the root connection.

    Multi-process access
    --------------------
    DuckDB allows only **one** read-write process at a time, but **multiple**
    read-only processes can open the same file concurrently.  Pass
    ``read_only=True`` to open in shared-read mode — safe for multi-process
    readers (e.g. web workers serving queries while a writer ingests data).
    """

    def __init__(self, db_path: str | Path = ":memory:", *, read_only: bool = False):
        self._db_path = str(db_path)
        if self._db_path != ":memory:":
            self._db = Path(self._db_path)
        else:
            self._db = None
        self._read_only = read_only
        self._is_newly_created = self._db is None or not self._db.exists()

        self._conn: duckdb.DuckDBPyConnection = None  # to prevent __del__ failure when connect fails
        self._conn = duckdb.connect(db_path, read_only=read_only)

    @property
    def is_newly_created(self) -> bool:
        """True when the db file didn't exist before connect (including :memory:)."""
        return self._is_newly_created

    # ── Lifecycle ──

    def cursor(self) -> duckdb.DuckDBPyConnection:
        """Return a new cursor. Safe to use from any thread."""
        return self._conn.cursor()

    def _execute_on_cursor(self, fn):
        """Run fn(cursor) with a cursor that is closed afterwards."""
        cur = self.cursor()
        try:
            return fn(cur)
        finally:
            cur.close()

    def __del__(self) -> None:
        conn = getattr(self, "_conn", None)
        if conn is not None:
            conn.close()

    def exists(self) -> bool:
        if self._db is None:
            return True
        return self._db.exists()

    # ── Extension management ──

    def update_extensions(self):
        self._execute_on_cursor(lambda cur: cur.execute("UPDATE EXTENSIONS"))

    def install_extension(self, name: str, *, repository: str = "core"):
        self._execute_on_cursor(lambda cur: cur.install_extension(name, repository=repository))

    def load_extension(self, name: str):
        self._execute_on_cursor(lambda cur: cur.load_extension(name))

    # ── Execute (DDL / DML) ──

    def execute(self, sql: str, *, parameters=None):
        self._execute_on_cursor(lambda cur: cur.execute(sql, parameters=parameters))

    # ── Bulk import ──

    def import_jsonl(
        self,
        table: str,
        lines: Iterator[str],
        *,
        reencode: bool = False,
    ) -> int:
        """Write JSON lines to a temp file, then COPY into the target table.

        Each element in lines should be a complete JSON string (no trailing newline needed).
        If reencode is True, each line is re-parsed and re-serialized to strip
        internal newlines / pretty-printing, ensuring valid JSONL.
        Returns the row count of the target table after import.
        """
        quoted = _quote_ident(table)
        cur = self.cursor()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                tmp_path = f"{temp_dir}/{table}.jsonl"
                with open(tmp_path, "w") as f:
                    for line in lines:
                        if reencode:
                            line = json.dumps(json.loads(line), ensure_ascii=False)
                        f.write(line + "\n")
                cur.execute(f"COPY {quoted} FROM '{tmp_path}'")
                result = cur.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()
                return result[0]
        finally:
            cur.close()

    # ── Query methods ──

    def list_tables_as_tuple(self) -> list[tuple[str]]:
        return self.query_typed_tuple("SHOW TABLES")

    def query_df(self, query: str, *, parameters: tuple | None = None) -> pd.DataFrame:
        cur = self.cursor()
        try:
            return cur.execute(query=query, parameters=parameters).df()
        finally:
            cur.close()

    @deprecated("Use query_typed_tuple or query_named_tuple instead")
    def query_tuple(self, sql: str, *, parameters=None) -> list[tuple]:
        cur = self.cursor()
        try:
            return cur.execute(sql, parameters=parameters).fetchall()
        finally:
            cur.close()

    def query_typed_tuple(self, sql: str, *, parameters=None) -> list[T_Tuple]:
        """Run sql and return rows as plain tuples, typed per caller's annotation.

        The row type is a pure type hint — rows are plain tuples at runtime.
        Annotate the return variable so the checker can infer T_Tuple:
            rows: list[tuple[int, str]] = db.query_typed_tuple("SELECT id, name ...")
        """
        cur = self.cursor()
        try:
            return cur.execute(sql, parameters=parameters).fetchall()  # type: ignore[return-value]
        finally:
            cur.close()

    def query_named_tuple(self, sql: str, row_type: type[T_NamedTuple], *, parameters=None) -> list[T_NamedTuple]:
        """Run sql and return rows as instances of `row_type` (a NamedTuple class)."""
        cur = self.cursor()
        try:
            raw = cur.execute(sql, parameters=parameters).fetchall()
            return [row_type(*r) for r in raw]
        finally:
            cur.close()

    def query_dict(self, sql: str, *, parameters=None) -> list[dict]:
        """Run sql and return rows as dicts. Column names inferred from cursor."""
        cur = self.cursor()
        try:
            cur.execute(sql, parameters=parameters)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            cur.close()

    def query_tuple_stream(
        self,
        sql: str,
        *,
        parameters=None,
        chunk_size=512,
    ) -> Generator[tuple, None, None]:
        cur = self.cursor()
        try:
            cur.execute(sql, parameters=parameters)
            while True:
                rows = cur.fetchmany(chunk_size)
                if not rows:
                    return
                yield from rows
        finally:
            cur.close()

    def query_dict_stream(
        self,
        sql: str,
        *,
        parameters=None,
        chunk_size=512,
    ) -> Generator[dict, None, None]:
        """Stream rows as dicts. Column names inferred from cursor."""
        cur = self.cursor()
        try:
            cur.execute(sql, parameters=parameters)
            cols = [d[0] for d in cur.description]
            while True:
                rows = cur.fetchmany(chunk_size)
                if not rows:
                    return
                yield from (dict(zip(cols, row)) for row in rows)
        finally:
            cur.close()

    def query_df_chunk(self, sql: str, *, parameters=None, chunk_size=64) -> Generator[pd.DataFrame, None, None]:
        cur = self.cursor()
        try:
            cur.execute(sql, parameters=parameters)
            while True:
                chunk_df = cur.fetch_df_chunk(chunk_size)
                if chunk_df.empty:
                    break
                yield chunk_df
        finally:
            cur.close()
