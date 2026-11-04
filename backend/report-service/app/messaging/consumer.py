"""큐 소비: 수동 ACK, 처리 실패 시 지연 재시도 → DLQ (아키텍처 1.6).

- 처리 실패: x-retry-count +1 후 <큐>.retry.<회차>로 재발행(1·5·15분 TTL 만료 시 원래 큐 복귀,
  P12)하고 ACK
- 최대 횟수(= definitions.json 단계 큐 개수) 초과: reject → dlx → <큐>.dlq
- 봉투 형식 오류: 재시도해도 복구되지 않으므로 바로 reject → DLQ
- 큐는 definitions.json에서 선언, 여기서는 존재 확인(passive)만
"""

import logging
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from pydantic import ValidationError

from app import tracing
from app.messaging.connection import AmqpConnection
from app.messaging.contracts import InvalidEvent, ReceivedEnvelope
from app.messaging.envelope import EventEnvelope

logger = logging.getLogger(__name__)

RETRY_COUNT_HEADER = "x-retry-count"

Handler = Callable[[EventEnvelope[dict[str, Any]]], Awaitable[None]]


def _retry_count_attribute(headers: dict[str, Any]) -> int:
    count = headers.get(RETRY_COUNT_HEADER, 0)
    return count if type(count) is int else -1


def _record_failure(span: Span, error: Exception, outcome: str) -> None:
    """Exception type only; messages may hold report content (NFR-PRF-02)."""
    span.set_attribute("messaging.outcome", outcome)
    span.set_attribute("error.type", type(error).__name__)
    span.set_status(Status(StatusCode.ERROR, type(error).__name__))


class Subscription:
    def __init__(self, channel, queue, tag):
        self.channel, self.queue, self.tag = channel, queue, tag

    async def stop(self):
        await self.queue.cancel(self.tag)

    async def close(self):
        await self.channel.close()


class EventConsumer:
    def __init__(self, amqp: AmqpConnection, max_retries: int, prefetch: int) -> None:
        self._amqp = amqp
        self._max_retries = max_retries
        self._prefetch = prefetch

    async def consume(self, queue_name: str, handler: Handler) -> Subscription:
        channel = await self._amqp.connection.channel()
        try:
            await channel.set_qos(prefetch_count=self._prefetch)
            queue = await channel.get_queue(queue_name, ensure=True)
            tag = await queue.consume(partial(self.handle_message, channel, queue_name, handler))
            return Subscription(channel, queue, tag)
        except BaseException:
            await channel.close()
            raise

    async def handle_message(
        self,
        channel: AbstractChannel,
        queue_name: str,
        handler: Handler,
        message: AbstractIncomingMessage,
    ) -> None:
        try:
            envelope = ReceivedEnvelope.model_validate_json(message.body)
        except ValidationError:
            logger.error(
                "봉투 형식 오류, DLQ 이동: queue=%s, messageId=%s", queue_name, message.message_id
            )
            await message.reject(requeue=False)
            return

        # 봉투 traceparent를 부모로 소비 span을 열고, 하위 호출·결과 이벤트에는 이 span을 전달한다
        with tracing.tracer.start_as_current_span(
            f"{queue_name} process",
            context=tracing.parent_context(envelope.traceparent),
            kind=SpanKind.CONSUMER,
            attributes={
                "messaging.system": "rabbitmq",
                "messaging.destination.name": queue_name,
                "messaging.message.id": envelope.id,
                "messaging.rabbitmq.retry_count": _retry_count_attribute(message.headers),
            },
        ) as span:
            traced = tracing.current_traceparent()
            if traced:
                envelope = envelope.model_copy(update={"traceparent": traced})
            await self._handle(channel, queue_name, handler, message, envelope, span)

    async def _handle(self, channel, queue_name, handler, message, envelope, span) -> None:
        try:
            await handler(envelope)
        except InvalidEvent as error:
            logger.warning("메시지 계약 오류, DLQ 이동: queue=%s, id=%s", queue_name, envelope.id)
            _record_failure(span, error, "dlq")
            await message.reject(requeue=False)
            return
        except Exception as error:
            retry_count = message.headers.get(RETRY_COUNT_HEADER, 0)
            if type(retry_count) is not int or retry_count < 0:
                _record_failure(span, error, "dlq")
                await message.reject(requeue=False)
                return
            if retry_count >= self._max_retries:
                logger.error("메시지 처리 실패, DLQ 이동: queue=%s, id=%s", queue_name, envelope.id)
                _record_failure(span, error, "dlq")
                await message.reject(requeue=False)
                return
            _record_failure(span, error, "retry")
            logger.warning(
                "메시지 처리 실패, 재시도 %s회차: queue=%s, id=%s",
                retry_count + 1,
                queue_name,
                envelope.id,
            )
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=message.body,
                    headers={**message.headers, RETRY_COUNT_HEADER: retry_count + 1},
                    content_type=message.content_type,
                    message_id=message.message_id,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=f"{queue_name}.retry.{retry_count + 1}",
            )
        await message.ack()
