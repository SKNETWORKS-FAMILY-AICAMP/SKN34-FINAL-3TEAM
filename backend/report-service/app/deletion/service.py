"""Guard -> physical object deletion -> atomic DB deletion -> core completion."""

import asyncio

from app.concurrency import run_blocking
from app.database import transaction
from app.deletion.state import DeleteStudent, DeletionRepository


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
            self._repository.finish(session, command)
