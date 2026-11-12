from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.llm.base import LlmClient
from app.llm.providers import get_llm
from app.memory_explanation.models import MemoryExplanationRequest, MemoryExplanationResponse
from app.memory_explanation.service import MemoryExplanationService

router = APIRouter(prefix="/internal/memory-explanations", tags=["memory-explanation"])


def get_memory_explanation_service(
    request: Request, llm: Annotated[LlmClient, Depends(get_llm)]
) -> MemoryExplanationService:
    return MemoryExplanationService(llm, get_settings(), request.app.state.active_versions)


@router.post("", response_model=MemoryExplanationResponse)
async def create_memory_explanation(
    body: MemoryExplanationRequest,
    service: Annotated[MemoryExplanationService, Depends(get_memory_explanation_service)],
) -> MemoryExplanationResponse:
    return await service.explain(body)
