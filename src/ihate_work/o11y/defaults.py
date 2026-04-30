import logging
from threading import Lock

_setup_lock = Lock()
_setup_done = False


def setup_library_logging():
    """
    Sane default for some noisy libraries.  Called by __init__.py.
    Must only be called once.
    """
    global _setup_done
    with _setup_lock:
        if _setup_done:
            raise RuntimeError("setup_library_logging() must only be called once")
        _setup_done = True
    for info_only in (
        "httpcore",
        "sqlalchemy",
        "PIL",
        "sse_starlette",
        "urllib3",
        "multipart",
    ):
        logging.getLogger(info_only).setLevel(logging.INFO)

    for warn_only in (
        "httpx",
        "elastic_transport.transport",
        "watchfiles",
        "LiteLLM",
    ):
        logging.getLogger(warn_only).setLevel(logging.WARN)
