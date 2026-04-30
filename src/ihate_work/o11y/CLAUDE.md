# ihate_work.o11y

Unified observability package for all Python subprojects in this monorepo.
Combines OpenTelemetry SDK (traces, metrics, logs) with structlog for structured logging.
Handles both our own code (structlog) and third-party library code (stdlib logging) through a single pipeline.

## Goals

1. **Single setup, consistent output** — call `setup_otel()` + `setup_structlog()` once at startup; every log/trace/metric from any module flows through the same pipeline.
2. **OTEL-native** — all signals export via OTLP. Log bodies are always dicts (never bare strings) so downstream schemas (Quickwit field mappings) stay consistent.
3. **Third-party library compatibility** — stdlib `logging.getLogger()` records from libraries (urllib3, sqlalchemy, etc.) are captured and normalized into the same dict shape as structlog events.
4. **Separation of concerns** — local rendering (console/file) is independent of OTEL export. Data lands in the right OTEL layer: callsite kwargs in body, runtime metadata (thread name) in attributes, module identity in scope.

## Architecture

### The three logging worlds

Python has three independent logging systems that all need to coexist:

| System | Who uses it | Record format |
|--------|------------|---------------|
| **stdlib `logging`** | Third-party libraries (urllib3, httpx, sqlalchemy, etc.) | `LogRecord` with printf-style message |
| **structlog** | Our application code | Event dict (Python dict with keyword args) |
| **OTEL SDK** | Export pipeline | `LogData` with body + attributes + resource |

This package bridges all three.

### Log flow

```
Our code                        Third-party libs
    |                                |
    v                                v
structlog processors            stdlib logging.getLogger()
    |                                |
    v                                |
wrap_for_formatter                   |
    |                                |
    v                                v
  stdlib LogRecord (msg=dict)    stdlib LogRecord (msg=string)
    |         |         |            |         |         |
    v         v         v            v         v         v
  OTEL     Console    File(JSONL)  OTEL     Console    File(JSONL)
handler   handler    handler      handler   handler    handler
```

All three handlers receive the same `LogRecord`. Each processes it differently:

- **OTEL handler** (`_SafeLoggingHandler`): normalizes `record.msg` to a dict, extracts `module` into `scope.name`, strips `thread` from body (moved to attributes as `thread.name`/`thread.id`), coerces non-OTLP-safe values, exports via OTLP.
- **Console handler**: runs through `ProcessorFormatter` → `ConsoleRenderer` for pretty terminal output. Thread name stripped unless `render_thread_name=True`.
- **File handler**: runs through `ProcessorFormatter` → `JSONRenderer` for JSONL files. Same `render_thread_name` control as console.

### Key design: body normalization

The `_SafeLoggingHandler.emit()` ensures every OTEL log body is a dict with at minimum `{message, level, timestamp}`:

- **structlog records**: `record.msg` is already a dict (from `wrap_for_formatter`). Passed through `_coerce_otel_value()` to ensure OTLP-safe types.
- **stdlib records**: `record.msg` is a string. Wrapped into `{message: str, level: str, timestamp: iso}` to match.
- **module → scope.name**: the `module` key is popped from the body and set as `record.name`, so OTEL uses it as `InstrumentationScope.name` without duplication.
- **thread → attributes**: the `thread` key is stripped from the body. Thread identity is added as OTEL attributes (`thread.name`, `thread.id`) per semantic conventions.

### Key design: foreign_pre_chain

stdlib log records don't go through structlog's processor chain. The `foreign_pre_chain` on `ProcessorFormatter` adds the same fields (log level, timestamp, module name, thread name) so they render identically on console and in file output.

## Modules

### `__init__.py` — public API + pre-setup defaults

Exports: `setup_otel`, `setup_structlog`, `get_o11y`.

On import, installs a minimal structlog config + default console handler so logs emitted *before* `setup_structlog()` are visible. The default handler is tagged with `_ihate_work_default = True` so `setup_structlog()` can find and remove it.

Also calls `setup_library_logging()` to silence noisy third-party loggers.

### `otel.py` — OTEL provider setup

`setup_otel(fallback_to_console=False)`: configures `TracerProvider`, `MeterProvider`, `LoggerProvider` with either OTLP/HTTP exporters (when `OTEL_EXPORTER_OTLP_ENDPOINT` is set) or console exporters (when fallback enabled).

### `structlog.py` — structlog + handler wiring

`setup_structlog(...)`: the main wiring function. Configures:

1. **structlog processor chain**: `merge_contextvars → add_log_level → add_thread_name → timestamp → rename_event → reorder_keys → wrap_for_formatter`
2. **OTEL handler** (`_SafeLoggingHandler`): subclass that normalizes bodies and coerces attribute types.
3. **Console handler**: `ProcessorFormatter` + `ConsoleRenderer`. Thread name stripped before rendering unless `render_thread_name=True`.
4. **File handler**: `ProcessorFormatter` + `JSONRenderer`, writes to `$IHATE_WORK_LOG_DIR` if set.

Parameters:
- `level` — root logger level (default `INFO`)
- `enable_console_log` / `console_level` — console handler toggle and level override
- `console_suppress` — tuple of logger name prefixes to filter from console (default: `("sqlalchemy",)`)
- `enable_file_log` / `file_level` — file handler toggle and level override
- `render_thread_name` — show thread name in local output: console and file (default `False`); thread identity is always exported to OTEL as attributes (`thread.name`, `thread.id`)

### `defaults.py` — library log level defaults

Silences noisy libraries:
- **INFO**: httpcore, sqlalchemy, PIL, sse_starlette, watchfiles, urllib3, multipart
- **WARN**: httpx, elastic_transport.transport, LiteLLM

### `_coerce_otel_value()` — type safety for OTLP

Recursively coerces non-primitive values to `str` before OTLP export. Warns once per (key_path, type) pair. Prevents `BatchLogRecordProcessor` from failing asynchronously on unexpected types.

## Usage

```python
# Once at startup (entrypoint / __main__.py)
import ihate_work.o11y as o11y
o11y.setup_otel()
o11y.setup_structlog()

# Per module
from ihate_work.o11y import get_o11y
logger, tracer, meter = get_o11y(__name__)

logger.info("importing", entity="subjects", count=1000)

with tracer.start_as_current_span("build_index"):
    ...
```

## OTEL log record shape

```
body (message):
  {
    "message": "importing",
    "level": "info",
    "timestamp": "2026-04-20T14:41:34.703208Z",
    "entity": "subjects",
    "count": 1000
  }

attributes:
  thread.name = "ThreadPoolExecutor-3_1"
  thread.id   = 140234567890
  code.filepath = "/.../storage.py"
  code.function = "import_entities"
  code.lineno   = 86

scope.name: "ihate_work.domains.bgm_archive.backend.duck.storage"
```

Body contains only callsite data (developer kwargs). Runtime metadata (`thread.*`, `code.*`) lives in attributes. Module identity is in `scope.name`.

## Environment variables

| Variable | Effect |
|----------|--------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Enables OTLP export (e.g. `http://localhost:4318`) |
| `OTEL_SERVICE_NAME` | Service name in OTEL resource attributes |
| `IHATE_WORK_LOG_DIR` | Enables local JSONL file logging |
