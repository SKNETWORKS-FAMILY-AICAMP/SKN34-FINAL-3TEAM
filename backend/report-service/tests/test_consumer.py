import asyncio
import json
from typing import Any

from app.messaging.connection import AmqpConnection
from app.messaging.consumer import RETRY_COUNT_HEADER, EventConsumer
from app.messaging.envelope import EventEnvelope

QUEUE = "report.report.generate"


class FakeMessage:
    def __init__(self, body: bytes, headers: dict[str, Any] | None = None) -> None:
        self.body = body
        self.headers = headers or {}
        self.content_type = "application/json"
        self.message_id = "m1"
        self.acked = False
        self.rejected = False

    async def ack(self) -> None:
        self.acked = True

    async def reject(self, requeue: bool = False) -> None:
        assert requeue is False
        self.rejected = True


class FakeExchange:
    def __init__(self) -> None:
        self.published: list[tuple[Any, str]] = []

    async def publish(self, message: Any, routing_key: str) -> None:
        self.published.append((message, routing_key))


class FakeChannel:
    def __init__(self) -> None:
        self.default_exchange = FakeExchange()


def envelope_body() -> bytes:
    envelope = EventEnvelope[dict[str, str]](
        type="report.generate", source="core-service", dataschema="report.generate.v1", data={}
    )
    return envelope.model_dump_json().encode()


def run(message: FakeMessage, handler: Any, max_retries: int = 2) -> FakeChannel:
    channel = FakeChannel()
    consumer = EventConsumer(AmqpConnection("amqp://unused"), max_retries=max_retries, prefetch=1)
    asyncio.run(consumer.handle_message(channel, QUEUE, handler, message))  # type: ignore[arg-type]
    return channel


async def ok(_: EventEnvelope[dict[str, Any]]) -> None:
    return None


async def fail(_: EventEnvelope[dict[str, Any]]) -> None:
    raise RuntimeError("처리 실패")


def test_success_acks() -> None:
    message = FakeMessage(envelope_body())
    channel = run(message, ok)
    assert message.acked and not message.rejected
    assert channel.default_exchange.published == []


def test_failure_republishes_to_retry_queue_with_count() -> None:
    message = FakeMessage(envelope_body(), {RETRY_COUNT_HEADER: 1})
    channel = run(message, fail)

    [(retry, routing_key)] = channel.default_exchange.published
    assert routing_key == f"{QUEUE}.retry.2"
    assert retry.headers[RETRY_COUNT_HEADER] == 2
    assert json.loads(retry.body) == json.loads(message.body)
    assert message.acked and not message.rejected


def test_failure_over_max_retries_rejects_to_dlq() -> None:
    message = FakeMessage(envelope_body(), {RETRY_COUNT_HEADER: 2})
    channel = run(message, fail)
    assert message.rejected and not message.acked
    assert channel.default_exchange.published == []


def test_malformed_envelope_rejects_without_retry() -> None:
    called = False

    async def handler(_: EventEnvelope[dict[str, Any]]) -> None:
        nonlocal called
        called = True

    message = FakeMessage(b"not-json")
    channel = run(message, handler)
    assert message.rejected and not called
    assert channel.default_exchange.published == []


def test_core_jackson_envelope_is_accepted() -> None:
    # core(Jackson) 출력 형식: 나노초·오프셋 시각, null traceparent
    body = (
        b'{"id":"8f1c2a8e-1111-4c1e-9d3b-123456789abc","specversion":"1.0",'
        b'"type":"report.generate","source":"core-service",'
        b'"time":"2026-10-26T14:00:00.123456789+09:00","subject":"student-1",'
        b'"dataschema":"report.generate.v1","traceparent":null,"data":{"jobId":"j1"}}'
    )
    received: list[EventEnvelope[dict[str, Any]]] = []

    async def handler(envelope: EventEnvelope[dict[str, Any]]) -> None:
        received.append(envelope)

    message = FakeMessage(body)
    run(message, handler)

    [envelope] = received
    assert envelope.subject == "student-1" and envelope.data == {"jobId": "j1"}
    assert envelope.time.utcoffset() is not None
    assert message.acked
