"""로컬 통합 검증용 replica. 합성 로더 외에는 운영 registry/report/publisher를 사용한다."""

import asyncio
import os

from app.messaging.connection import AmqpConnection
from app.messaging.publisher import EventPublisher
from app.model_loading_reporter import ModelLoadingReporter
from app.model_registry import ModelRegistry
from tests.test_model_registry import loaded, version


async def main():
    registry = ModelRegistry(loaded)
    name = os.environ["TEST_MODEL_NAME"]
    await registry.load(version(1, name=name, release="old"))
    if os.environ.get("TEST_FAIL") == "true":

        def broken(_):
            raise ValueError("synthetic failure")

        registry._loader = broken
    try:
        await registry.load(version(2, name=name, release="current"))
    except ValueError:
        pass
    amqp = AmqpConnection(os.environ["TEST_AMQP_URL"])
    amqp.start()
    try:
        async with asyncio.timeout(20):
            while not amqp.is_connected:
                await asyncio.sleep(0.1)
        reporter = ModelLoadingReporter(registry, EventPublisher(amqp))
        await reporter.publish()
        await reporter.close()
    finally:
        await amqp.close()


if __name__ == "__main__":
    asyncio.run(main())
