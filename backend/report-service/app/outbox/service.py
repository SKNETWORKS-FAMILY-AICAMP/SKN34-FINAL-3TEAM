"""다른 기능의 동일 트랜잭션에서 호출하는 Outbox 정리 진입점."""

from app.outbox.repository import OutboxRepository


def delete_subject(session, subject):
    OutboxRepository().delete_subject(session, subject)


def prune_published(session, before):
    return OutboxRepository().delete_published_before(session, before)
