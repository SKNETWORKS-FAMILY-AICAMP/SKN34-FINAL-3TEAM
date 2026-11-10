"""Idempotent report deletion completion callback; queue retry owns failures."""

from uuid import UUID

import httpx

from app.generation.pipeline import StudentDisplayName
from app.generation.records import RecordContractError
from app.generation.template_settings import validate_snapshot


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
        if (
            profile.get("studentId") != str(student_id)
            or not isinstance(profile.get("nickname"), str)
            or not profile["nickname"].strip()
        ):
            raise RecordContractError("Invalid student profile")
        settings = await self._client.get(f"/internal/students/{student_id}/report-template")
        settings.raise_for_status()
        return StudentDisplayName(
            student_id=UUID(profile["studentId"]),
            nickname=profile["nickname"],
            parent_sharing_enabled=sharing,
            template_snapshot=validate_snapshot(settings.json()),
            grade=profile.get("grade") if type(profile.get("grade")) is int else None,
        )

    async def report_deletion_completed(self, request_id: UUID):
        response = await self._client.post(
            f"/internal/deletion-requests/{request_id}/completions", json={"service": "report"}
        )
        response.raise_for_status()
