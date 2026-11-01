from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Security
from fastapi.security import APIKeyHeader

from app.config import get_settings
from app.errors import problem_responses
from app.generation.models import ReportStatus
from app.query.schemas import Download, EvidencePage, ReportDetail, ReportPage
from app.query.service import QueryService

router = APIRouter(
    prefix="/internal/reports",
    tags=["reports"],
    dependencies=[Security(APIKeyHeader(name="X-Internal-Token", auto_error=False))],
)


async def query_service(request: Request):
    settings = get_settings()
    return QueryService(
        request.app.state.session_factory,
        request.app.state.learning_client,
        lambda: request.app.state.storage,
        settings.report_download_ttl_seconds,
    )


Service = Annotated[QueryService, Depends(query_service)]
NarrativeEnabled = Annotated[bool, Header(alias="X-Report-Narrative-Enabled")]


@router.get(
    "",
    response_model=ReportPage,
    response_model_exclude_unset=True,
    responses=problem_responses(400, 401, 403, 409),
)
async def list_reports(
    service: Service,
    student_id: Annotated[UUID, Query(alias="studentId")],
    status: ReportStatus | None = None,
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
):
    return await service.list(student_id, status, page, size)


@router.get(
    "/{report_id}",
    response_model=ReportDetail,
    response_model_exclude_unset=True,
    responses=problem_responses(400, 401, 403, 404, 409),
)
async def detail(
    report_id: UUID,
    service: Service,
    narrative_enabled: NarrativeEnabled = False,
    revision: int | None = Query(None, ge=1),
):
    return await service.detail(report_id, revision, narrative_enabled)


@router.get(
    "/{report_id}/evidence/{item_id}",
    response_model=EvidencePage,
    response_model_exclude_unset=True,
    responses=problem_responses(400, 401, 403, 404, 409, 503),
)
async def evidence(report_id: UUID, item_id: UUID, service: Service):
    return await service.evidence(report_id, item_id)


@router.get(
    "/{report_id}/files/{format}",
    response_model=Download,
    response_model_exclude_unset=True,
    responses=problem_responses(400, 401, 403, 404, 409, 503),
)
async def file(
    report_id: UUID,
    format: Literal["pdf", "md", "html"],
    service: Service,
    narrative_enabled: NarrativeEnabled = False,
):
    return await service.file(report_id, format, narrative_enabled)
