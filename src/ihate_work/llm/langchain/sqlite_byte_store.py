import os
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from langchain_core.stores import BaseStore

import ihate_work.o11y as o11y

logger, *_ = o11y.get_o11y(__name__)


class SqliteByteStore(BaseStore[str, bytes]):
    """A byte store implementation using SQLite as the backend.

    This store uses a SQLite database to store key-value pairs where the keys are strings
    and the values are bytes. It implements the BaseStore interface from langchain_core.

    Attributes:
        path (str): The path to the SQLite database file.
        conn (sqlite3.Connection): The SQLite database connection.
    """

    def __init__(self, path: str | Path):
        """Initialize the SQLite byte store.

        Args:
            path (str): The path to the SQLite database file.
        """
        self.path = path

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        # Connect to the SQLite database
        self.conn = sqlite3.connect(path)

        logger.debug("Connected to SQLite database at %s", path)

        # Create the table if it doesn't exist
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS byte_store (
                    key TEXT PRIMARY KEY,
                    value BLOB
                );
                """
            )

    def mget(self, keys: Sequence[str]) -> list[bytes | None]:
        """Get the values associated with the given keys.

        Args:
            keys (Sequence[str]): A sequence of keys.

        Returns:
            A list of optional values associated with the keys.
            If a key is not found, the corresponding value will be None.
        """
        if not keys:
            return []

        # Prepare placeholders for the SQL query
        placeholders = ", ".join("?" for _ in keys)

        # Execute the query
        with self.conn:
            cursor = self.conn.execute(
                f"SELECT key, value FROM byte_store WHERE key IN ({placeholders})", keys
            )

            # Create a dictionary of key-value pairs from the results
            results_dict = {key: value for key, value in cursor.fetchall()}

        # Return the values in the same order as the keys
        return [results_dict.get(key) for key in keys]

    def get(self, key: str) -> bytes | None:
        return self.mget([key])[0]

    def mset(self, key_value_pairs: Iterable[tuple[str, bytes]]) -> None:
        """Set the values for the given keys.

        Args:
            key_value_pairs (Sequence[tuple[str, bytes]]): A sequence of key-value pairs.
        """
        if not key_value_pairs:
            return

        # Execute the query
        with self.conn:
            self.conn.executemany(
                """
                INSERT OR REPLACE INTO byte_store (key, value) VALUES (?, ?)
                """,
                key_value_pairs,
            )

    def set(self, key: str, value: bytes) -> None:
        return self.mset([(key, value)])

    def mdelete(self, keys: Sequence[str]) -> None:
        """Delete the given keys and their associated values.

        Args:
            keys (Sequence[str]): A sequence of keys to delete.
        """
        if not keys:
            return

        # Prepare placeholders for the SQL query
        placeholders = ", ".join("?" for _ in keys)

        # Execute the query
        with self.conn:
            self.conn.execute(
                f"DELETE FROM byte_store WHERE key IN ({placeholders})", keys
            )

    def delete(self, key: str) -> None:
        return self.mdelete([key])

    def yield_keys(self, *, prefix: str | None = None) -> Iterator[str]:
        """Get an iterator over keys that match the given prefix.

        Args:
            prefix (str, optional): The prefix to match. Defaults to None.

        Yields:
            Iterator[str]: An iterator over keys that match the given prefix.
        """
        if prefix is None:
            # Get all keys
            with self.conn:
                cursor = self.conn.execute("SELECT key FROM byte_store")
                for (key,) in cursor.fetchall():
                    yield key
        else:
            # Get keys with the given prefix
            with self.conn:
                cursor = self.conn.execute(
                    "SELECT key FROM byte_store WHERE key LIKE ?", (f"{prefix}%",)
                )
                for (key,) in cursor.fetchall():
                    yield key

    def close(self) -> None:
        """Close the SQLite connection."""
        if hasattr(self, "conn") and self.conn:
            self.conn.close()

    def __del__(self) -> None:
        """Destructor to ensure the connection is closed."""
        self.close()
