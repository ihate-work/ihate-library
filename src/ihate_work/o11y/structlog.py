import logging
import threading
from datetime import datetime, timezone
from os import getenv
from threading import Lock

import structlog

_setup_lock = Lock()
_setup_done = False

# OTLP body/attribute values only accept: None, bool, int, float, str,
# bytes, and (for body) dicts/lists of those.
_OTLP_PRIMITIVES = (type(None), bool, int, float, str, bytes)


# (key_path, type_qualname) pairs already warned about.  Plain set, not
# WeakSet — elements are (str, str) tuples which aren't weakly referenceable,
# and the actual type objects they represent are held by modules so would
# never be collected anyway.
_coerced_warned: set[tuple[str, str]] = set()


def _coerce_otel_value(val, _key=""):
    """Cast non-OTLP-safe values to str so library log entries don't explode."""
    if isinstance(val, _OTLP_PRIMITIVES):
        return val
    if isinstance(val, dict):
        return {k: _coerce_otel_value(v, f"{_key}.{k}" if _key else k) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_coerce_otel_value(v, f"{_key}[{i}]") for i, v in enumerate(val)]
    type_name = type(val).__qualname__
    pair = (_key, type_name)
    if pair not in _coerced_warned:
        _coerced_warned.add(pair)
        logging.getLogger(__name__).warning("coerced non-OTLP value to str: key=%r type=%s", _key, type_name)
    return str(val)


def setup_structlog(
    level=logging.INFO,
    enable_console_log=True,
    console_level=None,
    console_suppress: tuple[str, ...] | None = None,
    enable_file_log=True,
    file_level=None,
    render_thread_name=False,
):
    """
    Configure structlog to route through stdlib logging,
    which OTel's LoggingHandler picks up for export.
    Must only be called once.
    """
    global _setup_done
    with _setup_lock:
        if _setup_done:
            raise RuntimeError("setup_structlog() must only be called once")
        _setup_done = True

    from opentelemetry._logs import get_logger_provider
    from opentelemetry.sdk._logs import LoggingHandler

    def _add_thread_name(logger, method_name, event_dict):
        record = event_dict.get("_record")
        if record is not None:
            event_dict["thread"] = record.threadName
        else:
            event_dict["thread"] = threading.current_thread().name
        return event_dict

    # Move metadata keys to the end so they render last in console output.
    # With sort_keys=False, ConsoleRenderer preserves dict insertion order.
    _KEYS_LAST = ("thread", "module")

    def _reorder_keys(logger, method_name, event_dict):
        tail = {k: event_dict.pop(k) for k in _KEYS_LAST if k in event_dict}
        event_dict.update(tail)
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _add_thread_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.EventRenamer("message"),
            _reorder_keys,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    root = logging.getLogger()
    root.setLevel(level)

    # Remove the default handler installed by __init__.py.
    root.handlers = [h for h in root.handlers if not getattr(h, "_ihate_work_default", False)]

    # OTel LoggingHandler subclass that normalizes all log records into a
    # consistent dict body before export.  Two problems it solves:
    #
    # 1. Structlog vs stdlib body shape — structlog stores the full event dict
    #    as record.msg (a dict), but third-party libs (urllib3, etc.) emit plain
    #    strings.  Without normalization, the OTLP "message" field has mixed
    #    types (OBJECT vs VARCHAR), which breaks downstream schema assumptions
    #    (e.g. Quickwit field mappings).  The emit() override wraps plain-string
    #    records into the same dict shape structlog produces, enriched with code
    #    location from the LogRecord.
    #
    # 2. Non-primitive extras — structlog's wrap_for_formatter injects _logger
    #    and _name on the LogRecord.  OTel's _get_attributes reads vars(record)
    #    and chokes on these non-primitive values.  The _get_attributes override
    #    strips them without mutating the shared record (other handlers like
    #    ProcessorFormatter still need them).
    _STRUCTLOG_EXTRAS = ("_logger", "_name")

    class _SafeLoggingHandler(LoggingHandler):
        def emit(self, record):
            record = logging.makeLogRecord(vars(record))

            # structlog's wrap_for_formatter stores the event dict as
            # record.msg (a dict).  The OTel SDK passes non-str msg
            # directly as the log body, which the OTLP exporter later
            # serializes asynchronously in BatchLogRecordProcessor.
            # Validate here so failures are synchronous and obvious.
            if isinstance(record.msg, dict):
                record.msg = _coerce_otel_value(record.msg)
            else:
                # Normalize plain stdlib log records (from third-party libs)
                # into the same dict shape structlog produces, so all OTEL
                # log bodies are consistently structured.  Code location is
                # omitted here — it's already captured in OTEL attributes
                # from the LogRecord fields (pathname, funcName, lineno).
                record.msg = {
                    "message": record.getMessage(),
                    "level": record.levelname.lower(),
                    "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                }
                record.args = None

            # OTEL uses record.name as the InstrumentationScope name.
            # For structlog, record.name is "ihate_work.o11y" (the stdlib
            # logger it routes through), not the actual callsite.  Remove
            # "module" from the body and use it as record.name so the
            # callsite appears in scope.name without duplicating the data.
            # Also strip "thread" — it's runtime metadata that belongs in
            # OTEL attributes (added in _get_attributes), not the body.
            # Copy the dict to avoid mutating the shared record.msg that
            # other handlers (console, file) still need.
            if isinstance(record.msg, dict):
                body = dict(record.msg)
                if "module" in body:
                    record.name = body.pop("module")
                body.pop("thread", None)
                record.msg = body

            super().emit(record)

        @staticmethod
        def _get_attributes(record):
            attrs = LoggingHandler._get_attributes(record)
            for key in _STRUCTLOG_EXTRAS:
                attrs.pop(key, None)
            # OTEL semantic conventions: thread identity as attributes.
            attrs["thread.name"] = record.threadName
            attrs["thread.id"] = record.thread
            return {k: _coerce_otel_value(v) for k, v in attrs.items()}

    handler = _SafeLoggingHandler(logger_provider=get_logger_provider())
    root.addHandler(handler)

    # Processor chain for non-structlog (stdlib) log records so they get
    # the same formatting as structlog events on console and file output.
    # Uses "module" (matching structlog's key) instead of add_logger_name's
    # "logger" key, which ConsoleRenderer renders differently.
    def _add_module(logger, method_name, event_dict):
        record = event_dict.get("_record")
        if record is not None:
            event_dict.setdefault("module", record.name)
        return event_dict

    foreign_pre_chain = [
        _add_module,
        structlog.stdlib.add_log_level,
        _add_thread_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.EventRenamer("message"),
        _reorder_keys,
    ]

    # Wrap a renderer so it strips "thread" from the event dict when
    # render_thread_name is off.  Used for both console and file output
    # (local rendering), while OTEL always gets the full event dict.
    def _local_renderer(renderer):
        if render_thread_name:
            return renderer

        def _strip_and_render(logger, method_name, event_dict):
            event_dict.pop("thread", None)
            return renderer(logger, method_name, event_dict)

        return _strip_and_render

    # Pretty-print to console
    if enable_console_log:
        console = logging.StreamHandler()
        console.setLevel(console_level if console_level is not None else level)
        _suppressed = console_suppress if console_suppress is not None else ("sqlalchemy",)
        if _suppressed:
            console.addFilter(lambda record: not record.name.startswith(_suppressed))

        console.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=_local_renderer(structlog.dev.ConsoleRenderer(event_key="message", sort_keys=False)),
                foreign_pre_chain=foreign_pre_chain,
            )
        )
        root.addHandler(console)

    if enable_file_log and (log_dir := getenv("IHATE_WORK_LOG_DIR")):
        _setup_local_log_dir(
            log_dir,
            file_level if file_level is not None else level,
            foreign_pre_chain,
            _local_renderer,
        )


def _setup_local_log_dir(log_dir: str, level: int, foreign_pre_chain: list, local_renderer):
    """
    If $IHATE_WORK_LOG_DIR is set, configure structlog to log to that directory.
    Useful for simpler local dev.
    Log files are named logs-(date).jsonl
    """
    import os
    from datetime import date

    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"log-{date.today().isoformat()}-pid{os.getpid()}.jsonl")

    file_handler = logging.FileHandler(path)
    file_handler.setLevel(level)
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=local_renderer(structlog.processors.JSONRenderer()),
            foreign_pre_chain=foreign_pre_chain,
        )
    )
    logging.getLogger().addHandler(file_handler)
