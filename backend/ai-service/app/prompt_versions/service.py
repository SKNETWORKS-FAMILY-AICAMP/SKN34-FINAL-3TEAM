"""core snapshot 조회와 수신 이벤트 조정. 소비자는 검증한 이벤트를 offer로만 넘긴다."""

import asyncio
import logging

from app.clients.core_client import CoreClient
from app.prompt_versions.models import ActiveVersionItem, tracked
from app.prompt_versions.registry import ActiveVersions

logger = logging.getLogger(__name__)


class PromptSync:
    def __init__(
        self, core: CoreClient, versions: ActiveVersions, retry_interval: float = 5.0
    ) -> None:
        self._core = core
        self._versions = versions
        self._retry_interval = retry_interval
        self._pending: dict[str, ActiveVersionItem] = {}
        self.initialized = False

    def reset(self) -> None:
        """구독이 끊기면 다음 snapshot 전까지 준비되지 않은 상태로 돌아간다."""
        self.initialized = False
        self._pending.clear()

    def is_ready(self) -> bool:
        return self.initialized and self._versions.is_ready()

    def offer(self, item: ActiveVersionItem) -> None:
        """snapshot 전에는 이름별 최신 revision만 보존하고, 이후에는 바로 적용한다."""
        if not tracked(item):
            return
        if self.initialized:
            self._versions.apply(item)
            return
        previous = self._pending.get(item.name)
        if previous is None or item.revision > previous.revision:
            self._pending[item.name] = item
        elif item.revision == previous.revision and item != previous:
            logger.warning("Conflicting pending revision ignored name=%s", item.name)

    async def synchronize(self, disconnected: asyncio.Event) -> None:
        while not disconnected.is_set():
            try:
                snapshot = await self._core.active_versions()
                if disconnected.is_set():
                    return
                self._versions.replace(snapshot)
                for item in self._pending.values():
                    self._versions.apply(item)
                self._pending.clear()
                self.initialized = True
                return
            except Exception as exc:
                logger.warning("Prompt snapshot retry error_type=%s", type(exc).__name__)
            try:
                await asyncio.wait_for(disconnected.wait(), self._retry_interval)
            except TimeoutError:
                pass
