from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.llm.base import LlmClient
from app.llm.providers import get_llm
from app.memory_query.models import MemoryQueryRequest, MemoryQueryResponse
from app.memory_query.service import MemoryQueryService

router = APIRouter(prefix="/internal/memory-queries", tags=["memory-query"])


def get_memory_query_service(
    request: Request, llm: Annotated[LlmClient, Depends(get_llm)]
) -> MemoryQueryService:
    return MemoryQueryService(llm, get_settings(), request.app.state.active_versions)


@router.post("", response_model=MemoryQueryResponse)
async def create_memory_query(
    body: MemoryQueryRequest,
    service: Annotated[MemoryQueryService, Depends(get_memory_query_service)],
) -> MemoryQueryResponse:
    return await service.rewrite(body)
