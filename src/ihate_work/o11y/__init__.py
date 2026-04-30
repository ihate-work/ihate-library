"""
Shared observability infrastructure.

1. otel metrics + traces + logs
2. structured logging

Usage:
    # once at startup
    setup_otel()
    setup_structlog()

    # per module
    log, tracer, meter = get_o11y(__name__)

Deps:
    - otel sdk
    - structlog
"""

import logging as _logging

import structlog as global_structlog
from opentelemetry import metrics, trace
from opentelemetry.metrics import Meter
from opentelemetry.trace import Tracer

from .defaults import setup_library_logging
from .otel import setup_otel
from .structlog import setup_structlog

# Minimal default config so logs emitted before setup_structlog() are visible
# and use the same event dict shape (event→"message", module last).
# setup_structlog() replaces this config and removes _default_handler.
global_structlog.configure(
    processors=[
        global_structlog.contextvars.merge_contextvars,
        global_structlog.processors.add_log_level,
        global_structlog.processors.TimeStamper(fmt="iso"),
        global_structlog.processors.EventRenamer("message"),
        global_structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    wrapper_class=global_structlog.stdlib.BoundLogger,
    logger_factory=global_structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=False,
)

_default_handler = _logging.StreamHandler()
_default_handler.setFormatter(
    global_structlog.stdlib.ProcessorFormatter(
        processor=global_structlog.dev.ConsoleRenderer(
            event_key="message",
            sort_keys=False,
        ),
    )
)
# Tag so setup_structlog() can find and remove it.
_default_handler._ihate_work_default = True  # type: ignore[attr-defined]
_logging.getLogger().addHandler(_default_handler)


def get_o11y(
    callsite_name: str,
) -> tuple[global_structlog.stdlib.BoundLogger, Tracer, Meter]:
    """
    Called per file like get_o11y(__name__).
    Returns a (structlog_logger, otel_tracer, otel_meter) triplet.
    """
    return (
        global_structlog.get_logger().bind(module=callsite_name),
        trace.get_tracer(callsite_name),
        metrics.get_meter(callsite_name),
    )


setup_library_logging()

__all__ = ["setup_otel", "setup_structlog", "get_o11y"]
