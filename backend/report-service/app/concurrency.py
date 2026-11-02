"""Finish blocking work before cancellation releases job/student guards."""

import asyncio
import contextlib
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def run_blocking(operation: Callable[[], T]) -> T:
    task = asyncio.create_task(asyncio.to_thread(operation))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            await task
        raise
