"""Idempotent report deletion completion callback; queue retry owns failures."""

from uuid import UUID

import httpx


class CoreClient:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def report_deletion_completed(self, request_id: UUID):
        response = await self._client.post(
            f"/internal/deletion-requests/{request_id}/completions", json={"service": "report"}
        )
        response.raise_for_status()
