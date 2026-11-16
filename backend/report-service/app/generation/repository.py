"""Queries against the existing Alembic schema. The service owns transactions."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    delete,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Session

from app.generation.locking import lock_key
from app.generation.models import (
    GenerateReport,
    GenerationResult,
    ItemType,
    JobConflict,
    PeriodType,
    ReportState,
    ReportStatus,
    WeeklyReport,
)

metadata = MetaData()
report_job_guard = Table(
    "report_job_guard",
    metadata,
    Column("job_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("student_id", PG_UUID(as_uuid=True), nullable=False),
    Column("period_type", String, nullable=False),
    Column("period_from", Date, nullable=False),
    Column("period_to", Date, nullable=False),
    Column("failure_reason", String, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
weekly_report = Table(
    "weekly_report",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("job_id", PG_UUID(as_uuid=True), nullable=False),
    Column("student_id", PG_UUID(as_uuid=True), nullable=False),
    Column("period_type", String, nullable=False),
    Column("period_from", Date, nullable=False),
    Column("period_to", Date, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("status", String, nullable=False),
    Column("state", String),
    Column("inclusion_rule", Text),
    Column("failure_reason", String),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("generated_at", DateTime(timezone=True)),
    Column("narrative", JSONB(none_as_null=True)),
    Column("theme_summary", JSONB(none_as_null=True)),
    Column("verification", JSONB),
    Column("versions", JSONB),
    Column("evening_question", Text),
)
report_item = Table(
    "report_item",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("report_id", PG_UUID(as_uuid=True), nullable=False),
    Column("item_type", String, nullable=False),
    Column("seq", Integer, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("state", String, nullable=False),
    Column("verified", Boolean, nullable=False),
)
report_item_evidence = Table(
    "report_item_evidence",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("item_id", PG_UUID(as_uuid=True), nullable=False),
    Column("attempt_id", PG_UUID(as_uuid=True), nullable=False),
    Column("answer_id", PG_UUID(as_uuid=True), nullable=False),
    Column("answer_version", Integer, nullable=False),
)
report_file = Table(
    "report_file",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("report_id", PG_UUID(as_uuid=True), nullable=False),
    Column("format", String, nullable=False),
    Column("s3_key", String, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def _report(row) -> WeeklyReport:
    return WeeklyReport(
        id=row["id"],
        job_id=row["job_id"],
        student_id=row["student_id"],
        period_from=row["period_from"],
        period_to=row["period_to"],
        revision=row["revision"],
        period_type=PeriodType(row["period_type"]),
        status=ReportStatus(row["status"]),
        state=ReportState(row["state"]) if row["state"] is not None else None,
    )


class ReportRepository:
    def latest_page(self, session, student_id, status, page, size, period_type=None):
        ranked = (
            select(
                weekly_report,
                func.row_number()
                .over(
                    partition_by=(
                        weekly_report.c.student_id,
                        weekly_report.c.period_type,
                        weekly_report.c.period_from,
                    ),
                    order_by=weekly_report.c.revision.desc(),
                )
                .label("rank"),
            )
            .where(weekly_report.c.student_id == student_id)
            .subquery()
        )
        condition = ranked.c.rank == 1
        if period_type:
            condition &= ranked.c.period_type == period_type
        if status:
            condition &= ranked.c.status == status
        total = session.scalar(select(func.count()).select_from(ranked).where(condition))
        rows = (
            session.execute(
                select(ranked)
                .where(condition)
                .order_by(ranked.c.period_from.desc(), ranked.c.period_type)
                .offset(page * size)
                .limit(size)
            )
            .mappings()
            .all()
        )
        return rows, total

    def find(self, session, report_id):
        return (
            session.execute(select(weekly_report).where(weekly_report.c.id == report_id))
            .mappings()
            .one_or_none()
        )

    def revisions(self, session, student_id, period_from, period_type=PeriodType.WEEKLY):
        return (
            session.execute(
                select(weekly_report)
                .where(
                    weekly_report.c.student_id == student_id,
                    weekly_report.c.period_from == period_from,
                    weekly_report.c.period_type == period_type,
                )
                .order_by(weekly_report.c.revision.desc())
            )
            .mappings()
            .all()
        )

    def items(self, session, report_id):
        return (
            session.execute(
                select(report_item)
                .where(report_item.c.report_id == report_id)
                .order_by(report_item.c.item_type, report_item.c.seq)
            )
            .mappings()
            .all()
        )

    def correction_impact(self, session, student_id, attempt_id):
        """Completed revisions built from an attempt (#244). Evidence links are dropped when
        parent sharing is off, so match the attempt IDs every payload keeps."""
        attempt = str(attempt_id)
        weekly = and_(
            weekly_report.c.period_type == PeriodType.WEEKLY,
            report_item.c.item_type == ItemType.THINKING_TYPE,
            report_item.c.payload["missions"].contains([{"attemptId": attempt}]),
        )
        daily = and_(
            weekly_report.c.period_type == PeriodType.DAILY,
            report_item.c.item_type == ItemType.PROBLEM,
            report_item.c.payload["attemptId"].astext == attempt,
        )
        return (
            session.execute(
                select(
                    weekly_report.c.id,
                    weekly_report.c.period_type,
                    weekly_report.c.period_from,
                    weekly_report.c.revision,
                )
                .join(report_item, report_item.c.report_id == weekly_report.c.id)
                .where(
                    weekly_report.c.student_id == student_id,
                    weekly_report.c.status == ReportStatus.COMPLETED,
                    or_(weekly, daily),
                )
                .distinct()
                .order_by(weekly_report.c.period_from, weekly_report.c.revision)
            )
            .mappings()
            .all()
        )

    def evidence(self, session, report_id, item_id):
        item = session.scalar(
            select(report_item.c.id).where(
                report_item.c.id == item_id, report_item.c.report_id == report_id
            )
        )
        if item is None:
            return None
        return (
            session.execute(
                select(report_item_evidence).where(report_item_evidence.c.item_id == item_id)
            )
            .mappings()
            .all()
        )

    def file(self, session, report_id, format):
        return (
            session.execute(
                select(report_file).where(
                    report_file.c.report_id == report_id, report_file.c.format == format.upper()
                )
            )
            .mappings()
            .one_or_none()
        )

    def delete_student(self, session, student_id):
        session.execute(delete(report_job_guard).where(report_job_guard.c.student_id == student_id))
        reports = select(weekly_report.c.id).where(weekly_report.c.student_id == student_id)
        items = select(report_item.c.id).where(report_item.c.report_id.in_(reports))
        session.execute(
            delete(report_item_evidence).where(report_item_evidence.c.item_id.in_(items))
        )
        session.execute(delete(report_item).where(report_item.c.report_id.in_(reports)))
        session.execute(delete(report_file).where(report_file.c.report_id.in_(reports)))
        session.execute(delete(weekly_report).where(weekly_report.c.student_id == student_id))

    def guard(
        self, session, job_id, student_id, period_from, period_to, period_type=PeriodType.WEEKLY
    ):
        row = (
            session.execute(select(report_job_guard).where(report_job_guard.c.job_id == job_id))
            .mappings()
            .one_or_none()
        )
        if row is not None and (
            row["student_id"],
            row["period_from"],
            row["period_to"],
            row["period_type"],
        ) != (
            student_id,
            period_from,
            period_to,
            period_type,
        ):
            raise JobConflict("Report job guard student/period does not match")
        return row

    def block(
        self, session, job_id, student_id, period_from, period_to, period_type=PeriodType.WEEKLY
    ):
        session.execute(
            report_job_guard.insert().values(
                job_id=job_id,
                student_id=student_id,
                period_from=period_from,
                period_to=period_to,
                period_type=period_type,
                failure_reason="REPORT_NOT_CREATED",
                created_at=datetime.now(UTC),
            )
        )

    def failure_reason(self, session, report_id):
        return session.scalar(
            select(weekly_report.c.failure_reason).where(weekly_report.c.id == report_id)
        )

    def find_by_job(self, session: Session, job_id: UUID) -> WeeklyReport | None:
        row = (
            session.execute(select(weekly_report).where(weekly_report.c.job_id == job_id))
            .mappings()
            .one_or_none()
        )
        return _report(row) if row is not None else None

    @staticmethod
    def _save_items(session: Session, report_id: UUID, result: GenerationResult) -> None:
        item_rows, evidence_rows = [], []
        for item in result.items:
            item_id = uuid4()
            item_rows.append(
                {
                    "id": item_id,
                    "report_id": report_id,
                    "item_type": item.type,
                    "seq": item.seq,
                    "payload": item.payload,
                    "state": item.state,
                    "verified": item.verified,
                }
            )
            evidence_rows.extend(
                {
                    "id": uuid4(),
                    "item_id": item_id,
                    "attempt_id": link.attempt_id,
                    "answer_id": link.answer_id,
                    "answer_version": link.answer_version,
                }
                for link in item.evidence
            )
        if item_rows:
            session.execute(report_item.insert(), item_rows)
        if evidence_rows:
            session.execute(report_item_evidence.insert(), evidence_rows)
        if result.files:
            session.execute(
                report_file.insert(),
                [
                    {
                        "id": uuid4(),
                        "report_id": report_id,
                        "format": file.format,
                        "s3_key": file.key,
                        "size_bytes": file.size_bytes,
                        "created_at": result.generated_at or datetime.now(UTC),
                    }
                    for file in result.files
                ],
            )

    def get_or_create(self, session: Session, command: GenerateReport) -> tuple[WeeklyReport, bool]:
        # Also serializes revision allocation for different jobs for the same student/week.
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {
                "key": lock_key(
                    f"report-period:{command.student_id}:{command.period_type}:{command.period_from}"
                )
            },
        )
        existing = self.find_by_job(session, command.job_id)
        if existing is not None:
            if (
                existing.student_id,
                existing.period_from,
                existing.period_to,
                existing.period_type,
            ) != (
                command.student_id,
                command.period_from,
                command.period_to,
                command.period_type,
            ):
                raise JobConflict("Report job student/period does not match")
            return existing, False
        revision = session.scalar(
            select(func.coalesce(func.max(weekly_report.c.revision), 0) + 1).where(
                weekly_report.c.student_id == command.student_id,
                weekly_report.c.period_from == command.period_from,
                weekly_report.c.period_type == command.period_type,
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
                    period_type=command.period_type,
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
            "generated_at": (result.generated_at or datetime.now(UTC)) if result else None,
            "narrative": result.narrative if result else None,
            "theme_summary": result.theme_summary if result else None,
            "verification": (
                {**(result.verification or {}), "explanationState": result.explanation_state}
                if result and result.explanation_state is not None
                else result.verification
                if result
                else None
            ),
            "versions": result.versions if result else None,
            "evening_question": result.evening_question if result else None,
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
        if row is None:
            return None
        if result is not None:
            self._save_items(session, report_id, result)
        return _report(row)
