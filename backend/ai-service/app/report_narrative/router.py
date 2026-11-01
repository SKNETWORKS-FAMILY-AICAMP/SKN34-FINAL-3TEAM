from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.llm.base import LlmClient
from app.llm.providers import get_llm
from app.report_narrative.models import NarrativeRequest, NarrativeResponse
from app.report_narrative.service import NarrativeService

router = APIRouter(prefix="/internal/report-narratives", tags=["report-narrative"])


def get_narrative_service(
    request: Request, llm: Annotated[LlmClient, Depends(get_llm)]
) -> NarrativeService:
    return NarrativeService(llm, get_settings(), request.app.state.active_versions)


@router.post("", response_model=NarrativeResponse)
async def create_report_narrative(
    body: NarrativeRequest, service: Annotated[NarrativeService, Depends(get_narrative_service)]
) -> NarrativeResponse:
    return await service.generate(body)
