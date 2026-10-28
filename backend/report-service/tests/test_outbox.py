import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pamqp.commands import Basic
from sqlalchemy import select, text

from app.database import transaction
from app.messaging.envelope import EventEnvelope
from app.messaging.publisher import EventPublisher
from app.outbox.relay import OutboxRelay
from app.outbox.repository import OutboxRepository, PendingEvent, outbox_event


def seed(factory, student_id):
    envelope = EventEnvelope(
        type="test.synthetic",
        source="report-service",
        subject=str(student_id),
        dataschema="test.synthetic.v1",
        data={"synthetic": "직접 만든 테스트"},
    )
    with transaction(factory) as session:
        OutboxRepository().add(session, envelope)
    return envelope


def rows(factory):
    with factory() as session:
        return session.execute(select(outbox_event)).mappings().all()


def test_confirm_precedes_published_timestamp(report_factory, report_student_id):
    envelope = seed(report_factory, report_student_id)
    delivered = []

    class Publisher:
        async def publish(self, event):
            assert rows(report_factory)[0]["published_at"] is None
            with report_factory() as session:
                assert (
                    session.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname=current_database() "
                            "AND pid<>pg_backend_pid() AND state LIKE 'idle in transaction%'"
                        )
                    )
                    == 0
                )
            delivered.append(event)

    async def scenario():
        relay = OutboxRelay(report_factory, Publisher())
        assert await relay.publish_once()
        assert not await relay.publish_once()

    asyncio.run(scenario())
    assert rows(report_factory)[0]["published_at"] is not None
    assert len(delivered) == 1 and str(delivered[0].id) == envelope.id
    assert delivered[0].payload["data"] == envelope.data


def test_publication_failure_keeps_row_for_retry(report_factory, report_student_id):
    seed(report_factory, report_student_id)
    publisher = AsyncMock()
    publisher.publish.side_effect = ConnectionError("synthetic broker failure")
    with pytest.raises(ConnectionError):
        asyncio.run(OutboxRelay(report_factory, publisher).publish_once())
    assert rows(report_factory)[0]["published_at"] is None


def test_publish_timeout_keeps_row_for_retry(report_factory, report_student_id):
    seed(report_factory, report_student_id)

    class Publisher:
        async def publish(self, event):
            await asyncio.Event().wait()

    with pytest.raises(TimeoutError):
        asyncio.run(OutboxRelay(report_factory, Publisher(), timeout=0.05).publish_once())
    assert rows(report_factory)[0]["published_at"] is None


def test_mark_failure_replays_same_event_identity(report_factory, report_student_id):
    seed(report_factory, report_student_id)

    class BrokenMark(OutboxRepository):
        def mark_published(self, session, event_id):
            super().mark_published(session, event_id)
            raise RuntimeError("synthetic crash after confirm")

    publisher = AsyncMock()
    with pytest.raises(RuntimeError, match="after confirm"):
        asyncio.run(OutboxRelay(report_factory, publisher, repository=BrokenMark()).publish_once())
    assert rows(report_factory)[0]["published_at"] is None
    asyncio.run(OutboxRelay(report_factory, publisher).publish_once())
    first, second = [call.args[0] for call in publisher.publish.call_args_list]
    assert first.id == second.id and first.payload == second.payload


def test_two_relays_do_not_publish_one_locked_row_twice(report_factory, report_student_id):
    seed(report_factory, report_student_id)

    async def scenario():
        entered, finish = asyncio.Event(), asyncio.Event()
        published = []

        class Publisher:
            async def publish(self, event):
                published.append(event.id)
                entered.set()
                await finish.wait()

        relay = OutboxRelay(report_factory, Publisher())
        first = asyncio.create_task(relay.publish_once())
        try:
            await asyncio.wait_for(entered.wait(), 5)
            assert not await relay.publish_once()
        finally:
            finish.set()
            assert await first
        assert len(published) == 1

    asyncio.run(scenario())


def pending():
    event_id = uuid4()
    return PendingEvent(event_id, "test.synthetic", {"id": str(event_id), "data": {"test": True}})


def test_cancelled_publication_releases_claim(report_factory, report_student_id):
    seed(report_factory, report_student_id)

    async def scenario():
        entered = asyncio.Event()

        class Stalled:
            async def publish(self, event):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(OutboxRelay(report_factory, Stalled()).publish_once())
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await OutboxRelay(report_factory, AsyncMock()).publish_once()

    asyncio.run(scenario())


class FakeAmqp:
    def __init__(self, confirmation):
        self.is_connected = True
        self.exchange = AsyncMock()
        self.exchange.publish.return_value = confirmation
        self.channel = AsyncMock()
        self.channel.is_closed = False
        self.channel.get_exchange.return_value = self.exchange
        self.connection = AsyncMock()
        self.connection.channel.return_value = self.channel


def test_publisher_requests_confirm_and_detects_unroutable_messages():
    amqp = FakeAmqp(Basic.Ack())
    event = pending()
    asyncio.run(EventPublisher(amqp).publish(event))
    amqp.connection.channel.assert_awaited_once_with(publisher_confirms=True, on_return_raises=True)
    amqp.channel.get_exchange.assert_awaited_once_with("events.topic", ensure=True)
    call = amqp.exchange.publish.call_args
    assert call.kwargs["mandatory"] is True
    assert call.kwargs["routing_key"] == event.routing_key
    assert call.args[0].message_id == str(event.id)
    assert call.args[0].delivery_mode == 2


@pytest.mark.parametrize("confirmation", [None, Basic.Nack(), Basic.Reject()])
def test_publisher_rejects_missing_or_negative_confirm(confirmation):
    with pytest.raises(RuntimeError, match="did not confirm"):
        asyncio.run(EventPublisher(FakeAmqp(confirmation)).publish(pending()))


def test_publisher_propagates_broker_errors():
    amqp = FakeAmqp(None)
    amqp.exchange.publish.side_effect = ConnectionError("synthetic broker error")
    with pytest.raises(ConnectionError):
        asyncio.run(EventPublisher(amqp).publish(pending()))


def test_publisher_does_not_silently_drop_disconnected_event():
    amqp = FakeAmqp(None)
    amqp.is_connected = False
    with pytest.raises(ConnectionError, match="disconnected"):
        asyncio.run(EventPublisher(amqp).publish(pending()))
    amqp.exchange.publish.assert_not_awaited()
