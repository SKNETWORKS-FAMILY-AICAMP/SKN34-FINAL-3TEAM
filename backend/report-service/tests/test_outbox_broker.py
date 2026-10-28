"""Transport integration only; synthetic events do not claim #42 contract compatibility."""

import asyncio
import json

import aio_pika
import pytest
from aio_pika.exceptions import DeliveryError
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from app.messaging.connection import AmqpConnection
from app.messaging.publisher import EventPublisher
from app.outbox.relay import OutboxRelay
from tests.test_outbox import rows, seed


@pytest.fixture(scope="module")
def rabbit_url():
    container = (
        DockerContainer("rabbitmq:4.3.7-management-alpine")
        .with_env("RABBITMQ_DEFAULT_USER", "synthetic")
        .with_env("RABBITMQ_DEFAULT_PASS", "synthetic")
        .with_exposed_ports(5672)
        .waiting_for(LogMessageWaitStrategy("Server startup complete"))
    )
    with container:
        host, port = container.get_container_host_ip(), container.get_exposed_port(5672)
        yield f"amqp://synthetic:synthetic@{host}:{port}/"


def test_real_broker_confirm_and_unroutable_retry(rabbit_url, report_factory, report_student_id):
    first = seed(report_factory, report_student_id)

    async def scenario():
        amqp = AmqpConnection(rabbit_url)
        publisher = EventPublisher(amqp)
        amqp.start()
        try:
            async with asyncio.timeout(15):
                while not amqp.is_connected:
                    await asyncio.sleep(0.05)
            channel = await amqp.connection.channel()
            # Only test setup declares this isolated broker's topology.
            exchange = await channel.declare_exchange("events.topic", aio_pika.ExchangeType.TOPIC)
            queue = await channel.declare_queue(exclusive=True)
            await queue.bind(exchange, "test.synthetic")
            relay = OutboxRelay(report_factory, publisher)
            assert await relay.publish_once()
            received = await queue.get(timeout=5)
            assert received.message_id == first.id
            assert json.loads(received.body)["data"] == first.data
            await received.ack()
            assert rows(report_factory)[0]["published_at"] is not None

            await queue.unbind(exchange, "test.synthetic")
            second = seed(report_factory, report_student_id)
            with pytest.raises(DeliveryError):
                await relay.publish_once()
            unpublished = [r for r in rows(report_factory) if r["published_at"] is None]
            assert len(unpublished) == 1 and str(unpublished[0]["id"]) == second.id

            await queue.bind(exchange, "test.synthetic")
            assert await relay.publish_once()
            received = await queue.get(timeout=5)
            assert received.message_id == second.id
            await received.ack()
            assert all(r["published_at"] is not None for r in rows(report_factory))
            await channel.close()
        finally:
            await publisher.close()
            await amqp.close()

    asyncio.run(scenario())
