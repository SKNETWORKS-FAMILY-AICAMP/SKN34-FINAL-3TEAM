"""POST /internal/analysis/stream (SSE, API 명세서 3.3·4.2).

POST /internal/analysis/report-template (#209). 이벤트 순서·취소 동작은 service.py 참고.
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.analysis_agent.models import AnalysisRequest
from app.analysis_agent.service import AnalysisService
from app.analysis_agent.template_settings import TemplateProposal, TemplateProposalRequest
from app.config import get_settings
from app.llm.base import LlmClient
from app.llm.providers import get_llm
from app.security import UserContext, get_user_context

router = APIRouter(prefix="/internal/analysis", tags=["analysis"])


def get_analysis_service(
    request: Request, llm: Annotated[LlmClient, Depends(get_llm)]
) -> AnalysisService:
    return AnalysisService(llm, get_settings(), request.app.state.active_versions)


@router.post("/stream")
async def stream(
    body: AnalysisRequest,
    user: Annotated[UserContext, Depends(get_user_context)],
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
) -> StreamingResponse:
    events = service.stream(body, user)
    return StreamingResponse(
        (sse(name, data) async for name, data in events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def sse(event: str, data: BaseModel | dict[str, Any]) -> str:
    payload = data.model_dump(mode="json", by_alias=True) if isinstance(data, BaseModel) else data
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/report-template", response_model=TemplateProposal)
async def report_template(
    body: TemplateProposalRequest,
    user: Annotated[UserContext, Depends(get_user_context)],
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
) -> TemplateProposal:
    return await service.propose_template(body, user)
