import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from pamqp.commands import Basic

from app import tracing
from app.messaging.consumer import RETRY_COUNT_HEADER
from app.messaging.envelope import EventEnvelope
from app.messaging.publisher import EventPublisher
from app.outbox.repository import PendingEvent
from tests.test_consumer import QUEUE, FakeMessage, run

PARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"


@pytest.fixture
def spans(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # A local provider keeps other tests on the no-op API.
    monkeypatch.setattr(tracing, "tracer", provider.get_tracer("test"))
    yield exporter
    provider.shutdown()


def body(traceparent: str | None) -> bytes:
    return (
        EventEnvelope[dict[str, str]](
            type="report.generate",
            source="core-service",
            dataschema="report.generate.v1",
            traceparent=traceparent,
            data={},
        )
        .model_dump_json()
        .encode()
    )


def test_consumer_span_continues_the_envelope_trace_and_hands_its_own_context_down(spans):
    received: list[EventEnvelope[dict[str, Any]]] = []

    async def handler(envelope: EventEnvelope[dict[str, Any]]) -> None:
        received.append(envelope)

    message = FakeMessage(body(PARENT))
    run(message, handler)

    [span] = spans.get_finished_spans()
    assert span.context.trace_id == int("0af7651916cd43dd8448eb211c80319c", 16)
    assert span.parent.span_id == int("b7ad6b7169203331", 16)
    assert span.attributes["messaging.destination.name"] == QUEUE
    [envelope] = received
    assert envelope.traceparent == f"00-{span.context.trace_id:032x}-{span.context.span_id:016x}-01"
    assert message.acked


@pytest.mark.parametrize(("retries", "outcome"), [(0, "retry"), (2, "dlq")])
def test_failed_handling_marks_the_span_without_the_error_message(spans, retries, outcome):
    async def fail(_: EventEnvelope[dict[str, Any]]) -> None:
        raise RuntimeError("student report text must not reach the span")

    run(FakeMessage(body(PARENT), {RETRY_COUNT_HEADER: retries}), fail)

    [span] = spans.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["messaging.outcome"] == outcome
    assert span.attributes["error.type"] == "RuntimeError"
    recorded = json.dumps(dict(span.attributes)) + str(span.status.description)
    assert "student report text" not in recorded
    assert not span.events


def test_without_a_parent_the_consumer_starts_a_new_trace(spans):
    run(FakeMessage(body("00-analysis-trace")), lambda _: asyncio.sleep(0))
    [span] = spans.get_finished_spans()
    assert span.parent is None


def test_without_an_sdk_the_received_traceparent_passes_through_unchanged():
    received: list[str | None] = []

    async def handler(envelope: EventEnvelope[dict[str, Any]]) -> None:
        received.append(envelope.traceparent)

    run(FakeMessage(body(PARENT)), handler)
    assert received == [PARENT]


class FakeExchange:
    def __init__(self):
        self.messages = []

    async def publish(self, message, **_):
        self.messages.append(message)
        return Basic.Ack()


class FakeChannel:
    is_closed = False

    def __init__(self):
        self.exchange = FakeExchange()

    async def get_exchange(self, *_, **__):
        return self.exchange


class FakeAmqp:
    is_connected = True


@pytest.mark.parametrize("traceparent", [PARENT, None])
def test_published_events_carry_the_envelope_trace_as_an_amqp_header(traceparent):
    publisher = EventPublisher(FakeAmqp())  # type: ignore[arg-type]
    channel = FakeChannel()
    publisher._channel = channel  # type: ignore[assignment]
    event = PendingEvent(
        id=uuid4(), routing_key="report.generated", payload={"traceparent": traceparent, "data": {}}
    )
    asyncio.run(publisher.publish(event))
    [message] = channel.exchange.messages
    assert (message.headers or {}).get("traceparent") == traceparent
