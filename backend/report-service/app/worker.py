"""Shared v1 generation/deletion subscriptions, bounded Outbox relay and graceful drain."""

import asyncio
import contextlib
import logging
import signal
from contextlib import AsyncExitStack

from app.clients.ai_client import AiClient
from app.clients.base import internal_client
from app.clients.core_client import CoreClient
from app.clients.learning_client import LearningClient
from app.clients.storage import ObjectStorage
from app.concurrency import run_blocking
from app.config import get_settings
from app.database import create_db_engine, create_session_factory
from app.deletion.consumer import DELETION_QUEUE, StudentDeletedConsumer
from app.deletion.service import DeletionService
from app.generation.codec import ReportV1Codec
from app.generation.consumer import GENERATE_QUEUE, GenerationConsumer
from app.generation.locking import JobLocks
from app.generation.pipeline import DisplayNameProvider, build_pipeline
from app.generation.service import GenerationService
from app.messaging.connection import AmqpConnection
from app.messaging.consumer import EventConsumer
from app.messaging.publisher import EventPublisher
from app.outbox.relay import OutboxRelay

logger = logging.getLogger(__name__)


async def serve(amqp, consumer, handlers, relay, stop):
    subscriptions, active = [], set()

    def tracked(handler):
        async def call(envelope):
            task = asyncio.current_task()
            active.add(task)
            try:
                await handler(envelope)
            finally:
                active.discard(task)

        return call

    async def relay_loop():
        while not stop.is_set():
            try:
                if amqp.is_connected and await relay.publish_once():
                    continue
            except Exception:
                logger.warning("Outbox publication deferred; message contents omitted")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=1)

    relay_task = asyncio.create_task(relay_loop())
    try:
        for queue, handler in handlers:
            while not stop.is_set():
                try:
                    subscriptions.append(await consumer.consume(queue, tracked(handler)))
                    break
                except Exception:
                    logger.warning("Consumer registration deferred: queue=%s", queue)
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(stop.wait(), timeout=5)
        await stop.wait()
    finally:
        stop.set()
        try:
            for subscription in subscriptions:
                await subscription.stop()
        finally:
            if active:
                await asyncio.gather(*tuple(active), return_exceptions=True)
            await relay_task
            for subscription in subscriptions:
                await subscription.close()


async def run(generator=None, *, display_names: DisplayNameProvider | None = None) -> None:
    if generator is not None and display_names is not None:
        raise ValueError("Supply either a generator or a display name provider")
    settings = get_settings()
    amqp = AmqpConnection(settings.rabbitmq_url)
    engine = create_db_engine()
    factory = create_session_factory(engine)
    locks = JobLocks(engine)
    storage_instances = []

    def storage():
        if not storage_instances:
            storage_instances.append(ObjectStorage.configured())
        return storage_instances[0]

    codec = ReportV1Codec()
    publisher = EventPublisher(amqp)
    amqp.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # Windows 로컬 실행
            loop.add_signal_handler(sig, stop.set)
    try:
        async with AsyncExitStack() as clients:
            core_http = await clients.enter_async_context(internal_client(settings.core_url))
            core = CoreClient(core_http)
            if generator is None:
                learning_http = await clients.enter_async_context(
                    internal_client(settings.learning_url)
                )
                ai_http = await clients.enter_async_context(internal_client(settings.ai_url))
                generator = build_pipeline(
                    display_names if display_names is not None else core,
                    LearningClient(learning_http),
                    AiClient(ai_http),
                    storage(),
                )
            service = GenerationService(factory, locks, generator, codec)
            await serve(
                amqp,
                EventConsumer(amqp, settings.consumer_max_retries, settings.consumer_prefetch),
                [
                    (
                        DELETION_QUEUE,
                        StudentDeletedConsumer(DeletionService(factory, locks, storage, core)),
                    ),
                    (GENERATE_QUEUE, GenerationConsumer(service, codec)),
                ],
                OutboxRelay(factory, publisher),
                stop,
            )
    finally:
        await publisher.close()
        await amqp.close()
        for instance in storage_instances:
            await run_blocking(instance.close)
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
