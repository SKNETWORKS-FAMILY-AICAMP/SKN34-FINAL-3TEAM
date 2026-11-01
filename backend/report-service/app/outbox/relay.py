"""Session advisory claim across publish; confirmation uses a short DB transaction."""

import asyncio
import logging
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.database import run_db, transaction
from app.outbox.repository import OutboxRepository, PendingEvent

logger = logging.getLogger(__name__)


class Publisher(Protocol):
    async def publish(self, event: PendingEvent) -> None: ...


class OutboxRelay:
    def __init__(
        self,
        factory: sessionmaker[Session],
        publisher: Publisher,
        *,
        timeout: float = 15.0,
        repository: OutboxRepository | None = None,
    ) -> None:
        self._factory = factory
        self._publisher = publisher
        self._timeout = timeout
        self._repository = repository or OutboxRepository()

    async def publish_once(self) -> bool:
        with self._factory() as session:
            engine = session.get_bind()
        acquisition = asyncio.create_task(asyncio.to_thread(self._repository.claim_next, engine))
        try:
            claim = await asyncio.shield(acquisition)
        except asyncio.CancelledError:
            claim = await acquisition
            if claim is not None:
                await run_db(claim.close)
            raise
        if claim is None:
            return False
        try:
            try:
                async with asyncio.timeout(self._timeout):
                    await self._publisher.publish(claim.event)
            except Exception as exc:
                code = (
                    "PUBLISH_TIMEOUT"
                    if isinstance(exc, TimeoutError)
                    else "BROKER_UNAVAILABLE"
                    if isinstance(exc, ConnectionError)
                    else "PUBLISH_FAILED"
                )
                quarantined = await run_db(lambda: self._failed(claim.event.id, code))
                logger.log(
                    logging.ERROR if quarantined else logging.WARNING,
                    "Outbox %s: id=%s code=%s",
                    "quarantined" if quarantined else "retry deferred",
                    claim.event.id,
                    code,
                )
                raise
            await run_db(lambda: self._mark(claim.event.id))
            return True
        finally:
            await run_db(claim.close)

    def _mark(self, event_id):
        with transaction(self._factory) as session:
            self._repository.mark_published(session, event_id)

    def _failed(self, event_id, code):
        with transaction(self._factory) as session:
            return self._repository.record_failure(session, event_id, code)
