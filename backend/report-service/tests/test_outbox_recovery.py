"""#131: 실제 PostgreSQL의 학생별 순서·백오프·격리·운영 재처리."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update

from app.database import transaction
from app.outbox import manage
from app.outbox.relay import OutboxRelay
from app.outbox.repository import OutboxRepository, outbox_event
from tests.test_outbox import rows, seed


def test_backoff_blocks_only_same_student_then_quarantines_and_manual_retry_preserves_identity(
    report_factory, report_student_id, report_students, caplog
):
    first, second = seed(report_factory, report_student_id), seed(report_factory, report_student_id)
    other_student = uuid4()
    report_students.add(other_student)
    third = seed(report_factory, other_student)
    now = [datetime.now(UTC)]
    repository = OutboxRepository(lambda: now[0])
    sent = []

    class Publisher:
        fail = True

        async def publish(self, event):
            if str(event.id) == first.id and self.fail:
                raise ConnectionError("PRIVATE_CREDENTIAL_DO_NOT_STORE")
            sent.append(event)

    publisher = Publisher()

    async def scenario():
        relay = OutboxRelay(report_factory, publisher, repository=repository)
        for attempt, delay in enumerate((60, 300, 900, None), 1):
            failed_at = now[0]
            with pytest.raises(ConnectionError):
                await relay.publish_once()
            with report_factory() as session:
                item = (
                    session.execute(select(outbox_event).where(outbox_event.c.id == UUID(first.id)))
                    .mappings()
                    .one()
                )
            assert item["failure_count"] == attempt
            assert item["last_error_code"] == "BROKER_UNAVAILABLE"
            if attempt == 1:
                assert await relay.publish_once()  # 다른 학생은 즉시 처리.
                assert [str(x.id) for x in sent] == [third.id]
            assert not await relay.publish_once()  # 같은 학생의 뒤 이벤트도 대기.
            if delay is not None:
                assert item["next_attempt_at"] == failed_at + timedelta(seconds=delay)
                now[0] = item["next_attempt_at"] - timedelta(microseconds=1)
                assert not await relay.publish_once()
                now[0] += timedelta(microseconds=1)
            else:
                assert item["quarantined_at"] == failed_at and item["next_attempt_at"] is None
                now[0] += timedelta(days=1)
                assert not await relay.publish_once()
        with transaction(report_factory) as session:
            assert len(repository.quarantined(session)) == 1
            assert repository.requeue(session, UUID(first.id))
            assert not repository.requeue(session, UUID(first.id))
        publisher.fail = False
        assert await relay.publish_once()
        assert await relay.publish_once()
        assert not await relay.publish_once()

    asyncio.run(scenario())
    assert [str(x.id) for x in sent] == [third.id, first.id, second.id]
    replayed = sent[1]
    assert replayed.payload == first.model_dump(mode="json")
    with report_factory() as session:
        item = (
            session.execute(select(outbox_event).where(outbox_event.c.id == UUID(first.id)))
            .mappings()
            .one()
        )
    assert item["manual_retry_count"] == 1 and item["last_requeued_at"] is not None
    assert item["failure_count"] == 0 and item["published_at"] is not None
    assert "PRIVATE_CREDENTIAL" not in str(item) + caplog.text
    assert "quarantined" in caplog.text


def test_two_relays_cannot_overtake_same_student_but_can_publish_other_student(
    report_factory, report_student_id, report_students
):
    first, second = seed(report_factory, report_student_id), seed(report_factory, report_student_id)
    other = uuid4()
    report_students.add(other)
    third = seed(report_factory, other)

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        published = []

        class Publisher:
            async def publish(self, event):
                if str(event.id) == first.id:
                    entered.set()
                    await release.wait()
                published.append(str(event.id))

        relay = OutboxRelay(report_factory, Publisher())
        task = asyncio.create_task(relay.publish_once())
        try:
            await asyncio.wait_for(entered.wait(), 10)
            assert await OutboxRelay(report_factory, Publisher()).publish_once()
            assert published == [third.id]
            assert not await relay.publish_once()
        finally:
            release.set()
            await task
        assert await relay.publish_once()
        assert published == [third.id, first.id, second.id]

    asyncio.run(scenario())


def test_more_than_candidate_limit_failed_rows_cannot_hide_other_student(
    report_factory, report_student_id, report_students
):
    blocked = [seed(report_factory, report_student_id) for _ in range(105)]
    with transaction(report_factory) as session:
        session.execute(
            update(outbox_event)
            .where(outbox_event.c.id == UUID(blocked[0].id))
            .values(
                failure_count=4, quarantined_at=datetime.now(UTC), last_error_code="PUBLISH_FAILED"
            )
        )
    other = uuid4()
    report_students.add(other)
    healthy = seed(report_factory, other)
    publisher = AsyncMock()
    assert asyncio.run(OutboxRelay(report_factory, publisher).publish_once())
    assert str(publisher.publish.call_args.args[0].id) == healthy.id


def test_enqueue_order_uses_short_transaction_lock_not_network_publish_lock(
    report_factory, db_engine, report_student_id
):
    first = seed(report_factory, report_student_id)
    claim = OutboxRepository().claim_next(db_engine)
    assert str(claim.event.id) == first.id
    try:
        # 발행 선점이 살아 있어도 생성 상태의 Outbox 저장은 대기하지 않는다.
        with ThreadPoolExecutor(max_workers=1) as pool:
            second = pool.submit(seed, report_factory, report_student_id).result(timeout=5)
        assert second.id != first.id
    finally:
        claim.close()


def test_uncommitted_enqueue_cannot_be_overtaken_by_second_producer(
    report_factory, report_student_id
):
    from app.messaging.envelope import EventEnvelope

    inserted, release, second_done = threading.Event(), threading.Event(), threading.Event()
    first = EventEnvelope(
        type="test.synthetic",
        source="report-service",
        subject=str(report_student_id),
        dataschema="test.synthetic.v1",
        data={"step": 1},
    )
    second = first.model_copy(update={"id": str(uuid4()), "data": {"step": 2}})

    def enqueue(envelope, hold=False):
        with transaction(report_factory) as session:
            OutboxRepository().add(session, envelope)
            if hold:
                inserted.set()
                assert release.wait(10)
        if not hold:
            second_done.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(enqueue, first, True)
        assert inserted.wait(5)
        two = pool.submit(enqueue, second)
        try:
            assert not second_done.wait(0.2)
            assert not asyncio.run(OutboxRelay(report_factory, AsyncMock()).publish_once())
        finally:
            release.set()
        one.result(timeout=10)
        two.result(timeout=10)
    publisher = AsyncMock()
    relay = OutboxRelay(report_factory, publisher)
    asyncio.run(relay.publish_once())
    asyncio.run(relay.publish_once())
    assert [str(x.args[0].id) for x in publisher.publish.call_args_list] == [first.id, second.id]


def test_failure_record_is_atomic_and_deleted_event_is_not_recreated(
    report_factory, report_student_id
):
    event = seed(report_factory, report_student_id)
    repository = OutboxRepository()
    with pytest.raises(RuntimeError):
        with transaction(report_factory) as session:
            repository.record_failure(session, UUID(event.id), "PUBLISH_FAILED")
            raise RuntimeError("synthetic transaction rollback")
    assert rows(report_factory)[0]["failure_count"] == 0
    with transaction(report_factory) as session:
        session.execute(delete(outbox_event).where(outbox_event.c.id == UUID(event.id)))
    with transaction(report_factory) as session:
        assert repository.record_failure(session, UUID(event.id), "PUBLISH_FAILED") is None
        assert not repository.requeue(session, UUID(event.id))
    assert rows(report_factory) == []


def test_operator_cli_lists_no_payload_and_requeues_once(
    report_factory, db_engine, report_student_id, monkeypatch, capsys
):
    event = seed(report_factory, report_student_id)
    with transaction(report_factory) as session:
        session.execute(
            update(outbox_event)
            .where(outbox_event.c.id == UUID(event.id))
            .values(
                failure_count=4, quarantined_at=datetime.now(UTC), last_error_code="PUBLISH_FAILED"
            )
        )
    monkeypatch.setattr(manage, "create_db_engine", lambda: db_engine)
    assert manage.main(["list"]) == 0
    text_out = capsys.readouterr().out
    assert event.id in text_out and "직접 만든 테스트" not in text_out
    assert manage.main(["requeue", event.id]) == 0
    assert manage.main(["requeue", event.id]) == 2
    assert manage.main(["requeue", str(uuid4())]) == 2
