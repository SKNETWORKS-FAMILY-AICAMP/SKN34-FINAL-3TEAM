"""Short DB transactions around an asynchronous generation step (#50, sequence 6.1)."""

import asyncio
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.database import run_db, transaction
from app.deletion.service import ensure_generation_allowed
from app.generation.locking import JobLocks
from app.generation.models import (
    GenerateReport,
    GenerationResult,
    ReportEvent,
    ReportStatus,
    WeeklyReport,
)
from app.generation.ports import ReportEventCodec, ReportGenerator
from app.generation.repository import ReportRepository
from app.generation.unconfigured import GeneratorNotConfigured
from app.outbox.repository import OutboxRepository
from app.security import current_user_context


class GenerationService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        locks: JobLocks,
        generator: ReportGenerator,
        codec: ReportEventCodec,
        *,
        repository: ReportRepository | None = None,
        outbox: OutboxRepository | None = None,
    ) -> None:
        self._factory = factory
        self._locks = locks
        self._generator = generator
        self._codec = codec
        self._repository = repository or ReportRepository()
        self._outbox = outbox or OutboxRepository()

    async def generate(self, command: GenerateReport) -> None:
        # Preserve the lease even if cancellation arrives while acquisition is in a DB thread.
        acquisition = asyncio.create_task(
            asyncio.to_thread(self._locks.acquire, command.job_id, command.student_id)
        )
        try:
            lease = await asyncio.shield(acquisition)
        except asyncio.CancelledError:
            try:
                lease = await acquisition
            except Exception:
                raise asyncio.CancelledError() from None
            await run_db(lease.close)
            raise
        try:
            report = await run_db(lambda: self._start(command))
            if report is None or report.status != ReportStatus.RUNNING:
                return
            try:
                result = await self._generator.generate(command, report)
            except GeneratorNotConfigured:
                await run_db(
                    lambda: self._finish(report.id, failure_reason="GENERATOR_NOT_CONFIGURED")
                )
            except Exception:
                # Do not persist raw exceptions (may contain student text, URLs or credentials).
                await run_db(lambda: self._finish(report.id, failure_reason="GENERATION_FAILED"))
            else:
                # DB/codec failure here is retriable; rollback leaves RUNNING for redelivery.
                await run_db(lambda: self._finish(report.id, result=result))
        finally:
            await run_db(lease.close)

    def _record_event(self, session: Session, event: ReportEvent) -> None:
        context = current_user_context()
        envelope = self._codec.encode(event, context.traceparent if context else None)
        if envelope.type != event.event_type or envelope.subject != str(event.report.student_id):
            raise ValueError("Encoded event type/subject does not match report")
        self._outbox.add(session, envelope)

    def _start(self, command: GenerateReport) -> WeeklyReport | None:
        with transaction(self._factory) as session:
            if not ensure_generation_allowed(session, command.student_id, command.requested_at):
                return None
            if (
                self._repository.guard(
                    session,
                    command.job_id,
                    command.student_id,
                    command.period_from,
                    command.period_to,
                    command.period_type,
                )
                is not None
            ):
                return None
            report, created = self._repository.get_or_create(session, command)
            if created:
                self._record_event(session, ReportEvent("report.started", report))
            return report

    def _finish(
        self,
        report_id: UUID,
        *,
        result: GenerationResult | None = None,
        failure_reason: str | None = None,
    ) -> None:
        with transaction(self._factory) as session:
            report = self._repository.finish(
                session, report_id, result=result, failure_reason=failure_reason
            )
            if report is not None:
                event_type = "report.completed" if result is not None else "report.failed"
                self._record_event(session, ReportEvent(event_type, report, failure_reason))


class ReportReadService:
    """조회 기능에 제공하는 generation 소유 데이터 접근."""

    def __init__(self):
        self._repository = ReportRepository()

    def latest_page(self, session, student_id, status, page, size, period_type=None):
        return self._repository.latest_page(session, student_id, status, page, size, period_type)

    def find(self, session, report_id):
        return self._repository.find(session, report_id)

    def revisions(self, session, student_id, period_from, period_type="WEEKLY"):
        return self._repository.revisions(session, student_id, period_from, period_type)

    def items(self, session, report_id):
        return self._repository.items(session, report_id)

    def correction_impact(self, session, student_id, attempt_id):
        return self._repository.correction_impact(session, student_id, attempt_id)

    def evidence(self, session, report_id, item_id):
        return self._repository.evidence(session, report_id, item_id)

    def file(self, session, report_id, format):
        return self._repository.file(session, report_id, format)


def delete_student(session, student_id):
    ReportRepository().delete_student(session, student_id)
