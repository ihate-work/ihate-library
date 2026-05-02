# ihate_library

Shared Python library under the `ihate_work.*` namespace. Extracted from [vibra](../main/) monorepo's `_shared/py-local/`.

## Modules

### `o11y` — Observability (structlog + OpenTelemetry)

Unified logging, tracing, and metrics. See `src/ihate_work/o11y/CLAUDE.md` for architecture details.

```python
import ihate_work.o11y as o11y

o11y.setup_otel()
o11y.setup_structlog()
logger, tracer, meter = o11y.get_o11y(__name__)
```

### `bootstrap` — Import-time setup (dotenv, log defaults)

### `storage` — DB wrappers (DuckDB, PostgreSQL)

Requires optional deps: `pip install local-ihate-work[storage]`

### `llm` — LLM client wrappers

- `llm/langchain` — LangChain embeddings, SQLite cache
- `llm/litellm` — LiteLLM chat/embedding, Langfuse observability
- `llm/llm_clients` — Bare API clients (Claude, Gemini)

Requires optional deps: `pip install local-ihate-work[llm]` or `[llm-langchain]`

### `util` — General utilities

- `util/meta` — `create_redirection_getattr` for PEP 562 deprecation shims
- `util/perf` — Throughput tracker, memory profiling
- `util/concurrency` — Worker pools, recycling pools
- `util/iter` — Iterator utilities
- `util/text_cleaner` — HTML/text sanitization (requires `[text]` extra)
- `util/nlp` — CJK variant mapping
- `util/prefix_counter`, `util/uniq_by`, `util/versatile` — Misc helpers

## Dependency management

```sh
make setup       # create venv + install core deps + editable package
make test        # run pytest
make lint        # run ruff
```

Optional extras: `storage`, `llm`, `llm-langchain`, `text`, `perf`

## Coding rules

Inherited from vibra conventions:

- **o11y**: Use `ihate_work.o11y` exclusively (not stdlib `logging.getLogger()`). structlog uses keyword args, not printf-style. `setup_otel()` / `setup_structlog()` called exactly once at entry point.
- **Data models**: Pydantic `BaseModel` by default for structured records. Keyword args only.
- **No mutable globals**: Wire deps through constructor args or framework DI.
- **Tests**: Named `TESTEE_test.py`. Run with `make test`.
- **dotenv**: Always `load_dotenv(override=False)`.
- **Moving APIs**: Use `create_redirection_getattr` for PEP 562 deprecation shims. Re-export shared symbols from `__init__.py`.
