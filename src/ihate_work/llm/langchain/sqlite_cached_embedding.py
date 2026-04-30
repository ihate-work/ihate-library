from pathlib import Path

from langchain_core.embeddings import Embeddings

from langchain.embeddings import CacheBackedEmbeddings

from .sqlite_byte_store import SqliteByteStore


def with_sqlite_cache(
    underlying_embeddings: Embeddings,
    *,
    cache_db_path: str | Path,
    namespace: str,
) -> Embeddings:
    """Wrap an embedding with a SQLite cache.

    Args:
        underlying_embeddings (Embeddings): The embedding to wrap.
        cache_db_path (str | Path): The path to the SQLite database file.
        namespace (str): Cache namespace for this model.

    Returns:
        Embeddings: The wrapped embedding with SQLite caching.
    """
    # Create a SQLite byte store
    byte_store = SqliteByteStore(cache_db_path)

    # Wrap the embedding with the byte store
    return CacheBackedEmbeddings.from_bytes_store(
        underlying_embeddings, byte_store, namespace=namespace
    )
