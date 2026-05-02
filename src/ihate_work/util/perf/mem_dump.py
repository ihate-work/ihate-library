"""Dump tracemalloc allocation stats on signal.

earlyoom sends SIGTERM (catchable) before Linux OOM killer sends SIGKILL
(uncatchable). Call ``setup_mem_dump_on_signal()`` early in your program to
start tracemalloc and register a handler that prints the top allocation
sites when the process receives the configured signal(s).
"""

from __future__ import annotations

import os
import signal
import sys
import tracemalloc
import types
from collections.abc import Sequence

from ihate_work.o11y import get_o11y

logger, *_ = get_o11y(__name__)

_DEFAULT_TOP_N = 30
_DEFAULT_SIGNALS = (signal.SIGTERM,)


def _dump_handler(signum: int, frame: types.FrameType | None) -> None:
    """Dump tracemalloc snapshot then exit."""
    sig_name = signal.Signals(signum).name

    if not tracemalloc.is_tracing():
        logger.warning("tracemalloc not active, skipping memory dump", signal=sig_name)
        sys.exit(1)

    snapshot = tracemalloc.take_snapshot()
    snapshot = snapshot.filter_traces(
        [
            tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
            tracemalloc.Filter(False, "<frozen importlib._bootstrap_external>"),
            tracemalloc.Filter(False, "<unknown>"),
        ]
    )

    stats = snapshot.statistics("lineno")

    total_mb = sum(s.size for s in stats) / (1024 * 1024)
    lines = [
        f"{sig_name} received — tracemalloc top {min(_DEFAULT_TOP_N, len(stats))} "
        f"allocations (tracked total: {total_mb:.1f} MiB):",
    ]
    for stat in stats[:_DEFAULT_TOP_N]:
        lines.append(f"  {stat}")

    # Use stderr directly — logger may be broken if we're mid-OOM.
    pid = os.getpid()
    msg = "\n".join(lines)
    print(f"[pid={pid}] {msg}", file=sys.stderr, flush=True)
    logger.info(
        "mem_dump_on_signal",
        pid=pid,
        signal=sig_name,
        tracked_mib=f"{total_mb:.1f}",
        top_n=len(stats[:_DEFAULT_TOP_N]),
    )

    sys.exit(1)


def setup_mem_dump_on_signal(
    *,
    signals: Sequence[signal.Signals] = _DEFAULT_SIGNALS,
    nframes: int = 5,
) -> None:
    """Start tracemalloc and register signal handler(s) that dump allocations.

    Args:
        signals: Signals to handle. Default ``(SIGTERM,)``.
            SIGKILL cannot be caught — use SIGTERM (earlyoom) or
            SIGUSR1 (manual dump without killing).
        nframes: Number of stack frames to store per allocation (higher = more
            detail but more overhead). Default 5 is a good balance.

    Call this once at program startup, before the heavy work begins::

        from ihate_work.util.perf import setup_mem_dump_on_signal
        setup_mem_dump_on_signal()

        # or with SIGUSR1 for on-demand dumps:
        setup_mem_dump_on_signal(signals=(signal.SIGTERM, signal.SIGUSR1))
    """
    if not tracemalloc.is_tracing():
        tracemalloc.start(nframes)
        logger.debug("tracemalloc started", nframes=nframes)

    registered = []
    for sig in signals:
        if sig == signal.SIGKILL:
            logger.warning("SIGKILL cannot be caught, skipping", signal=sig.name)
            continue
        signal.signal(sig, _dump_handler)
        registered.append(sig.name)

    logger.debug("mem dump handler registered", signals=registered)
