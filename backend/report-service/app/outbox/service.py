"""다른 기능의 동일 트랜잭션에서 호출하는 Outbox 정리 진입점과 운영용 격리 이벤트 처리."""

from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.database import transaction
from app.outbox.repository import OutboxRepository


def add_event(session, envelope):
    OutboxRepository().add(session, envelope)


def delete_subject(session, subject):
    OutboxRepository().delete_subject(session, subject)


def prune_published(session, before):
    return OutboxRepository().delete_published_before(session, before)


def list_quarantined(factory: sessionmaker[Session], limit: int) -> list[dict]:
    with transaction(factory) as session:
        return [dict(row) for row in OutboxRepository().quarantined(session, limit)]


def requeue(factory: sessionmaker[Session], event_id: UUID) -> bool:
    with transaction(factory) as session:
        return OutboxRepository().requeue(session, event_id)
