"""Real #42 wire messages through production consumer/relay and disposable DB/broker."""

import asyncio
import json
from pathlib import Path

import aio_pika
import pytest

from app.generation.codec import ReportV1Codec
from app.generation.consumer import GENERATE_QUEUE, GenerationConsumer
from app.generation.locking import JobLocks
from app.generation.service import GenerationService
from app.messaging.connection import AmqpConnection
from app.messaging.consumer import EventConsumer
from app.messaging.publisher import EventPublisher
from app.outbox.relay import OutboxRelay
from app.worker import serve
from tests.report_helpers import EmptyGenerator
from tests.test_generation import stored
from tests.test_outbox_broker import rabbit_url  # noqa: F401
from tests.test_report_codec import validate_contract, wire


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("narrative_enabled", [False, True])
def test_worker_duplicate_command_and_real_lifecycle_events(
    request, report_factory, db_engine, report_student_id, failure, narrative_enabled
):
    broker_url = request.getfixturevalue("rabbit_url")
    body = wire(report_student_id)
    body["data"]["narrativeEnabled"] = narrative_enabled
    validate_contract(body)
    received_commands = []

    class Generator(EmptyGenerator):
        async def generate(self, command, report):
            received_commands.append(command)
            result = await super().generate(command, report)
            if failure:
                raise RuntimeError("synthetic private error must not be emitted")
            return result

    generator, codec = Generator(), ReportV1Codec()
    handler = GenerationConsumer(
        GenerationService(report_factory, JobLocks(db_engine), generator, codec), codec
    )

    async def scenario():
        amqp = AmqpConnection(broker_url)
        publisher = EventPublisher(amqp)
        amqp.start()
        stop, worker = asyncio.Event(), None
        try:
            async with asyncio.timeout(15):
                while not amqp.is_connected:
                    await asyncio.sleep(0.05)
            channel = await amqp.connection.channel(publisher_confirms=True)
            # Read topology declarations from the team's file; only test setup declares them.
            root = Path(__file__).resolve().parents[3]
            config = json.loads(
                (
                    root
                    / "infrastructure/gitops/charts/platform-data/files/rabbitmq/definitions.json"
                ).read_text()
            )
            queue_definition = next(q for q in config["queues"] if q["name"] == GENERATE_QUEUE)
            command_exchange = await channel.declare_exchange("cmd.direct", "direct", durable=True)
            events = await channel.declare_exchange("events.topic", "topic", durable=True)
            await channel.declare_exchange("dlx", "direct", durable=True)
            commands = await channel.declare_queue(
                GENERATE_QUEUE,
                durable=queue_definition["durable"],
                arguments=queue_definition["arguments"],
            )
            await commands.bind(command_exchange, "report.generate")
            sink = await channel.declare_queue(exclusive=True)
            await sink.bind(events, "report.*")
            worker = asyncio.create_task(
                serve(
                    amqp,
                    EventConsumer(amqp, 3, 1),
                    [(GENERATE_QUEUE, handler)],
                    OutboxRelay(report_factory, publisher),
                    stop,
                )
            )
            for _ in range(2):
                await command_exchange.publish(
                    aio_pika.Message(
                        json.dumps(body).encode(),
                        content_type="application/json",
                        message_id=body["id"],
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key="report.generate",
                    mandatory=True,
                )
            received = []
            async with asyncio.timeout(20):
                while len(received) < 2:
                    message = await sink.get(fail=False)
                    if message is None:
                        await asyncio.sleep(0.05)
                        continue
                    value = json.loads(message.body)
                    validate_contract(value)
                    received.append(value)
                    await message.ack()
            stop.set()
            await worker
            assert {event["type"] for event in received} == {
                "report.started",
                "report.failed" if failure else "report.completed",
            }
            assert len({event["id"] for event in received}) == 2
            assert all(event["data"]["jobId"] == body["data"]["jobId"] for event in received)
            await commands.delete(if_unused=False, if_empty=False)
            await channel.close()
        finally:
            stop.set()
            if worker is not None:
                await worker
            await publisher.close()
            await amqp.close()

    asyncio.run(scenario())
    reports, events = stored(report_factory, report_student_id)
    assert generator.calls == 1 and len(reports) == 1 and len(events) == 2
    assert reports[0]["status"] == ("FAILED" if failure else "COMPLETED")
    assert received_commands[0].narrative_enabled is narrative_enabled
    assert generator.contexts[0].role == "SYSTEM"
    assert generator.contexts[0].student_scope == frozenset({str(report_student_id)})
    assert all(event["published_at"] is not None for event in events)
