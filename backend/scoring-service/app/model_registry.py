"""모델 단위 revision·승인 범위·완료 후 교체. snapshot과 이벤트가 함께 사용한다."""

import asyncio
import logging
from collections.abc import Callable

from starlette.concurrency import run_in_threadpool

from app.model_loader import LoadedModel
from app.model_versions import ActiveModelVersion

logger = logging.getLogger(__name__)


class RevisionConflict(ValueError):
    """같은 revision에 상충하는 메타데이터가 전달됨."""


class ModelRegistry:
    def __init__(self, loader: Callable[[ActiveModelVersion], LoadedModel]) -> None:
        self._loader = loader
        self._models: dict[str, LoadedModel] = {}
        self._desired: dict[str, ActiveModelVersion] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, name: str, scope: str) -> LoadedModel | None:
        model = self._models.get(name)
        desired = self._desired.get(name)
        if (
            model is None
            or desired is None
            or scope not in model.metadata.scopes
            or scope not in desired.scopes
        ):
            return None
        return model

    def is_active(self, name: str, scope: str) -> bool:
        return self.get(name, scope) is not None

    def versions(self) -> list[dict[str, str | int]]:
        return [
            {"name": name, "version": model.metadata.version, "revision": model.metadata.revision}
            for name, model in sorted(self._models.items())
        ]

    async def load(self, version: ActiveModelVersion) -> bool:
        name = version.name
        desired = self._desired.get(name)
        if desired is not None:
            if version.revision < desired.revision:
                return False
            if version.revision == desired.revision and version != desired:
                raise RevisionConflict("conflicting metadata for same revision")
        self._desired[name] = version
        lock = self._locks.setdefault(name, asyncio.Lock())
        async with lock:
            if self._desired.get(name) != version:
                return False
            current = self._models.get(name)
            if current is not None and current.metadata.revision == version.revision:
                return False
            # 다운로드·CPU 로딩이 이벤트 루프를 막지 않는다. 실패 시 기존 모델 그대로 유지.
            loaded = await run_in_threadpool(self._loader, version)
            if loaded.metadata != version:
                raise ValueError("loaded model metadata mismatch")
            if self._desired.get(name) != version:
                return False
            self._models[name] = loaded
            logger.info("Model loaded name=%s revision=%s", name, version.revision)
            return True

    async def replace(self, versions: list[ActiveModelVersion]) -> None:
        # 전체 snapshot을 전달한다. 실패가 나도 다른 모델의 로딩을 계속한다.
        names = {version.name for version in versions}
        if len(names) != len(versions):
            raise ValueError("duplicate active model")
        # 초기 재시도 사이 snapshot에서 빠진 항목을 활성으로 남기지 않는다.
        for name in set(self._desired) - names:
            self._desired.pop(name, None)
            self._models.pop(name, None)
        failed = False
        for version in versions:
            try:
                await self.load(version)
            except Exception as exc:
                # 예외 본문에는 URI·자격 증명 등이 들어갈 수 있어 유형만 남긴다.
                logger.warning("Model load failed error_type=%s", type(exc).__name__)
                failed = True
        if failed:
            raise RuntimeError("model snapshot loading failed")
