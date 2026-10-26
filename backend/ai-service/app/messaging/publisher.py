"""llm.usage.recorded 발행 (아키텍처 1.4·1.6, NFR-PRF-02).

상태 없는 서비스라 best-effort: 응답을 막지 않도록 백그라운드로 보내고,
브로커 미연결·발행 실패는 경고만 남기고 버림 (유실은 Langfuse trace로 보정).
exchange는 definitions.json이 선언하므로 여기서는 선언하지 않음.
"""

import asyncio
import logging
from typing import Any

import aio_pika
from aio_pika.abc import AbstractChannel

from app.llm.base import LlmUsage
from app.messaging.connection import AmqpConnection
from app.messaging.envelope import EventEnvelope
from app.security import current_user_context

logger = logging.getLogger(__name__)

EXCHANGE = "events.topic"
ROUTING_KEY = "llm.usage.recorded"
EVENT_TYPE = "llm.usage.recorded"
SOURCE = "ai-service"
DATASCHEMA = "https://sagomungchi.dev/schemas/events/llm.usage.recorded.v1.schema.json"


def usage_data(usage: LlmUsage) -> dict[str, Any]:
    """contracts/events/llm.usage.recorded.v1.schema.json의 data. 학생 ID·원문·비용 없음."""
    return {
        "service": "ai",
        "callType": usage.call_type,
        "model": usage.model,
        "promptVersion": usage.prompt_version,
        "inputTokens": usage.input_tokens,
        "outputTokens": usage.output_tokens,
        "latencyMs": usage.latency_ms,
        "success": usage.success,
        "errorCode": usage.error_code,
    }


def usage_event(usage: LlmUsage) -> EventEnvelope[dict[str, Any]]:
    context = current_user_context()
    return EventEnvelope(
        type=EVENT_TYPE,
        source=SOURCE,
        dataschema=DATASCHEMA,
        traceparent=context.traceparent if context else None,
        data=usage_data(usage),
    )


class UsagePublisher:
    def __init__(self, amqp: AmqpConnection) -> None:
        self._amqp = amqp
        self._channel: AbstractChannel | None = None
        self._channel_lock = asyncio.Lock()
        self._pending: set[asyncio.Task[None]] = set()

    def record(self, usage: LlmUsage) -> None:
        """LlmClient의 recorder. 요청 컨텍스트에서 봉투를 만들고 발행은 백그라운드로."""
        task = asyncio.get_running_loop().create_task(self._publish(usage_event(usage)))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _publish(self, event: EventEnvelope[dict[str, Any]]) -> None:
        if not self._amqp.is_connected:
            logger.warning("RabbitMQ 미연결, 사용량 이벤트 버림: id=%s", event.id)
            return
        try:
            channel = await self._get_channel()
            exchange = await channel.get_exchange(EXCHANGE, ensure=False)
            await exchange.publish(
                aio_pika.Message(
                    body=event.model_dump_json().encode(),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    message_id=event.id,
                    type=event.type,
                ),
                routing_key=ROUTING_KEY,
            )
        except Exception:  # noqa: BLE001 - best-effort, 발행 실패가 서비스에 번지지 않음
            logger.warning("사용량 이벤트 발행 실패: id=%s", event.id, exc_info=True)

    async def _get_channel(self) -> AbstractChannel:
        async with self._channel_lock:
            if self._channel is None or self._channel.is_closed:
                self._channel = await self._amqp.connection.channel()
            return self._channel

    async def close(self, timeout: float = 2.0) -> None:
        """종료 시 보내던 이벤트를 잠깐 기다림."""
        if self._pending:
            await asyncio.wait(self._pending, timeout=timeout)
