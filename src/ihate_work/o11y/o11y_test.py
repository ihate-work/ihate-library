import structlog
from opentelemetry.metrics import Meter
from opentelemetry.trace import Tracer

from . import get_o11y, setup_structlog


def test_get_o11y_returns_triple():
    logger, tracer, meter = get_o11y("test_module")
    assert isinstance(logger, structlog.stdlib.BoundLogger)
    assert isinstance(tracer, Tracer)
    assert isinstance(meter, Meter)


def test_get_o11y_binds_module():
    logger, _, _ = get_o11y("my.module.name")
    # The logger should have "module" bound in its context
    ctx = structlog.get_context(logger)
    assert ctx.get("module") == "my.module.name"


def test_setup_structlog_runs_without_error():
    # Just verify it doesn't crash — it reconfigures the global structlog
    setup_structlog()


def test_logger_keyword_args():
    logger, _, _ = get_o11y("test_kw")
    # structlog loggers accept keyword args — this should not raise
    logger.info("test event", key="value", count=42)
