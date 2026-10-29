"""core snapshot 조회·최초 로딩 재시도. health 요청에서 하위 서비스를 호출하지 않는다."""

import asyncio
import contextlib
import logging

from app.clients.core_client import CoreClient
from app.model_registry import ModelRegistry, RevisionConflict
from app.model_versions import ActiveModelVersion

logger = logging.getLogger(__name__)


class ModelStartup:
    def __init__(self, core: CoreClient, registry: ModelRegistry, retry_interval: float) -> None:
        self._core = core
        self._registry = registry
        self._retry_interval = retry_interval
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.ready = False
        self._pending: dict[str, ActiveModelVersion] = {}
        self._changed = asyncio.Event()

    def offer(self, version: ActiveModelVersion) -> None:
        """조회·로딩 중에도 수신을 계속하고 이름별 최신 이벤트만 보존한다."""
        previous = self._pending.get(version.name)
        if previous is None or version.revision > previous.revision:
            self._pending[version.name] = version
            self._changed.set()
        elif version.revision == previous.revision and version != previous:
            logger.warning("Conflicting model event ignored")

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.ready:
                    snapshot = {v.name: v for v in await self._core.active_versions()}
                    for name, event in self._pending.items():
                        if name not in snapshot or event.revision > snapshot[name].revision:
                            snapshot[name] = event
                    await self._registry.replace(list(snapshot.values()))
                # snapshot 조회·로딩 사이에 들어온 이벤트도 readiness 전에 조정한다.
                while self._pending:
                    failed = False
                    for name, version in list(self._pending.items()):
                        try:
                            await self._registry.load(version)
                        except RevisionConflict:
                            logger.warning("Conflicting model event ignored")
                        except Exception as exc:
                            # 한 모델의 장애가 다른 이름의 버전 교체를 막지 않는다.
                            logger.warning("Model update retry error_type=%s", type(exc).__name__)
                            failed = True
                            continue
                        if self._pending.get(name) == version:
                            del self._pending[name]
                    if failed:
                        raise RuntimeError("pending model update failed")
                self.ready = True
                self._changed.clear()
                await self._changed.wait()
                continue
            except Exception as exc:
                logger.warning("Model startup retry error_type=%s", type(exc).__name__)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), self._retry_interval)

    async def is_ready(self) -> bool:
        return self.ready

    async def close(self) -> None:
        self.ready = False
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
