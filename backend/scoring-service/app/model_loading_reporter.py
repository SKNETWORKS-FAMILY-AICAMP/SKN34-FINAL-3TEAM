"""전체 상태를 즉시/30초마다 재보고. 발행 실패는 로딩과 분리한다."""

import asyncio
import contextlib
import os
import socket
from uuid import uuid4

from app.messaging.envelope import EventEnvelope
from app.messaging.publisher import EventPublisher
from app.model_registry import ModelRegistry

EVENT = "model.loading.reported"


class ModelLoadingReporter:
    def __init__(self, registry: ModelRegistry, publisher: EventPublisher, interval: float = 30):
        self.registry = registry
        self.publisher = publisher
        self.interval = interval
        self.pod_id = os.environ.get("POD_NAME") or socket.gethostname()
        self.instance_id = str(uuid4())
        self.sequence = 0
        self.task = None

    async def publish(self):
        self.sequence += 1
        envelope = EventEnvelope(
            type=EVENT,
            source="scoring-service",
            dataschema=f"{EVENT}.v1",
            data={
                "podId": self.pod_id,
                "instanceId": self.instance_id,
                "sequence": self.sequence,
                "models": self.registry.loading_status(),
            },
        )
        try:
            async with asyncio.timeout(2):
                await self.publisher.publish(envelope, EVENT)
        except Exception:
            # heartbeat가 전체 상태를 다시 보내므로 추론·로딩을 막지 않는다.
            pass

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def run(self):
        while True:
            self.registry.changed.clear()
            await self.publish()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.registry.changed.wait(), self.interval)

    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        await self.publisher.close()
