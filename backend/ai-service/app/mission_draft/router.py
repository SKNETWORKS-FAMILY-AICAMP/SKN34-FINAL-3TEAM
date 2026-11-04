from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.llm.base import LlmClient
from app.llm.providers import get_llm
from app.mission_draft.models import MissionDraftRequest, MissionDraftResponse
from app.mission_draft.service import MissionDraftService

router = APIRouter(prefix="/internal/mission-drafts", tags=["mission-draft"])


def get_mission_draft_service(
    request: Request, llm: Annotated[LlmClient, Depends(get_llm)]
) -> MissionDraftService:
    return MissionDraftService(llm, get_settings(), request.app.state.active_versions)


@router.post("", response_model=MissionDraftResponse)
async def create_mission_draft(
    body: MissionDraftRequest,
    service: Annotated[MissionDraftService, Depends(get_mission_draft_service)],
) -> MissionDraftResponse:
    return await service.generate(body)
