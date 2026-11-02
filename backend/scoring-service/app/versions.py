"""scoring에 로딩 완료한 모델 버전만 조회."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.model_registry import ModelRegistry

router = APIRouter(prefix="/internal", tags=["versions"])


class ModelVersionSummary(BaseModel):
    name: str
    version: str
    revision: int = Field(ge=1)


class VersionsResponse(BaseModel):
    items: list[ModelVersionSummary]


@router.get("/versions")
async def versions(request: Request) -> VersionsResponse:
    registry: ModelRegistry = request.app.state.model_registry
    return VersionsResponse(items=registry.versions())
