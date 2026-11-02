"""Idempotent report deletion completion callback; queue retry owns failures."""

from uuid import UUID

import httpx

from app.generation.pipeline import StudentDisplayName


class CoreClient:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def lookup(self, student_id: UUID) -> StudentDisplayName:
        response = await self._client.get(f"/internal/students/{student_id}/profile")
        response.raise_for_status()
        profile = response.json()
        sharing = profile.get("parentSharingEnabled", False)
        if not isinstance(sharing, bool):
            raise ValueError("Invalid student sharing preference")
        return StudentDisplayName(UUID(profile["studentId"]), profile["nickname"], sharing)

    async def report_deletion_completed(self, request_id: UUID):
        response = await self._client.post(
            f"/internal/deletion-requests/{request_id}/completions", json={"service": "report"}
        )
        response.raise_for_status()
