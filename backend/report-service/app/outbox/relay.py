"""Session advisory claim across publish; confirmation uses a short DB transaction."""

import asyncio
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.database import run_db, transaction
from app.outbox.repository import OutboxRepository, PendingEvent


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
            async with asyncio.timeout(self._timeout):
                await self._publisher.publish(claim.event)
            await run_db(lambda: self._mark(claim.event.id))
            return True
        finally:
            await run_db(claim.close)

    def _mark(self, event_id):
        with transaction(self._factory) as session:
            self._repository.mark_published(session, event_id)
