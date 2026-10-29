"""Per-job session locks, without holding a DB transaction over generation/HTTP calls."""

from hashlib import blake2b
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from app.generation.models import GenerationBusy


def lock_key(value: str) -> int:
    return int.from_bytes(blake2b(value.encode(), digest_size=8).digest(), "big", signed=True)


class JobLease:
    def __init__(self, connection: Connection, keys: list[tuple[int, bool]]) -> None:
        self._connection = connection
        self._keys = keys

    def close(self) -> None:
        try:
            for key, shared in reversed(self._keys):
                function = "pg_advisory_unlock_shared" if shared else "pg_advisory_unlock"
                self._connection.execute(text(f"SELECT {function}(:key)"), {"key": key})
        except BaseException:
            # Never return a connection with a session lock to the pool.
            self._connection.invalidate()
            raise
        finally:
            self._connection.close()


class JobLocks:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def acquire(self, job_id: UUID, student_id: UUID | None = None) -> JobLease:
        keys = []
        if student_id is not None:
            keys.append((lock_key(f"report-student:{student_id}"), True))
        keys.append((lock_key(f"report-job:{job_id}"), False))
        return self._acquire(keys)

    def acquire_student(self, student_id: UUID) -> JobLease:
        return self._acquire([(lock_key(f"report-student:{student_id}"), False)])

    def _acquire(self, keys: list[tuple[int, bool]]) -> JobLease:
        connection = self._engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        acquired_keys = []
        try:
            for key, shared in keys:
                function = "pg_try_advisory_lock_shared" if shared else "pg_try_advisory_lock"
                if not connection.scalar(text(f"SELECT {function}(:key)"), {"key": key}):
                    raise GenerationBusy("Report generation/deletion is already running")
                acquired_keys.append((key, shared))
            return JobLease(connection, acquired_keys)
        except BaseException:
            JobLease(connection, acquired_keys).close()
            raise
