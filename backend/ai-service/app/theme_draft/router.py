from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.llm.providers import get_theme_llms, theme_llm_problem
from app.theme_draft.models import ThemeDraftRequest, ThemeDraftResponse
from app.theme_draft.service import (
    NotReadyRunner,
    ThemeDraftGraphRunner,
    ThemeDraftRunner,
    ThemeDraftService,
)

router = APIRouter(prefix="/internal/theme-drafts", tags=["theme-draft"])


def get_theme_draft_runner(request: Request) -> ThemeDraftRunner:
    """테마 모델 설정이 틀리면 이 경로만 503. 다른 경로는 그대로 동작한다."""
    settings = get_settings()
    if problem := theme_llm_problem(settings):
        return NotReadyRunner(problem)
    llm, review_llm = get_theme_llms(request)
    state = request.app.state
    # 그림·영상·저장소는 기동 때 만든 것(없으면 None: 그 단계를 건너뛰고 경고)
    return ThemeDraftGraphRunner(
        llm,
        review_llm,
        settings,
        state.active_versions,
        image=getattr(state, "theme_image", None),
        video=getattr(state, "theme_video", None),
        storage=getattr(state, "theme_storage", None),
    )


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
