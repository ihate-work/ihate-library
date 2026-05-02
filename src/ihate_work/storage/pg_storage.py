import uuid
from collections.abc import Generator
from contextlib import contextmanager

import pandas as pd
import psycopg2
import psycopg2.extras
import psycopg2.pool

from ihate_work.o11y import get_o11y

logger, *_ = get_o11y(__name__)


class PgStorage:
    def __init__(self, connection_string: str, *, minconn=1, maxconn=4):
        self._pool = psycopg2.pool.ThreadedConnectionPool(minconn, maxconn, connection_string)
        logger.info("pool_created", minconn=minconn, maxconn=maxconn)

    def close(self):
        self._pool.closeall()
        logger.info("pool_closed")

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # ── Execute (DDL / DML) ──

    def execute(self, sql: str, *, parameters=None):
        logger.debug("execute", sql=sql)
        with self.use_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, parameters)

    # ── Query methods ──

    def list_tables_as_tuple(self) -> list[tuple]:
        return self.query_tuple("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")

    def query_df(self, query: str, *, parameters=None) -> pd.DataFrame:
        logger.debug("query_df", sql=query)
        with self.use_conn() as conn:
            return pd.read_sql(query, conn, params=parameters)

    def query_tuple(self, sql: str, *, parameters=None) -> list[tuple]:
        logger.debug("query_tuple", sql=sql)
        with self.use_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, parameters)
                rows = cur.fetchall()
                logger.debug("query_tuple_done", row_count=len(rows))
                return rows

    def query_dict(self, sql: str, *, parameters=None) -> list[dict]:
        logger.debug("query_dict", sql=sql)
        with self.use_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, parameters)
                rows = [dict(row) for row in cur.fetchall()]
                logger.debug("query_dict_done", row_count=len(rows))
                return rows

    def query_tuple_stream(self, sql: str, *, parameters=None, chunk_size=512) -> Generator[tuple, None, None]:
        logger.debug("query_tuple_stream", sql=sql, chunk_size=chunk_size)
        cursor_name = f"pg_stream_{uuid.uuid4().hex[:8]}"
        with self.use_conn() as conn:
            with conn.cursor(name=cursor_name) as cur:
                cur.itersize = chunk_size
                cur.execute(sql, parameters)
                while True:
                    rows = cur.fetchmany(chunk_size)
                    if not rows:
                        return
                    yield from rows

    def query_dict_stream(self, sql: str, *, parameters=None, chunk_size=512) -> Generator[dict, None, None]:
        logger.debug("query_dict_stream", sql=sql, chunk_size=chunk_size)
        cursor_name = f"pg_stream_{uuid.uuid4().hex[:8]}"
        with self.use_conn() as conn:
            with conn.cursor(name=cursor_name, cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.itersize = chunk_size
                cur.execute(sql, parameters)
                while True:
                    rows = cur.fetchmany(chunk_size)
                    if not rows:
                        return
                    yield from (dict(row) for row in rows)

    def query_df_chunk(self, sql: str, *, parameters=None, chunk_size=64) -> Generator[pd.DataFrame, None, None]:
        logger.debug("query_df_chunk", sql=sql, chunk_size=chunk_size)
        cursor_name = f"pg_chunk_{uuid.uuid4().hex[:8]}"
        with self.use_conn() as conn:
            with conn.cursor(name=cursor_name) as cur:
                cur.itersize = chunk_size
                cur.execute(sql, parameters)
                while True:
                    rows = cur.fetchmany(chunk_size)
                    if not rows:
                        return
                    cols = [desc[0] for desc in cur.description]
                    yield pd.DataFrame(rows, columns=cols)

    @contextmanager
    def use_conn(self):
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            logger.error("conn_error", exc_info=True)
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)
