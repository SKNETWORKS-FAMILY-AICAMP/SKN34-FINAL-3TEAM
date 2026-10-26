import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from app import security
from app.llm.base import LlmUsage
from app.messaging.publisher import (
    DATASCHEMA,
    EXCHANGE,
    ROUTING_KEY,
    UsagePublisher,
    usage_data,
    usage_event,
)
from app.security import UserContext, bind_user_context

SCHEMA_PATH = (
    Path(__file__).resolve().parents[4] / "contracts/events/llm.usage.recorded.v1.schema.json"
)
VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))

SUCCESS = LlmUsage("JUDGMENT", "claude-sonnet-5-5", "judge@2", 1200, 150, 2300, True, None)
FAILURE = LlmUsage(
    "FOLLOWUP", "claude-sonnet-5-5", "followup@4", None, None, 266, False, "LLM_AUTH_FAILED"
)


@pytest.mark.parametrize("usage", [SUCCESS, FAILURE])
def test_event_data_matches_contract_schema(usage: LlmUsage) -> None:
    # 완료 조건: 사용량 이벤트가 contracts/events 스키마와 일치
    errors = list(VALIDATOR.iter_errors(usage_data(usage)))
    assert errors == []


def test_contract_rejects_unknown_field() -> None:
    # 계약 테스트가 실제로 검사하는지 확인 (학생 ID 같은 필드가 끼면 실패)
    assert list(VALIDATOR.iter_errors({**usage_data(SUCCESS), "studentId": "s1"}))


def test_envelope_has_no_student_subject_and_carries_trace() -> None:
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    token = bind_user_context(UserContext("u1", "SYSTEM", frozenset({"s1"}), traceparent))
    try:
        event = usage_event(SUCCESS)
    finally:
        security._current.reset(token)
    assert (event.type, event.source, event.dataschema) == (
        "llm.usage.recorded",
        "ai-service",
        DATASCHEMA,
    )
    assert event.subject is None  # 학생 ID 미포함 (NFR-PRF-02)
    assert event.traceparent == traceparent
    assert "s1" not in event.model_dump_json()


class FakeExchange:
    def __init__(self) -> None:
        self.published: list[tuple[Any, str]] = []

    async def publish(self, message: Any, routing_key: str) -> None:
        self.published.append((message, routing_key))


class FakeChannel:
    def __init__(self) -> None:
        self.exchange = FakeExchange()
        self.is_closed = False
        self.requested: list[tuple[str, bool]] = []

    async def get_exchange(self, name: str, ensure: bool = True) -> FakeExchange:
        self.requested.append((name, ensure))
        return self.exchange


class FakeConnection:
    def __init__(self, channel: FakeChannel) -> None:
        self._channel = channel

    async def channel(self) -> FakeChannel:
        return self._channel


class FakeAmqp:
    """AmqpConnection 대역: is_connected·connection만 사용."""

    def __init__(self, connected: bool) -> None:
        self.is_connected = connected
        self.channel = FakeChannel()
        self.connection = FakeConnection(self.channel)


def make_publisher(connected: bool) -> tuple[UsagePublisher, FakeAmqp]:
    amqp = FakeAmqp(connected)
    return UsagePublisher(amqp), amqp  # type: ignore[arg-type]


def test_publishes_to_events_topic_in_background() -> None:
    publisher, amqp = make_publisher(connected=True)

    async def run() -> None:
        publisher.record(SUCCESS)  # 동기 호출, 응답을 막지 않음
        await publisher.close()

    asyncio.run(run())
    [(message, routing_key)] = amqp.channel.exchange.published
    assert routing_key == ROUTING_KEY
    assert amqp.channel.requested == [(EXCHANGE, False)]  # exchange는 선언하지 않음
    body = json.loads(message.body)
    assert body["type"] == "llm.usage.recorded"
    assert list(VALIDATOR.iter_errors(body["data"])) == []
    assert message.message_id == body["id"]


def test_disconnected_broker_drops_event_without_error(caplog: pytest.LogCaptureFixture) -> None:
    publisher, amqp = make_publisher(connected=False)

    async def run() -> None:
        publisher.record(SUCCESS)
        await publisher.close()

    with caplog.at_level("WARNING"):
        asyncio.run(run())
    assert amqp.channel.exchange.published == []
    assert "RabbitMQ 미연결" in caplog.text
