import asyncio
import threading

import pytest

from app.concurrency import run_blocking


@pytest.mark.parametrize("operation_failure", [False, True])
def test_cancellation_waits_for_thread_before_releasing_caller_guard(operation_failure):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    guard_released = []

    def operation():
        entered.set()
        assert release.wait(5)
        finished.set()
        if operation_failure:
            raise RuntimeError("synthetic late thread error")

    async def guarded():
        try:
            await run_blocking(operation)
        finally:
            guard_released.append(finished.is_set())

    async def scenario():
        task = asyncio.create_task(guarded())
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and guard_released == []
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(scenario())
    finally:
        release.set()
    assert guard_released == [True]


def test_blocking_success_and_error_propagate_without_cancellation():
    assert asyncio.run(run_blocking(lambda: 42)) == 42

    def fail():
        raise RuntimeError("synthetic operation error")

    with pytest.raises(RuntimeError, match="synthetic operation"):
        asyncio.run(run_blocking(fail))
