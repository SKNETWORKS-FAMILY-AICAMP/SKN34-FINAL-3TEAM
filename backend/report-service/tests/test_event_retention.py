"""#208 보존 기간 정리: 발행 완료 outbox·processed_event만 삭제, 미발행·격리 행은 유지."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import insert, select

from app.deletion.service import prune_event_records
from app.deletion.state import processed_event
from app.outbox.repository import outbox_event
from app.worker import serve

NOW = datetime(2026, 11, 2, tzinfo=UTC)
OLD = NOW - timedelta(days=91)


def outbox_row(session, created_at, published_at=None, quarantined_at=None):
    event_id = uuid4()
    session.execute(
        insert(outbox_event).values(
            id=event_id,
            event_type="report.started",
            routing_key="report.started",
            subject=str(uuid4()),
            payload={"synthetic": True},
            created_at=created_at,
            published_at=published_at,
            quarantined_at=quarantined_at,
            failure_count=0,
            manual_retry_count=0,
        )
    )
    return event_id


def processed_row(session, processed_at):
    event_id = uuid4()
    session.execute(
        insert(processed_event).values(
            event_id=event_id, event_type="student.deleted", processed_at=processed_at
        )
    )
    return event_id


def test_prune_keeps_unpublished_quarantined_and_recent_rows(db_session_factory):
    with db_session_factory.begin() as session:
        old_published = outbox_row(session, OLD, published_at=OLD)
        old_pending = outbox_row(session, OLD)
        old_quarantined = outbox_row(session, OLD, quarantined_at=OLD)
        recent_published = outbox_row(session, NOW, published_at=NOW)
        old_processed = processed_row(session, OLD)
        recent_processed = processed_row(session, NOW)

    prune_event_records(db_session_factory, 90, NOW)

    with db_session_factory() as session:
        outbox_ids = set(session.scalars(select(outbox_event.c.id)))
        processed_ids = set(session.scalars(select(processed_event.c.event_id)))
    assert old_published not in outbox_ids
    assert {old_pending, old_quarantined, recent_published} <= outbox_ids
    assert old_processed not in processed_ids and recent_processed in processed_ids


def test_serve_runs_cleanup_and_stops_with_worker():
    async def scenario():
        stop = asyncio.Event()
        calls = []

        async def cleanup():
            calls.append(1)
            stop.set()
            raise RuntimeError("synthetic cleanup failure")  # 실패해도 worker는 정상 종료

        class Consumer:
            async def consume(self, queue, call):
                raise AssertionError("no handlers")

        class Relay:
            async def publish_once(self):
                return False

        async with asyncio.timeout(5):
            await serve(SimpleNamespace(is_connected=True), Consumer(), [], Relay(), stop, cleanup)
        assert calls == [1]

    asyncio.run(scenario())
