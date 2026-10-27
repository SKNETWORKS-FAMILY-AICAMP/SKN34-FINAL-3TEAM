"""Worker composition; report.generate requires #42's production codec injection."""

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
from app.generation.consumer import GENERATE_QUEUE, GenerationConsumer
from app.generation.locking import JobLocks
from app.generation.narrative_generator import NarrativeGenerator
from app.generation.ports import ReportEventCodec
from app.generation.record_generator import RecordGenerator
from app.generation.service import GenerationService
from app.messaging.connection import AmqpConnection
from app.messaging.consumer import EventConsumer
from app.messaging.publisher import EventPublisher
from app.outbox.relay import OutboxRelay
from app.rendering.generator import RenderingGenerator
from app.rendering.renderer import ReportRenderer

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
                logger.warning("Outbox publication deferred; retrying without message contents")
            try:
                await asyncio.wait_for(stop.wait(), timeout=1)
            except TimeoutError:
                pass

    task = asyncio.create_task(relay_loop())
    try:
        for queue, handler in handlers:
            while not stop.is_set():
                try:
                    subscriptions.append(await consumer.consume(queue, tracked(handler)))
                    break
                except Exception:
                    logger.warning("Consumer registration deferred: queue=%s", queue)
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=5)
                    except TimeoutError:
                        pass
        await stop.wait()
    finally:
        stop.set()
        for subscription in subscriptions:
            await subscription.stop()
        if active:
            await asyncio.gather(*tuple(active), return_exceptions=True)
        await task
        for subscription in subscriptions:
            await subscription.close()


async def run(report_codec: ReportEventCodec | None = None) -> None:
    settings = get_settings()
    amqp = AmqpConnection(settings.rabbitmq_url)
    engine = create_db_engine()
    factory, locks = create_session_factory(engine), JobLocks(engine)
    storage_instances = []

    def storage():
        if not storage_instances:
            storage_instances.append(ObjectStorage.configured())
        return storage_instances[0]

    amqp.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # Windows 로컬 실행
            loop.add_signal_handler(sig, stop.set)
    publisher = EventPublisher(amqp)
    try:
        async with AsyncExitStack() as stack:
            core = CoreClient(await stack.enter_async_context(internal_client(settings.core_url)))
            handlers = [
                (
                    DELETION_QUEUE,
                    StudentDeletedConsumer(DeletionService(factory, locks, storage, core)),
                )
            ]
            if report_codec is not None:
                learning = LearningClient(
                    await stack.enter_async_context(internal_client(settings.learning_url))
                )
                ai = AiClient(await stack.enter_async_context(internal_client(settings.ai_url)))

                class LazyRendering:
                    async def generate(self, command, report):
                        return await RenderingGenerator(
                            NarrativeGenerator(RecordGenerator(learning), ai, learning),
                            ReportRenderer(),
                            storage(),
                        ).generate(command, report)

                handlers.append(
                    (
                        GENERATE_QUEUE,
                        GenerationConsumer(
                            GenerationService(factory, locks, LazyRendering(), report_codec),
                            report_codec,
                        ),
                    )
                )
            else:
                logger.warning("report.generate disabled: #42 codec integration required")
            await serve(
                amqp,
                EventConsumer(amqp, settings.consumer_max_retries, settings.consumer_prefetch),
                handlers,
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
