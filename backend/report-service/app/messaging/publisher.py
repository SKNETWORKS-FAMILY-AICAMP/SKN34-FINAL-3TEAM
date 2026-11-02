"""Confirmed Outbox publication; failures propagate so the DB row remains unpublished."""

import json

import aio_pika
from aio_pika.abc import AbstractChannel
from pamqp.commands import Basic

from app.messaging.connection import AmqpConnection
from app.outbox.repository import PendingEvent


class EventPublisher:
    def __init__(self, amqp: AmqpConnection, timeout: float = 10.0) -> None:
        self._amqp = amqp
        self._timeout = timeout
        self._channel: AbstractChannel | None = None

    async def publish(self, event: PendingEvent) -> None:
        if not self._amqp.is_connected:
            raise ConnectionError("RabbitMQ is disconnected")
        if self._channel is None or self._channel.is_closed:
            self._channel = await self._amqp.connection.channel(
                publisher_confirms=True, on_return_raises=True
            )
        # Topology belongs to definitions.json, never declare it here.
        exchange = await self._channel.get_exchange("events.topic", ensure=True)
        confirmation = await exchange.publish(
            aio_pika.Message(
                body=json.dumps(event.payload, ensure_ascii=False).encode("utf-8"),
                content_type="application/json",
                message_id=str(event.id),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=event.routing_key,
            mandatory=True,
            timeout=self._timeout,
        )
        if not isinstance(confirmation, Basic.Ack):
            raise RuntimeError("RabbitMQ did not confirm the event")

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
