"""Persist full envelopes in the caller's transaction; never commit from a repository."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import blake2b
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    exists,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Session

from app.messaging.envelope import EventEnvelope

metadata = MetaData()
outbox_event = Table(
    "outbox_event",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("event_type", String, nullable=False),
    Column("routing_key", String, nullable=False),
    Column("subject", String, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("failure_count", Integer, nullable=False),
    Column("next_attempt_at", DateTime(timezone=True)),
    Column("last_error_code", String(64)),
    Column("last_failed_at", DateTime(timezone=True)),
    Column("quarantined_at", DateTime(timezone=True)),
    Column("manual_retry_count", Integer, nullable=False),
    Column("last_requeued_at", DateTime(timezone=True)),
)

RETRY_DELAYS = (60, 300, 900)  # 최초 시도 + 지연 재시도 3회, 이후 격리.


def subject_key(subject: str, action: str = "publish") -> int:
    return int.from_bytes(
        blake2b(f"report-outbox-{action}:{subject}".encode(), digest_size=8).digest(),
        "big",
        signed=True,
    )


@dataclass(frozen=True)
class PendingEvent:
    id: UUID
    routing_key: str
    payload: dict[str, Any]


class OutboxClaim:
    def __init__(self, connection, key, event):
        self.connection, self.key, self.event = connection, key, event

    def close(self):
        try:
            self.connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self.key})
        except BaseException:
            self.connection.invalidate()
            raise
        finally:
            self.connection.close()


class OutboxRepository:
    def __init__(self, clock: Callable[[], datetime] | None = None):
        self._clock = clock or (lambda: datetime.now(UTC))

    def add(self, session: Session, envelope: EventEnvelope[dict[str, Any]]) -> None:
        if not envelope.subject:
            raise ValueError("Report event subject is required")
        # 생산자끼리만 짧게 직렬화한다. 발행 중 유지되는 publish lock과 분리해
        # 상태 저장 트랜잭션이 브로커 응답을 기다리지 않도록 한다.
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": subject_key(envelope.subject, "enqueue")},
        )
        previous = session.scalar(
            select(func.max(outbox_event.c.created_at)).where(
                outbox_event.c.subject == envelope.subject, outbox_event.c.published_at.is_(None)
            )
        )
        now = self._clock()
        created = max(now, previous + timedelta(microseconds=1)) if previous else now
        session.execute(
            outbox_event.insert().values(
                id=UUID(envelope.id),
                event_type=envelope.type,
                routing_key=envelope.type,
                subject=envelope.subject,
                payload=envelope.model_dump(mode="json"),
                created_at=created,
                failure_count=0,
                manual_retry_count=0,
            )
        )

    def claim_next(self, engine) -> OutboxClaim | None:
        connection = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        held_key = None
        try:
            earlier = outbox_event.alias("earlier")
            head = ~exists(
                select(earlier.c.id).where(
                    earlier.c.subject == outbox_event.c.subject,
                    earlier.c.published_at.is_(None),
                    or_(
                        earlier.c.created_at < outbox_event.c.created_at,
                        (earlier.c.created_at == outbox_event.c.created_at)
                        & (earlier.c.id < outbox_event.c.id),
                    ),
                )
            )
            eligible = (
                outbox_event.c.published_at.is_(None),
                outbox_event.c.quarantined_at.is_(None),
                or_(
                    outbox_event.c.next_attempt_at.is_(None),
                    outbox_event.c.next_attempt_at <= self._clock(),
                ),
                head,
            )
            candidates = connection.execute(
                select(outbox_event.c.id, outbox_event.c.subject)
                .where(*eligible)
                .order_by(outbox_event.c.created_at, outbox_event.c.id)
                .limit(100)
            ).all()
            for event_id, subject in candidates:
                key = subject_key(subject)
                if not connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}):
                    continue
                held_key = key
                row = (
                    connection.execute(
                        select(outbox_event).where(outbox_event.c.id == event_id, *eligible)
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is not None:
                    return OutboxClaim(
                        connection, key, PendingEvent(row["id"], row["routing_key"], row["payload"])
                    )
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                held_key = None
        except BaseException:
            if held_key is not None:
                connection.invalidate()
            connection.close()
            raise
        connection.close()
        return None

    def mark_published(self, session: Session, event_id: UUID) -> None:
        session.execute(
            outbox_event.update()
            .where(outbox_event.c.id == event_id, outbox_event.c.published_at.is_(None))
            .values(published_at=self._clock(), next_attempt_at=None)
        )

    def record_failure(self, session: Session, event_id: UUID, error_code: str):
        if error_code not in {"PUBLISH_FAILED", "PUBLISH_TIMEOUT", "BROKER_UNAVAILABLE"}:
            raise ValueError("Only safe publication error codes may be stored")
        failures = session.scalar(
            select(outbox_event.c.failure_count)
            .where(outbox_event.c.id == event_id, outbox_event.c.published_at.is_(None))
            .with_for_update()
        )
        if failures is None:  # 삭제 소비자가 이미 지운 이벤트는 되살리지 않는다.
            return None
        failures += 1
        now = self._clock()
        quarantined = failures > len(RETRY_DELAYS)
        session.execute(
            outbox_event.update()
            .where(outbox_event.c.id == event_id)
            .values(
                failure_count=failures,
                last_failed_at=now,
                last_error_code=error_code,
                next_attempt_at=None
                if quarantined
                else now + timedelta(seconds=RETRY_DELAYS[failures - 1]),
                quarantined_at=now if quarantined else None,
            )
        )
        return quarantined

    def quarantined(self, session: Session, limit: int = 100):
        return (
            session.execute(
                select(
                    outbox_event.c.id,
                    outbox_event.c.event_type,
                    outbox_event.c.failure_count,
                    outbox_event.c.last_error_code,
                    outbox_event.c.quarantined_at,
                    outbox_event.c.manual_retry_count,
                    outbox_event.c.last_requeued_at,
                )
                .where(
                    outbox_event.c.quarantined_at.is_not(None),
                    outbox_event.c.published_at.is_(None),
                )
                .order_by(outbox_event.c.created_at, outbox_event.c.id)
                .limit(limit)
            )
            .mappings()
            .all()
        )

    def requeue(self, session: Session, event_id: UUID) -> bool:
        subject = session.scalar(
            select(outbox_event.c.subject).where(
                outbox_event.c.id == event_id,
                outbox_event.c.published_at.is_(None),
                outbox_event.c.quarantined_at.is_not(None),
            )
        )
        if subject is None or not session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": subject_key(subject)}
        ):
            return False
        result = session.execute(
            outbox_event.update()
            .where(
                outbox_event.c.id == event_id,
                outbox_event.c.published_at.is_(None),
                outbox_event.c.quarantined_at.is_not(None),
            )
            .values(
                failure_count=0,
                next_attempt_at=None,
                quarantined_at=None,
                manual_retry_count=outbox_event.c.manual_retry_count + 1,
                last_requeued_at=self._clock(),
            )
        )
        return result.rowcount == 1
