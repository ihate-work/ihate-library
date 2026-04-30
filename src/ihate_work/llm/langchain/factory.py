import os
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

import ihate_work.o11y as o11y

from .sqlite_cached_embedding import with_sqlite_cache

logger, *_ = o11y.get_o11y(__name__)


def get_embedding_model(
    model_spec: str, cache_path: str | Path | None = None, **kwargs
) -> "Embeddings":
    """Create embeddings client from model_spec str. Now supports 'ollama:MODEL'"""
    try:
        provider, model = (model_spec or "undefined:undefined").split(":", 1)
    except Exception as e:
        raise ValueError(f"Invalid model specifier: {model_spec}") from e
    if cache_path is None:
        cache_path = os.getenv("EMBEDDING_CACHE_DB")

    if provider == "ollama":
        from langchain_ollama import (
            OllamaEmbeddings,
        )

        base_url = kwargs.pop("base_url", None)

        return _maybe_cached_embedding(
            OllamaEmbeddings(
                base_url=base_url or _get_ollama_base_url(), model=model, **kwargs
            ),
            cache_path=cache_path,
            model=model,
        )
    else:
        raise ValueError(f"Unknown embedding model: {model_spec}")


def get_chat_model(model_spec: str, **kwargs) -> "BaseChatModel":
    try:
        provider, model = (model_spec or "undefined:undefined").split(":", 1)
    except Exception as e:
        raise ValueError(f"Invalid model specifier: {model_spec}") from e

    if provider == "ollama":
        base_url = kwargs.pop("base_url", None)

        from langchain_ollama import (
            ChatOllama,
        )

        return ChatOllama(
            base_url=base_url or _get_ollama_base_url(),
            model=model,
            **kwargs,
        )
    else:
        raise ValueError(f"Unknown embedding model: {model_spec}")


def _get_ollama_base_url() -> str:
    """Get the base URL for the Ollama API from environment variables."""
    base_url = os.getenv("OLLAMA_BASE_URL")
    if not base_url:
        raise ValueError(
            "OLLAMA_BASE_URL environment variable is not set. "
            "Please set it to the base URL of your Ollama API."
        )
    return base_url


def _maybe_cached_embedding(
    inner: Embeddings, *, model: str, cache_path: str | Path | None = None
) -> Embeddings:
    """Wrap an embedding with a SQLite cache if cache_path is provided."""
    if cache_path:
        return with_sqlite_cache(inner, cache_db_path=cache_path, namespace=model)
    return inner
