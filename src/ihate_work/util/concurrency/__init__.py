"""Concurrency utilities."""

from ihate_work.util.concurrency.recycling_pool import RecyclingPool
from ihate_work.util.concurrency.recycling_pool2 import RecyclingPool2
from ihate_work.util.concurrency.workers import run_in_workers, wait_pending
from ihate_work.util.meta import create_optional_getattr

__all__ = [
    "LokyExecutor",
    "RecyclingPool",
    "RecyclingPool2",
    "run_in_workers",
    "wait_pending",
]

__getattr__ = create_optional_getattr(
    __name__,
    [
        ("LokyExecutor", "ihate_work.util.concurrency.loky_executor", "loky"),
    ],
)
