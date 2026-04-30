import concurrent.futures as cf
import inspect
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Generic, ParamSpec, TypeVar, cast

try:
    import streamlit as st
    from streamlit.runtime.scriptrunner import get_script_run_ctx

    ST_AVAILABLE = True
except ImportError:
    ST_AVAILABLE = False
from functools import _make_key

import ihate_work.o11y as o11y

logger, *_ = o11y.get_o11y(__name__)
_default_executor = cf.ThreadPoolExecutor()

R = TypeVar("R")

P = ParamSpec("P")


_finding_cache_storage = threading.RLock()


def versatile(c: Callable[P, R]) -> "PolymorphicCallable[P, R]":
    """_summary_

    Args:
        c (Callable[P, R]): _description_

    Returns:
        PolymorphicCallable[P, R]: wrapped callable that can be transformed at callsite
    """

    def decorator(_callable: Callable) -> Callable:
        assert callable(_callable)
        callable_sig = _get_signature(_callable)
        return PolymorphicCallable(_callable, callable_sig)

    return cast(PolymorphicCallable[P, R], decorator(c))


class CacheStorage(dict):
    # TODO: implement cache capacity
    # TODO: implement ttl
    pass


_global_cache: defaultdict[str, CacheStorage] = defaultdict(lambda: CacheStorage())


class PolymorphicCallable(Generic[P, R]):
    """
    Wrapped callable to provide caching / transformations
    """

    def __init__(
        self,
        callable_: Callable[P, R],
        callable_sig: str,
        _cache_store: CacheStorage | None = None,
    ):
        self._callable = callable_
        self._callable_sig = callable_sig
        self._cache_store = _cache_store

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        if self._cache_store is not None:
            logger.debug("calling with cache %s", type(self._cache_store))
            return _call_with_cache(self._callable, self._cache_store, *args, **kwargs)
        else:
            return self._callable(*args, **kwargs)

    def __hash__(self):
        return hash(("polymorphic_callable", self._callable_sig))

    @property
    def with_global_cache(self) -> "PolymorphicCallable[P, R]":
        assert self._cache_store is None, "cache policy already set"
        with _finding_cache_storage:
            cache_storage = _global_cache[self._callable_sig]
        return PolymorphicCallable(self._callable, self._callable_sig, cache_storage)

    @property
    def with_st_session_cache(self) -> "PolymorphicCallable[P, R]":
        assert self._cache_store is None, "cache policy already set"
        assert ST_AVAILABLE, "streamlit not available"
        assert get_script_run_ctx(), "not in a Streamlit ScriptThread"

        cache_key = "_poly_callable_caches"

        with _finding_cache_storage:
            if "_poly_callable_caches" in st.session_state:
                all_cache_storage = st.session_state[cache_key]
            else:
                st.session_state[cache_key] = (
                    all_cache_storage := defaultdict(lambda: CacheStorage())
                )
            cache_storage = all_cache_storage[self._callable_sig]
        return PolymorphicCallable(self._callable, self._callable_sig, cache_storage)

    @property
    def in_worker(self) -> Callable[P, cf.Future[R]]:
        return lambda *args, **kwargs: _default_executor.submit(
            lambda: _call_with_cache(self._callable, self._cache_store, *args, **kwargs)
        )


def _call_with_cache(
    callable: Callable[P, R],
    _cache: CacheStorage | dict | None,
    *args: P.args,
    **kwargs: P.kwargs,
):
    if _cache is None:
        return callable(*args, **kwargs)
    args_hash = hash(_make_key(args, kwargs, typed=True))
    with _finding_cache_storage:
        if args_hash in _cache:
            logger.debug("function call: cache hit")
            return _cache[args_hash]
    logger.debug("function call: cache miss")
    result = callable(*args, **kwargs)
    with _finding_cache_storage:
        logger.debug("function call: cache filled")
        _cache[args_hash] = result
        return result


def _get_signature(f: Callable) -> str:
    """_summary_

    Args:
        f (Callable): _description_

    Returns:
        str: A hash-like string taking into account the function's module, file, line number, and source code lines. Should be unique across executions of the same code.
    """
    logger.debug("module: %s", f.__module__)
    logger.debug("file: %s", inspect.getabsfile(f))
    lines, lineno = inspect.getsourcelines(f)
    logger.debug("srclines: %s / %s", lines, lineno)
    h = hash(
        (
            f.__module__,
            inspect.getabsfile(f),
            lineno,
            tuple(lines),
            # inspect.getsource(f),
            # inspect.getsourcefile(f)
        )
    )
    return f"{f.__module__}:{inspect.getabsfile(f)}:{lineno} ${h}"
