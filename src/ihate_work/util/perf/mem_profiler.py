"""Object-level memory profiling via pympler.

pympler is lazy-imported: ``import ihate_work.util.perf.mem_profiler``
has zero cost when pympler is not installed.  The ``ImportError`` surfaces
when you call ``setup_mem_profiler()`` — fail loud at setup, not at use.
"""

from __future__ import annotations

from types import ModuleType

from ihate_work.o11y import get_o11y

logger, *_ = get_o11y(__name__)

_muppy: ModuleType | None = None
_summary: ModuleType | None = None


def setup_mem_profiler() -> None:
    """Eagerly import pympler so that subsequent calls work.

    Raises:
        ImportError: If pympler is not installed.
    """
    global _muppy, _summary
    from pympler import muppy, summary  # noqa: WPS433

    _muppy = muppy
    _summary = summary
    logger.debug("pympler loaded")


def report_memory_usage() -> None:
    """Print a pympler object summary to stdout.

    Call ``setup_mem_profiler()`` once before using this function.
    """
    if _muppy is None or _summary is None:
        raise RuntimeError(
            "pympler not loaded — call setup_mem_profiler() first"
        )
    all_objects = _muppy.get_objects()
    sum1 = _summary.summarize(all_objects)
    _summary.print_(sum1)
