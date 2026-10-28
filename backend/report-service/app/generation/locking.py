"""Per-job session locks, without holding a DB transaction over generation/HTTP calls."""

from hashlib import blake2b
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from app.generation.models import GenerationBusy


def lock_key(value: str) -> int:
    return int.from_bytes(blake2b(value.encode(), digest_size=8).digest(), "big", signed=True)


class JobLease:
    def __init__(self, connection: Connection, key: int) -> None:
        self._connection = connection
        self._key = key

    def close(self) -> None:
        try:
            self._connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self._key})
        except BaseException:
            # Never return a connection with a session lock to the pool.
            self._connection.invalidate()
            raise
        finally:
            self._connection.close()


class JobLocks:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def acquire(self, job_id: UUID) -> JobLease:
        connection = self._engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        key = lock_key(f"report-job:{job_id}")
        try:
            acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            if not acquired:
                raise GenerationBusy("Report job is already running")
            return JobLease(connection, key)
        except BaseException:
            connection.close()
            raise
