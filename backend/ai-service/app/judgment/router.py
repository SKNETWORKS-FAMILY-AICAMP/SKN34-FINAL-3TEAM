from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.judgment.models import JudgmentRequest, JudgmentResponse
from app.judgment.service import JudgmentService
from app.llm.base import LlmClient
from app.llm.providers import get_llm

router = APIRouter(prefix="/internal/judgments", tags=["judgment"])


def get_judgment_service(
    request: Request, llm: Annotated[LlmClient, Depends(get_llm)]
) -> JudgmentService:
    return JudgmentService(llm, get_settings(), request.app.state.active_versions)


@router.post("", response_model=JudgmentResponse)
async def judge(
    body: JudgmentRequest, service: Annotated[JudgmentService, Depends(get_judgment_service)]
) -> JudgmentResponse:
    return await service.judge(body)
