# ihate_work.util.perf

Performance measurement, profiling, and diagnostics utilities.

## Modules

### `rater.py` — Throughput tracker

Immutable `Rater` class that tracks (count, timestamp) pairs. Call `.tick(n)` to record progress, read `.rate` (instant), `.avg_rate` (overall), `.total`, `.elapsed`.

### `mem_profiler.py` — Object-level memory profiling (pympler)

Lazy-imports pympler. Call `setup_mem_profiler()` once (raises `ImportError` if pympler not installed), then `report_memory_usage()` to print object type/size summary.

### `mem_dump.py` — Allocation dump on signal (tracemalloc)

`setup_mem_dump_on_signal(signals=(SIGTERM,), nframes=5)` — starts tracemalloc and registers signal handlers. On signal, dumps top allocation sites (file:line) to stderr. Designed for earlyoom SIGTERM; also useful with SIGUSR1 for on-demand dumps.

## Import

```python
from ihate_work.util.perf import Rater
from ihate_work.util.perf import setup_mem_profiler, report_memory_usage
from ihate_work.util.perf import setup_mem_dump_on_signal
```

## Design notes

- **pympler is lazy**: `import ihate_work.util.perf` does NOT import pympler. The `ImportError` only fires when `setup_mem_profiler()` is called — fail at setup, not at import.
- **Re-exports**: `ihate_work.util.rater` and `ihate_work.util.mem_profiler` still work as thin re-exports. New code should import from `ihate_work.util.perf`.
