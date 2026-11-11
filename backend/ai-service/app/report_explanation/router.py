from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.llm.base import LlmClient
from app.llm.providers import get_explanation_llm
from app.report_explanation.models import ExplanationRequest, ExplanationResponse
from app.report_explanation.service import ExplanationService

router = APIRouter(prefix="/internal/report-explanations", tags=["report-explanation"])


def get_explanation_service(
    request: Request, llm: Annotated[LlmClient, Depends(get_explanation_llm)]
) -> ExplanationService:
    return ExplanationService(llm, get_settings(), request.app.state.active_versions)


@router.post("", response_model=ExplanationResponse)
async def create_report_explanation(
    body: ExplanationRequest,
    service: Annotated[ExplanationService, Depends(get_explanation_service)],
) -> ExplanationResponse:
    return await service.explain(body)
