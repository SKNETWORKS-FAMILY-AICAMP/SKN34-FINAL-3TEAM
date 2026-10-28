"""core snapshot 조회·최초 로딩 재시도. health 요청에서 하위 서비스를 호출하지 않는다."""

import asyncio
import contextlib
import logging

from app.clients.core_client import CoreClient
from app.model_registry import ModelRegistry

logger = logging.getLogger(__name__)


class ModelStartup:
    def __init__(self, core: CoreClient, registry: ModelRegistry, retry_interval: float) -> None:
        self._core = core
        self._registry = registry
        self._retry_interval = retry_interval
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.ready = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                versions = await self._core.active_versions()
                await self._registry.replace(versions)
                self.ready = True
                return
            except Exception as exc:
                logger.warning("Model startup retry error_type=%s", type(exc).__name__)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), self._retry_interval)

    async def is_ready(self) -> bool:
        return self.ready

    async def close(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
