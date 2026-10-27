"""Persist full envelopes in the caller's transaction; never commit from a repository."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Column, DateTime, MetaData, String, Table, select
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
)


@dataclass(frozen=True)
class PendingEvent:
    id: UUID
    routing_key: str
    payload: dict[str, Any]


class OutboxRepository:
    def add(self, session: Session, envelope: EventEnvelope[dict[str, Any]]) -> None:
        if not envelope.subject:
            raise ValueError("Report event subject is required")
        session.execute(
            outbox_event.insert().values(
                id=UUID(envelope.id),
                event_type=envelope.type,
                routing_key=envelope.type,
                subject=envelope.subject,
                payload=envelope.model_dump(mode="json"),
                created_at=datetime.now(UTC),
            )
        )

    def next_unpublished(self, session: Session) -> PendingEvent | None:
        row = (
            session.execute(
                select(outbox_event)
                .where(outbox_event.c.published_at.is_(None))
                .order_by(outbox_event.c.created_at, outbox_event.c.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return PendingEvent(row["id"], row["routing_key"], row["payload"])

    def mark_published(self, session: Session, event_id: UUID) -> None:
        session.execute(
            outbox_event.update()
            .where(outbox_event.c.id == event_id, outbox_event.c.published_at.is_(None))
            .values(published_at=datetime.now(UTC))
        )
