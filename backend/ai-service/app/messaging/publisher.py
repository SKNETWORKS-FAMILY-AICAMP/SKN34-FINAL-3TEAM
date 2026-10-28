"""이벤트 발행: events.topic, best-effort (아키텍처 1.6).

상태 없는 서비스라 Outbox 없이 처리 결과 반환 후 발행, 실패해도 예외를 올리지 않음.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Literal

import aio_pika
from aio_pika.abc import AbstractChannel
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.messaging.connection import AmqpConnection
from app.messaging.envelope import EventEnvelope

logger = logging.getLogger(__name__)

EVENTS_EXCHANGE = "events.topic"
LLM_USAGE_RECORDED = "llm.usage.recorded"

CallType = Literal["JUDGMENT", "FOLLOWUP", "ANALYSIS", "REPORT_NARRATIVE", "M2", "M1"]


class EventPublisher:
    def __init__(self, amqp: AmqpConnection) -> None:
        self._amqp = amqp
        self._channel: AbstractChannel | None = None

    async def publish(self, envelope: EventEnvelope[Any], routing_key: str) -> bool:
        if not self._amqp.is_connected:
            logger.warning("RabbitMQ 미연결, 이벤트 미발행: %s %s", routing_key, envelope.id)
            return False
        try:
            if self._channel is None or self._channel.is_closed:
                self._channel = await self._amqp.connection.channel()  # publisher confirm 기본 사용
            exchange = await self._channel.get_exchange(EVENTS_EXCHANGE, ensure=False)
            await exchange.publish(
                aio_pika.Message(
                    body=envelope.model_dump_json(by_alias=True).encode(),
                    content_type="application/json",
                    message_id=envelope.id,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=routing_key,
            )
            return True
        except Exception as exc:  # noqa: BLE001 - best-effort, 호출 흐름에 영향 없음
            logger.warning("이벤트 발행 실패: %s %s: %s", routing_key, envelope.id, exc)
            return False


class LlmUsageRecorded(BaseModel):
    """contracts/events/llm.usage.recorded.v1.schema.json. 학생 ID·원문 미포함 (NFR-PRF-02)"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    service: Literal["ai", "scoring"]
    call_type: CallType
    model: str
    prompt_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int
    success: bool
    error_code: str | None = None
    occurred_at: datetime


class UsagePublisher:
    def __init__(self, publisher: EventPublisher, service: Literal["ai", "scoring"], source: str):
        self._publisher = publisher
        self._service = service
        self._source = source

    async def publish(
        self,
        call_type: CallType,
        model: str,
        *,
        input_tokens: int | None,
        output_tokens: int | None,
        latency_ms: int,
        success: bool,
        prompt_version: str | None = None,
        error_code: str | None = None,
    ) -> bool:
        envelope = EventEnvelope[LlmUsageRecorded](
            type=LLM_USAGE_RECORDED,
            source=self._source,
            dataschema=f"{LLM_USAGE_RECORDED}.v1",
            data=LlmUsageRecorded(
                service=self._service,
                call_type=call_type,
                model=model,
                prompt_version=prompt_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                success=success,
                error_code=error_code,
                occurred_at=datetime.now(UTC),
            ),
        )
        return await self._publisher.publish(envelope, LLM_USAGE_RECORDED)
