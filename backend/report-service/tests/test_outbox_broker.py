"""Transport integration only; synthetic events do not claim #42 contract compatibility."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import aio_pika
import pytest
from aio_pika.exceptions import DeliveryError
from sqlalchemy import select
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from app.database import transaction
from app.messaging.connection import AmqpConnection
from app.messaging.envelope import EventEnvelope
from app.messaging.publisher import EventPublisher
from app.outbox.relay import OutboxRelay
from app.outbox.repository import OutboxRepository, outbox_event
from tests.test_outbox import rows, seed
from tests.test_report_codec import validate_contract


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
            now = [datetime.now(UTC)]
            relay = OutboxRelay(
                report_factory, publisher, repository=OutboxRepository(lambda: now[0])
            )
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
            assert not await relay.publish_once()  # 지연 시간이 지나기 전에는 발행하지 않음.
            now[0] += timedelta(minutes=1)
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


def test_poison_stream_does_not_block_other_student_and_real_broker_manual_replay(
    rabbit_url, report_factory, report_student_id, report_students
):
    other = uuid4()
    report_students.add(other)
    job, report = str(uuid4()), str(uuid4())

    def event(kind, student, job_id, report_id):
        return EventEnvelope(
            type=kind,
            source="report-service",
            subject=str(student),
            dataschema=kind + ".v1",
            data={"jobId": job_id, "studentId": str(student), "reportId": report_id},
        )

    poison = event("report.started", report_student_id, job, report)
    following = event("report.completed", report_student_id, job, report)
    healthy = event("report.completed", other, str(uuid4()), str(uuid4()))
    for envelope in (poison, following, healthy):
        validate_contract(envelope.model_dump(mode="json"))
        with transaction(report_factory) as session:
            OutboxRepository().add(session, envelope)

    async def scenario():
        amqp = AmqpConnection(rabbit_url)
        publisher = EventPublisher(amqp)
        amqp.start()
        try:
            async with asyncio.timeout(15):
                while not amqp.is_connected:
                    await asyncio.sleep(0.05)
            channel = await amqp.connection.channel()
            exchange = await channel.declare_exchange("events.topic", aio_pika.ExchangeType.TOPIC)
            sink = await channel.declare_queue(exclusive=True)
            await sink.bind(exchange, "report.completed")
            now = [datetime.now(UTC)]
            repository = OutboxRepository(lambda: now[0])
            relay = OutboxRelay(report_factory, publisher, repository=repository)
            for index, delay in enumerate((60, 300, 900, None)):
                with pytest.raises(DeliveryError):
                    await relay.publish_once()  # 실제 mandatory return.
                if index == 0:
                    assert await relay.publish_once()
                    message = await sink.get(timeout=5)
                    assert message.message_id == healthy.id
                    await message.ack()
                assert not await relay.publish_once()
                if delay is not None:
                    now[0] += timedelta(seconds=delay)
            with report_factory() as session:
                row = (
                    session.execute(
                        select(outbox_event).where(outbox_event.c.id == UUID(poison.id))
                    )
                    .mappings()
                    .one()
                )
                assert row["failure_count"] == 4 and row["quarantined_at"] is not None
            await sink.bind(exchange, "report.started")
            with transaction(report_factory) as session:
                assert repository.requeue(session, UUID(poison.id))
            for expected in (poison, following):
                assert await relay.publish_once()
                message = await sink.get(timeout=5)
                assert message.message_id == expected.id
                body = json.loads(message.body)
                assert body == expected.model_dump(mode="json")
                validate_contract(body)
                await message.ack()
            assert not await relay.publish_once()
            await channel.close()
        finally:
            await publisher.close()
            await amqp.close()

    asyncio.run(scenario())
