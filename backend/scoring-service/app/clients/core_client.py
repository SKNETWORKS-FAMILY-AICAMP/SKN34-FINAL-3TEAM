"""기존 internal_client의 인증·timeout을 사용하는 core 활성 버전 조회."""

import httpx

from app.model_versions import ActiveModelVersion, scoring_versions


class CoreClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def active_versions(self) -> list[ActiveModelVersion]:
        response = await self._client.get("/internal/model-versions/active")
        response.raise_for_status()
        return scoring_versions(response.json())
