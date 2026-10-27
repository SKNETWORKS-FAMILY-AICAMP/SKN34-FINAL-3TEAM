from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.followup.models import FollowupRequest, FollowupResponse
from app.followup.service import FollowupService
from app.llm.base import LlmClient
from app.llm.providers import get_llm

router = APIRouter(prefix="/internal/followups", tags=["followup"])


def get_followup_service(llm: Annotated[LlmClient, Depends(get_llm)]) -> FollowupService:
    return FollowupService(llm, get_settings())


@router.post("", response_model=FollowupResponse)
async def create_followup(
    body: FollowupRequest, service: Annotated[FollowupService, Depends(get_followup_service)]
) -> FollowupResponse:
    return await service.create(body)
