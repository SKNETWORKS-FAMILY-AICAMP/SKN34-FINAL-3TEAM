import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from app.llm.base import LlmUsage
from app.messaging.envelope import EventEnvelope
from app.messaging.publisher import EventPublisher, UsagePublisher
from app.messaging.usage_recorder import BackgroundUsageRecorder

CONTRACTS = Path(__file__).resolve().parents[4] / "contracts/events"


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((CONTRACTS / name).read_text(encoding="utf-8")))


DATA = validator("llm.usage.recorded.v1.schema.json")
ENVELOPE = validator("envelope.schema.json")

SUCCESS = LlmUsage("JUDGMENT", "claude-sonnet-5-5", "judge@2", 1200, 150, 2300, True, None)
FAILURE = LlmUsage(
    "FOLLOWUP", "claude-sonnet-5-5", "followup@4", None, None, 266, False, "LLM_AUTH_FAILED"
)


class CapturingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.sent: list[tuple[dict[str, Any], str]] = []

    async def publish(self, envelope: EventEnvelope[Any], routing_key: str) -> bool:
        self.sent.append((json.loads(envelope.model_dump_json(by_alias=True)), routing_key))
        return True


def record(*usages: LlmUsage) -> list[tuple[dict[str, Any], str]]:
    capturing = CapturingPublisher()
    recorder = BackgroundUsageRecorder(UsagePublisher(capturing, service="ai", source="ai-service"))

    async def run() -> None:
        for usage in usages:
            recorder(usage)  # 동기 호출, 응답을 막지 않음
        await recorder.close()

    asyncio.run(run())
    return capturing.sent


@pytest.mark.parametrize("usage", [SUCCESS, FAILURE])
def test_llm_usage_becomes_contract_valid_event(usage: LlmUsage) -> None:
    # 완료 조건: 사용량 이벤트가 contracts/events 스키마와 일치 (봉투·data 모두)
    [(body, routing_key)] = record(usage)
    assert routing_key == "llm.usage.recorded"
    assert list(ENVELOPE.iter_errors(body)) == []
    assert list(DATA.iter_errors(body["data"])) == []
    assert body["subject"] is None  # 학생 ID 미포함 (NFR-PRF-02)
    data = body["data"]
    assert (data["service"], data["callType"], data["promptVersion"], data["errorCode"]) == (
        "ai",
        usage.call_type,
        usage.prompt_version,
        usage.error_code,
    )
    assert (data["inputTokens"], data["outputTokens"], data["latencyMs"]) == (
        usage.input_tokens,
        usage.output_tokens,
        usage.latency_ms,
    )


def test_each_llm_request_is_one_event() -> None:
    assert len(record(SUCCESS, FAILURE)) == 2


def test_publish_error_is_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    class BrokenPublisher(UsagePublisher):
        async def publish(self, *args: Any, **kwargs: Any) -> bool:
            raise RuntimeError("broker down")

    recorder = BackgroundUsageRecorder(BrokenPublisher(CapturingPublisher(), "ai", "ai-service"))

    async def run() -> None:
        recorder(SUCCESS)
        await recorder.close()

    with caplog.at_level("WARNING"):
        asyncio.run(run())
    assert "사용량 이벤트 발행 실패" in caplog.text
