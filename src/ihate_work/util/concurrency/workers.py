import concurrent.futures as cf
import math
import os
from collections.abc import Callable, Iterator
from typing import Any

import ihate_work.o11y as o11y

logger, *_ = o11y.get_o11y(__name__)

_default_num_worker = math.floor(os.cpu_count() / 3)


def wait_pending(
    all_futures: list[cf.Future],
    pending: set[cf.Future],
    target: int,
    *,
    raise_on_exception=True,
) -> set[cf.Future]:
    """wait until len(pending_tasks) <= target"""
    while len(pending) > target:
        done, pending = cf.wait(pending, timeout=10, return_when=cf.FIRST_COMPLETED)
        if raise_on_exception:
            for f in done:
                f.result()
        logger.debug("%d/%d task pending", len(pending), len(all_futures))
    return pending


def run_in_workers(
    create_tasks: Callable[[cf.Executor], Iterator[cf.Future[Any]]],
    *,
    raise_on_exception=True,
    num_worker=_default_num_worker,
    task_queue_length: int | None = None,
) -> list[cf.Future]:
    all_futures = []
    if not task_queue_length:
        task_queue_length = 2 * num_worker
    with cf.ProcessPoolExecutor(max_workers=num_worker) as executor:
        pending = set()
        for new_task in create_tasks(executor):
            if new_task is None:
                pending = wait_pending(
                    all_futures, pending, 0, raise_on_exception=raise_on_exception
                )
                continue
            pending.add(new_task)
            all_futures.append(new_task)
            pending = wait_pending(
                all_futures,
                pending,
                task_queue_length,
                raise_on_exception=raise_on_exception,
            )
    pending = wait_pending(
        all_futures, pending, 0, raise_on_exception=raise_on_exception
    )
    return all_futures
