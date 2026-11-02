"""Shared deletion wire through real RabbitMQ/Postgres/MinIO; core completion is a stub."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import aio_pika
from sqlalchemy import delete

from app.deletion.consumer import DELETION_QUEUE, StudentDeletedConsumer
from app.deletion.service import DeletionService
from app.deletion.state import DeleteStudent, processed_event
from app.generation.locking import JobLocks
from app.messaging.connection import AmqpConnection
from app.messaging.consumer import EventConsumer
from tests.test_deletion import Core, envelope
from tests.test_generation import stored
from tests.test_minio_storage import (  # noqa: F401
    generate,
    keys,
    minio_endpoint,
    minio_storage,
)
from tests.test_outbox_broker import rabbit_url  # noqa: F401
from tests.test_rendering import FakeRenderer
from tests.test_report_codec import validate_contract


def test_deletion_retry_and_duplicate_on_real_broker_and_storage(
    request, report_factory, db_engine, report_student_id, report_students
):
    storage, admin = request.getfixturevalue("minio_storage")
    broker = request.getfixturevalue("rabbit_url")
    other = uuid4()
    report_students.add(other)
    for student in (report_student_id, other):
        generate(report_factory, db_engine, student, storage, FakeRenderer())
    other_keys = keys(admin, f"reports/{other}/")
    command = DeleteStudent(uuid4(), report_student_id, uuid4(), "RECORDS", datetime.now(UTC))
    body = envelope(command).model_dump(mode="json")
    validate_contract(body)
    core = Core()

    class FailOnce:
        calls = 0

        def delete_prefix(self, prefix):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("Injected first deletion outage")
            storage.delete_prefix(prefix)

    guarded_storage = FailOnce()
    handler = StudentDeletedConsumer(
        DeletionService(report_factory, JobLocks(db_engine), lambda: guarded_storage, core)
    )

    async def scenario():
        amqp, subscription = AmqpConnection(broker), None
        amqp.start()
        try:
            async with asyncio.timeout(15):
                while not amqp.is_connected:
                    await asyncio.sleep(0.05)
            channel = await amqp.connection.channel(publisher_confirms=True)
            root = Path(__file__).resolve().parents[3]
            topology = json.loads(
                (
                    root
                    / "infrastructure/gitops/charts/platform-data/files/rabbitmq/definitions.json"
                ).read_text()
            )
            events = await channel.declare_exchange("events.topic", "topic", durable=True)
            await channel.declare_exchange("dlx", "direct", durable=True)
            queues = {}
            for definition in topology["queues"]:
                if definition["name"] in (DELETION_QUEUE, DELETION_QUEUE + ".retry.1"):
                    queues[definition["name"]] = await channel.declare_queue(
                        definition["name"],
                        durable=definition["durable"],
                        arguments=definition["arguments"],
                    )
            await queues[DELETION_QUEUE].bind(events, "student.deleted")
            subscription = await EventConsumer(amqp, 3, 1).consume(DELETION_QUEUE, handler)
            await events.publish(
                aio_pika.Message(json.dumps(body).encode(), content_type="application/json"),
                routing_key="student.deleted",
                mandatory=True,
            )
            async with asyncio.timeout(20):
                while True:
                    retry = await queues[DELETION_QUEUE + ".retry.1"].get(fail=False)
                    if retry is not None:
                        break
                    await asyncio.sleep(0.05)
            assert retry.headers["x-retry-count"] == 1
            assert json.loads(retry.body) == body
            assert len(stored(report_factory, report_student_id)[0]) == 1
            assert len(keys(admin, f"reports/{report_student_id}/")) == 6
            assert not core.calls
            # Consume the real retry queue, then redeliver immediately rather than wait its 1m TTL.
            for _ in range(2):
                await events.publish(
                    aio_pika.Message(
                        retry.body, headers=retry.headers, content_type="application/json"
                    ),
                    routing_key="student.deleted",
                    mandatory=True,
                )
            await retry.ack()
            async with asyncio.timeout(20):
                while len(core.calls) < 2:
                    await asyncio.sleep(0.05)
            await subscription.stop()
            assert core.calls == [command.request_id, command.request_id]
            assert guarded_storage.calls == 2  # one failure, one physical deletion
            assert stored(report_factory, report_student_id) == ([], [])
            assert not keys(admin, f"reports/{report_student_id}/")
            assert keys(admin, f"reports/{other}/") == other_keys
            assert len(stored(report_factory, other)[0]) == 1
            await channel.close()
        finally:
            if subscription is not None:
                await subscription.close()
            await amqp.close()

    try:
        asyncio.run(scenario())
    finally:
        with report_factory.begin() as session:
            session.execute(
                delete(processed_event).where(processed_event.c.event_id == command.event_id)
            )
