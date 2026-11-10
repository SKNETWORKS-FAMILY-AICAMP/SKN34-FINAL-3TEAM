from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.theme_draft.models import ThemeDraftRequest, ThemeDraftResponse
from app.theme_draft.service import NotReadyRunner, ThemeDraftRunner, ThemeDraftService

router = APIRouter(prefix="/internal/theme-drafts", tags=["theme-draft"])


def get_theme_draft_runner() -> ThemeDraftRunner:
    return NotReadyRunner()


def get_theme_draft_service(
    runner: Annotated[ThemeDraftRunner, Depends(get_theme_draft_runner)],
) -> ThemeDraftService:
    return ThemeDraftService(runner, get_settings())


@router.post("", response_model=ThemeDraftResponse)
async def create_theme_draft(
    body: ThemeDraftRequest,
    service: Annotated[ThemeDraftService, Depends(get_theme_draft_service)],
) -> ThemeDraftResponse:
    return await service.generate(body)
