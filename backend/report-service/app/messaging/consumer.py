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
from pydantic import ValidationError

from app.messaging.connection import AmqpConnection
from app.messaging.contracts import InvalidEvent, ReceivedEnvelope
from app.messaging.envelope import EventEnvelope

logger = logging.getLogger(__name__)

RETRY_COUNT_HEADER = "x-retry-count"

Handler = Callable[[EventEnvelope[dict[str, Any]]], Awaitable[None]]


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

        try:
            await handler(envelope)
        except InvalidEvent:
            logger.warning("메시지 계약 오류, DLQ 이동: queue=%s, id=%s", queue_name, envelope.id)
            await message.reject(requeue=False)
            return
        except Exception:
            retry_count = message.headers.get(RETRY_COUNT_HEADER, 0)
            if type(retry_count) is not int or retry_count < 0:
                await message.reject(requeue=False)
                return
            if retry_count >= self._max_retries:
                logger.error("메시지 처리 실패, DLQ 이동: queue=%s, id=%s", queue_name, envelope.id)
                await message.reject(requeue=False)
                return
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
