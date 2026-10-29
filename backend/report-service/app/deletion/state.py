"""Durable guard plus ordinary processed_event idempotency; no source text is retained."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, MetaData, String, Table, delete, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert

from app.generation.models import GenerationBusy
from app.generation.records import RecordContractError
from app.generation.repository import (
    report_file,
    report_item,
    report_item_evidence,
    report_job_guard,
    weekly_report,
)
from app.outbox.repository import outbox_event

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


@dataclass(frozen=True)
class DeleteStudent:
    event_id: UUID
    student_id: UUID
    request_id: UUID
    scope: str
    occurred_at: datetime

    def __post_init__(self):
        if self.scope not in {"PROFILE", "RECORDS"} or self.occurred_at.utcoffset() is None:
            raise RecordContractError("Invalid student deletion scope/time")


def generation_allowed(session, student_id, requested_at):
    row = (
        session.execute(select(deletion_guard).where(deletion_guard.c.student_id == student_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        return True
    if row["status"] == "PENDING":
        raise GenerationBusy("Student deletion is pending")
    # Core does not resume learning after either deletion scope. A future resume
    # contract must explicitly lift this guard; message time grants no permission.
    return False


def query_allowed(session, student_id):
    status = session.scalar(
        select(deletion_guard.c.status).where(deletion_guard.c.student_id == student_id)
    )
    if status == "PENDING":
        from app.errors import ApiError

        raise ApiError(409, "DELETION_IN_PROGRESS", "학생 기록을 삭제 중입니다")


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
        if processed is not None:
            if (
                processed == "student.deleted"
                and row is not None
                and row["status"] == "PENDING"
                and row["deletion_request_id"] != command.request_id
            ):
                # Completed before a newer request started; resend only its completion report.
                return False
            if (
                processed != "student.deleted"
                or row is None
                or row["status"] != "COMPLETED"
                # PROFILE also covers later events: use the same coverage rule
                # on redelivery as when the event was first marked processed.
                or (row["scope"] != "PROFILE" and row["cutoff_at"] < command.occurred_at)
                or (command.scope == "PROFILE" and row["scope"] != "PROFILE")
            ):
                raise RecordContractError("Processed deletion identity is inconsistent")
            return False
        if row is not None:
            covered = row["scope"] == "PROFILE" or (
                command.scope == "RECORDS" and row["cutoff_at"] >= command.occurred_at
            )
            if covered and row["status"] == "COMPLETED":
                self._mark_processed(session, command)
                return False
            if row["status"] == "PENDING" and row["deletion_request_id"] != command.request_id:
                raise GenerationBusy("Another deletion request must finish first")
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
            delete(report_job_guard).where(report_job_guard.c.student_id == command.student_id)
        )
        reports = select(weekly_report.c.id).where(weekly_report.c.student_id == command.student_id)
        items = select(report_item.c.id).where(report_item.c.report_id.in_(reports))
        session.execute(
            delete(report_item_evidence).where(report_item_evidence.c.item_id.in_(items))
        )
        session.execute(delete(report_item).where(report_item.c.report_id.in_(reports)))
        session.execute(delete(report_file).where(report_file.c.report_id.in_(reports)))
        session.execute(
            delete(weekly_report).where(weekly_report.c.student_id == command.student_id)
        )
        session.execute(
            delete(outbox_event).where(outbox_event.c.subject == str(command.student_id))
        )
        session.execute(
            deletion_guard.update()
            .where(deletion_guard.c.student_id == command.student_id)
            .values(status="COMPLETED", updated_at=datetime.now(UTC))
        )
        self._mark_processed(session, command)
