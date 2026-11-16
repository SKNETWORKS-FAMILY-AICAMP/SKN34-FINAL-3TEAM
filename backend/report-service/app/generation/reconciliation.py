"""Reconcile persisted state under the same session locks as generation and deletion."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.database import transaction
from app.deletion.service import ensure_generation_allowed
from app.errors import ApiError
from app.generation.codec import ReportV1Codec
from app.generation.models import GenerationBusy, JobConflict, PeriodType, ReportEvent, ReportStatus
from app.generation.repository import ReportRepository
from app.outbox import service as outbox_service
from app.security import current_user_context


@dataclass(frozen=True)
class ReconciledJob:
    job_id: UUID
    student_id: UUID
    period_from: date
    period_to: date
    status: str
    report_id: UUID | None = None
    failure_reason: str | None = None
    period_type: PeriodType = PeriodType.WEEKLY


class ReconciliationService:
    def __init__(self, factory, locks):
        self._factory, self._locks = factory, locks
        self._repository = ReportRepository()

    def reconcile(self, job_id, student_id, period_from, period_to, period_type=PeriodType.WEEKLY):
        context = current_user_context()
        if (
            context is None
            or context.role != "SYSTEM"
            or context.student_scope != {str(student_id)}
        ):
            raise ApiError(403, "FORBIDDEN", "SYSTEM과 단일 학생 범위가 필요합니다")
        if (period_type == PeriodType.DAILY and period_from != period_to) or (
            period_type == PeriodType.WEEKLY
            and (period_from.weekday() != 0 or (period_to - period_from).days != 6)
        ):
            raise ApiError(
                400, "VALIDATION_FAILED", "일일은 하루, 주간은 월요일부터 일요일이어야 합니다"
            )

        def result(status, report_id=None, reason=None):
            return ReconciledJob(
                job_id, student_id, period_from, period_to, status, report_id, reason, period_type
            )

        try:
            lease = self._locks.acquire(job_id, student_id)
        except GenerationBusy:
            return result("BUSY")
        try:
            with transaction(self._factory) as session:
                report = self._repository.find_by_job(session, job_id)
                if report is not None and (
                    report.student_id,
                    report.period_from,
                    report.period_to,
                    report.period_type,
                ) != (student_id, period_from, period_to, period_type):
                    raise JobConflict("Report job student/period does not match")
                guard = self._repository.guard(
                    session, job_id, student_id, period_from, period_to, period_type
                )
                try:
                    allowed = ensure_generation_allowed(session, student_id, None)
                except GenerationBusy:
                    return result("BUSY")
                if not allowed:
                    return result("FAILED", reason="STUDENT_DELETED")
                if report is not None:
                    if report.status == ReportStatus.RUNNING:
                        report = self._repository.finish(
                            session, report.id, failure_reason="REPORT_EXECUTION_ABANDONED"
                        )
                        outbox_service.add_event(
                            session,
                            ReportV1Codec().encode(
                                ReportEvent("report.failed", report, "REPORT_EXECUTION_ABANDONED"),
                                context.traceparent,
                            ),
                        )
                    # Return stored terminal state even if outbox delivery was lost.
                    reason = self._repository.failure_reason(session, report.id)
                    return result(report.status, report.id, reason)
                if guard is None:
                    self._repository.block(
                        session, job_id, student_id, period_from, period_to, period_type
                    )
                return result("FAILED", reason="REPORT_NOT_CREATED")
        except JobConflict as exc:
            raise ApiError(
                409, "REPORT_JOB_IDENTITY_MISMATCH", "작업의 학생 또는 기간이 다릅니다"
            ) from exc
        finally:
            lease.close()
