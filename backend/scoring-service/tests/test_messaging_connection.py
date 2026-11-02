"""#140: 외부 브로커 없이 연결 복구·중지·robust 연결 상태를 직접 검사한다."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.messaging import connection


def broker():
    connected = asyncio.Event()
    connected.set()
    return SimpleNamespace(is_closed=False, connected=connected, close=AsyncMock())


def test_initial_failure_recovers_and_robust_disconnect_changes_readiness(monkeypatch, caplog):
    async def scenario():
        live = broker()
        connect = AsyncMock(side_effect=[ConnectionError("PRIVATE_PASSWORD_URL"), live])
        monkeypatch.setattr(connection.aio_pika, "connect_robust", connect)
        amqp = connection.AmqpConnection("amqp://synthetic", retry_interval=0.001)
        assert not amqp.is_connected
        with pytest.raises(RuntimeError, match="미연결"):
            _ = amqp.connection
        amqp.start()
        await asyncio.wait_for(amqp._task, 2)
        assert amqp.is_connected and amqp.connection is live
        assert connect.await_count == 2
        assert all(
            x.kwargs == {"timeout": connection.CONNECT_TIMEOUT} for x in connect.await_args_list
        )
        live.connected.clear()
        assert not amqp.is_connected
        live.connected.set()  # 재접속은 aio-pika robust connection이 담당한다.
        assert amqp.is_connected
        live.is_closed = True
        assert not amqp.is_connected
        await amqp.close()
        live.close.assert_awaited_once()

    asyncio.run(scenario())
    assert "ConnectionError" in caplog.text and "PRIVATE_PASSWORD_URL" not in caplog.text


def test_shutdown_interrupts_retry_delay_without_another_connection_attempt(monkeypatch):
    async def scenario():
        attempted = asyncio.Event()

        async def fail(*args, **kwargs):
            attempted.set()
            raise ConnectionError("synthetic")

        connect = AsyncMock(side_effect=fail)
        monkeypatch.setattr(connection.aio_pika, "connect_robust", connect)
        amqp = connection.AmqpConnection("amqp://synthetic", retry_interval=60)
        amqp.start()
        await asyncio.wait_for(attempted.wait(), 2)
        await asyncio.wait_for(amqp.close(), 2)
        assert amqp._task.done() and not amqp._task.cancelled()
        assert connect.await_count == 1 and not amqp.is_connected

    asyncio.run(scenario())


def test_shutdown_during_connect_waits_then_closes_the_returned_connection(monkeypatch):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        live = broker()

        async def connect(*args, **kwargs):
            entered.set()
            await release.wait()
            return live

        monkeypatch.setattr(connection.aio_pika, "connect_robust", connect)
        amqp = connection.AmqpConnection("amqp://synthetic")
        amqp.start()
        await entered.wait()
        closing = asyncio.create_task(amqp.close())
        await asyncio.sleep(0)
        assert not closing.done()
        release.set()
        await asyncio.wait_for(closing, 2)
        assert not amqp._task.cancelled()
        live.close.assert_awaited_once()

    asyncio.run(scenario())


def test_close_before_start_does_not_connect(monkeypatch):
    connect = AsyncMock()
    monkeypatch.setattr(connection.aio_pika, "connect_robust", connect)
    asyncio.run(connection.AmqpConnection("amqp://synthetic").close())
    connect.assert_not_called()
