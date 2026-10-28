"""Queries against the existing Alembic schema. The service owns transactions."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Session

from app.generation.locking import lock_key
from app.generation.models import (
    GenerateReport,
    GenerationResult,
    JobConflict,
    ReportState,
    ReportStatus,
    WeeklyReport,
)

metadata = MetaData()
weekly_report = Table(
    "weekly_report",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("job_id", PG_UUID(as_uuid=True), nullable=False),
    Column("student_id", PG_UUID(as_uuid=True), nullable=False),
    Column("period_from", Date, nullable=False),
    Column("period_to", Date, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("status", String, nullable=False),
    Column("state", String),
    Column("inclusion_rule", Text),
    Column("failure_reason", String),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("generated_at", DateTime(timezone=True)),
)


def _report(row) -> WeeklyReport:
    return WeeklyReport(
        id=row["id"],
        job_id=row["job_id"],
        student_id=row["student_id"],
        period_from=row["period_from"],
        period_to=row["period_to"],
        revision=row["revision"],
        status=ReportStatus(row["status"]),
        state=ReportState(row["state"]) if row["state"] is not None else None,
    )


class ReportRepository:
    def find_by_job(self, session: Session, job_id: UUID) -> WeeklyReport | None:
        row = (
            session.execute(select(weekly_report).where(weekly_report.c.job_id == job_id))
            .mappings()
            .one_or_none()
        )
        return _report(row) if row is not None else None

    def get_or_create(self, session: Session, command: GenerateReport) -> tuple[WeeklyReport, bool]:
        # Also serializes revision allocation for different jobs for the same student/week.
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": lock_key(f"report-period:{command.student_id}:{command.period_from}")},
        )
        existing = self.find_by_job(session, command.job_id)
        if existing is not None:
            if (existing.student_id, existing.period_from, existing.period_to) != (
                command.student_id,
                command.period_from,
                command.period_to,
            ):
                raise JobConflict("Report job student/period does not match")
            return existing, False
        revision = session.scalar(
            select(func.coalesce(func.max(weekly_report.c.revision), 0) + 1).where(
                weekly_report.c.student_id == command.student_id,
                weekly_report.c.period_from == command.period_from,
            )
        )
        row = (
            session.execute(
                weekly_report.insert()
                .values(
                    id=uuid4(),
                    job_id=command.job_id,
                    student_id=command.student_id,
                    period_from=command.period_from,
                    period_to=command.period_to,
                    revision=revision,
                    status=ReportStatus.RUNNING,
                    state=None,
                    created_at=datetime.now(UTC),
                )
                .returning(weekly_report)
            )
            .mappings()
            .one()
        )
        return _report(row), True

    def finish(
        self,
        session: Session,
        report_id: UUID,
        *,
        result: GenerationResult | None = None,
        failure_reason: str | None = None,
    ) -> WeeklyReport | None:
        if (result is None) == (failure_reason is None):
            raise ValueError("Supply exactly one generation result or failure reason")
        values = {
            "status": ReportStatus.COMPLETED if result is not None else ReportStatus.FAILED,
            "state": result.state if result is not None else None,
            "inclusion_rule": result.inclusion_rule if result is not None else None,
            "failure_reason": failure_reason,
            "generated_at": datetime.now(UTC) if result is not None else None,
        }
        row = (
            session.execute(
                weekly_report.update()
                .where(
                    weekly_report.c.id == report_id,
                    weekly_report.c.status == ReportStatus.RUNNING,
                )
                .values(**values)
                .returning(weekly_report)
            )
            .mappings()
            .one_or_none()
        )
        return _report(row) if row is not None else None
