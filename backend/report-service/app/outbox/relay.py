"""Concurrent relays claim separate rows and commit published_at only after confirmation."""

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
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
        loop = asyncio.get_running_loop()
        return await run_db(lambda: self._publish_one(loop))

    def _publish_one(self, loop: asyncio.AbstractEventLoop) -> bool:
        # The Session and transaction stay in one DB thread. AMQP stays on its event loop.
        with transaction(self._factory) as session:
            event = self._repository.next_unpublished(session)
            if event is None:
                return False
            publication = asyncio.run_coroutine_threadsafe(self._publisher.publish(event), loop)
            try:
                publication.result(timeout=self._timeout)
            except FutureTimeoutError:
                publication.cancel()
                raise
            self._repository.mark_published(session, event.id)
            return True
