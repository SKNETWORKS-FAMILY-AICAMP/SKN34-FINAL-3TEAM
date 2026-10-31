"""기존 internal_client의 인증·timeout으로 core 활성 버전 snapshot 조회."""

import httpx

from app.versions import ActiveSnapshot, ActiveVersionItem


class CoreClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def active_versions(self) -> list[ActiveVersionItem]:
        response = await self._client.get("/internal/model-versions/active")
        response.raise_for_status()
        return ActiveSnapshot.model_validate(response.json()).items
