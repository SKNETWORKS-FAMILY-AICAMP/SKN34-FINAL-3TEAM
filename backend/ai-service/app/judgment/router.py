from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.judgment.models import JudgmentRequest, JudgmentResponse
from app.judgment.service import JudgmentService
from app.llm.base import LlmClient
from app.llm.factory import get_llm

router = APIRouter(prefix="/internal/judgments", tags=["judgment"])


def get_judgment_service(llm: Annotated[LlmClient, Depends(get_llm)]) -> JudgmentService:
    return JudgmentService(llm, get_settings())


@router.post("", response_model=JudgmentResponse)
async def judge(
    body: JudgmentRequest, service: Annotated[JudgmentService, Depends(get_judgment_service)]
) -> JudgmentResponse:
    return await service.judge(body)
