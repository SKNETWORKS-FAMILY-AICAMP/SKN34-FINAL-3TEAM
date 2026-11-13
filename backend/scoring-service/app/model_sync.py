"""구독 세션별 snapshot 조회·revision 조정. 소비자는 검증한 이벤트를 offer로만 넘긴다."""

from app.clients.core_client import CoreClient
from app.model_registry import ModelRegistry
from app.model_startup import ModelStartup
from app.model_versions import scoring_versions


class ModelSync:
    def __init__(self, core: CoreClient, registry: ModelRegistry, retry_interval: float) -> None:
        self._core = core
        self._registry = registry
        self._retry_interval = retry_interval
        self._startup: ModelStartup | None = None

    def reset(self) -> None:
        """새 구독마다 이전 조정 상태 없이 시작한다. 큐 소비 전에 불러 수신 이벤트를 보존한다."""
        self._startup = ModelStartup(self._core, self._registry, self._retry_interval)

    def start(self) -> None:
        """큐 바인딩·소비 시작 후 snapshot 조회와 로딩을 시작한다."""
        if self._startup is not None:
            self._startup.start()

    async def stop(self) -> None:
        if self._startup is not None:
            await self._startup.close()

    async def is_ready(self) -> bool:
        return self._startup is not None and await self._startup.is_ready()

    def offer(self, data: dict[str, object]) -> None:
        """scoring 대상 MODEL만 이름별 최신 revision으로 보존·적용한다."""
        for version in scoring_versions({"items": [data]}):
            if self._startup is not None:
                self._startup.offer(version)
