"""Guard -> physical object deletion -> atomic DB deletion -> core completion."""

import asyncio

from app.concurrency import run_blocking
from app.database import transaction
from app.deletion.repository import DeletionRepository, delete_processed_before, guard_status
from app.deletion.state import DeleteStudent, generation_allowed
from app.errors import ApiError
from app.outbox.service import delete_subject


def ensure_generation_allowed(session, student_id, requested_at=None):
    return generation_allowed(guard_status(session, student_id))


def ensure_query_allowed(session, student_id):
    if guard_status(session, student_id) == "PENDING":
        raise ApiError(409, "DELETION_IN_PROGRESS", "학생 기록을 삭제 중입니다")


def prune_processed(session, before):
    return delete_processed_before(session, before)


def finish_deletion(session, command, repository=None):
    # 생성 서비스도 삭제 장벽을 사용하므로 이 호출 경계에서 지연 import한다.
    from app.generation.service import delete_student

    delete_student(session, command.student_id)
    delete_subject(session, str(command.student_id))
    (repository or DeletionRepository()).finish(session, command)


class DeletionService:
    def __init__(self, factory, locks, storage_loader, core, *, repository=None):
        self._factory, self._locks = factory, locks
        self._storage, self._core = storage_loader, core
        self._repository = repository or DeletionRepository()

    async def delete(self, command: DeleteStudent):
        acquisition = asyncio.create_task(
            asyncio.to_thread(self._locks.acquire_student, command.student_id)
        )
        try:
            lease = await asyncio.shield(acquisition)
        except asyncio.CancelledError:
            try:
                lease = await acquisition
            except Exception:
                raise asyncio.CancelledError() from None
            await run_blocking(lease.close)
            raise
        try:
            needed = await run_blocking(lambda: self._begin(command))
            if needed:
                await run_blocking(
                    lambda: self._storage().delete_prefix(f"reports/{command.student_id}/")
                )
                await run_blocking(lambda: self._finish(command))
            # Repeat callback even after processed_event: core may have missed the first callback.
            await self._core.report_deletion_completed(command.request_id)
        finally:
            await run_blocking(lease.close)

    def _begin(self, command):
        with transaction(self._factory) as session:
            return self._repository.begin(session, command)

    def _finish(self, command):
        with transaction(self._factory) as session:
            finish_deletion(session, command, self._repository)
