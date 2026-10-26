import asyncio
import json
from pathlib import Path
from typing import Any

from app.messaging.connection import AmqpConnection
from app.messaging.envelope import EventEnvelope
from app.messaging.publisher import EventPublisher, UsagePublisher

CONTRACT = Path(__file__).parents[3] / "contracts/events/llm.usage.recorded.v1.schema.json"


class CapturingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.sent: list[tuple[dict[str, Any], str]] = []

    async def publish(self, envelope: EventEnvelope[Any], routing_key: str) -> bool:
        self.sent.append((json.loads(envelope.model_dump_json(by_alias=True)), routing_key))
        return True


def test_usage_envelope_matches_contract() -> None:
    capturing = CapturingPublisher()
    usage = UsagePublisher(capturing, service="ai", source="ai-service")

    asyncio.run(
        usage.publish(
            "JUDGMENT",
            "test-model",
            input_tokens=10,
            output_tokens=20,
            latency_ms=300,
            success=True,
        )
    )

    [(body, routing_key)] = capturing.sent
    schema = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert routing_key == "llm.usage.recorded"
    assert body["type"] == "llm.usage.recorded"
    assert body["dataschema"] == "llm.usage.recorded.v1"
    assert set(schema["required"]) <= body["data"].keys() <= schema["properties"].keys()
    assert body["data"]["callType"] == "JUDGMENT"


def test_publish_without_connection_returns_false() -> None:
    publisher = EventPublisher(AmqpConnection("amqp://guest:guest@127.0.0.1:1/"))
    envelope = EventEnvelope[dict[str, str]](type="t", source="s", dataschema="t.v1", data={})

    assert asyncio.run(publisher.publish(envelope, "t")) is False
