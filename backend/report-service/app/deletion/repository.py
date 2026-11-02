"""삭제 장벽과 처리 이력 DB 작업. 트랜잭션은 호출 서비스가 소유한다."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, MetaData, String, Table, delete, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert

from app.deletion.state import DeleteStudent, begin_action

metadata = MetaData()
deletion_guard = Table(
    "report_deletion_guard",
    metadata,
    Column("student_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("scope", String, nullable=False),
    Column("cutoff_at", DateTime(timezone=True), nullable=False),
    Column("deletion_request_id", PG_UUID(as_uuid=True), nullable=False),
    Column("status", String, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
processed_event = Table(
    "processed_event",
    metadata,
    Column("event_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("event_type", String, nullable=False),
    Column("processed_at", DateTime(timezone=True), nullable=False),
)


def delete_processed_before(session, before: datetime) -> int:
    """보존 기간 정리(#208). 삭제 장벽 report_deletion_guard는 지우지 않는다."""
    return session.execute(
        delete(processed_event).where(processed_event.c.processed_at < before)
    ).rowcount


def guard_status(session, student_id):
    return session.scalar(
        select(deletion_guard.c.status).where(deletion_guard.c.student_id == student_id)
    )


class DeletionRepository:
    def begin(self, session, command: DeleteStudent) -> bool:
        row = (
            session.execute(
                select(deletion_guard).where(deletion_guard.c.student_id == command.student_id)
            )
            .mappings()
            .one_or_none()
        )
        processed = session.scalar(
            select(processed_event.c.event_type).where(
                processed_event.c.event_id == command.event_id
            )
        )
        action = begin_action(row, processed, command)
        if action == "MARK":
            self._mark_processed(session, command)
        if action != "START":
            return False
        values = {
            "student_id": command.student_id,
            "scope": "PROFILE" if row and row["scope"] == "PROFILE" else command.scope,
            "cutoff_at": max(row["cutoff_at"], command.occurred_at) if row else command.occurred_at,
            "deletion_request_id": command.request_id,
            "status": "PENDING",
            "updated_at": datetime.now(UTC),
        }
        session.execute(
            insert(deletion_guard)
            .values(**values)
            .on_conflict_do_update(index_elements=[deletion_guard.c.student_id], set_=values)
        )
        return True

    @staticmethod
    def _mark_processed(session, command):
        session.execute(
            insert(processed_event)
            .values(
                event_id=command.event_id,
                event_type="student.deleted",
                processed_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing()
        )

    def finish(self, session, command):
        session.execute(
            deletion_guard.update()
            .where(deletion_guard.c.student_id == command.student_id)
            .values(status="COMPLETED", updated_at=datetime.now(UTC))
        )
        self._mark_processed(session, command)
