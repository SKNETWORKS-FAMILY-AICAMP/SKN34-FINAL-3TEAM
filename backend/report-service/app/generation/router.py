from dataclasses import asdict
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field

from app.database import run_db
from app.errors import problem_responses
from app.generation.locking import JobLocks
from app.generation.models import PeriodType
from app.generation.reconciliation import ReconciliationService

router = APIRouter(
    prefix="/internal/report-jobs",
    tags=["report-jobs"],
    dependencies=[Security(APIKeyHeader(name="X-Internal-Token", auto_error=False))],
)


class ReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: UUID = Field(alias="studentId")
    period_from: date = Field(alias="periodFrom")
    period_to: date = Field(alias="periodTo")
    period_type: PeriodType = Field(default=PeriodType.WEEKLY, alias="periodType")


class ReconcileResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    student_id: UUID = Field(alias="studentId")
    period_from: date = Field(alias="periodFrom")
    period_to: date = Field(alias="periodTo")
    job_id: UUID = Field(alias="jobId")
    status: Literal["BUSY", "COMPLETED", "FAILED"]
    report_id: UUID | None = Field(alias="reportId")
    failure_reason: str | None = Field(alias="failureReason", pattern=r"^[A-Z][A-Z0-9_]{0,99}$")


@router.post(
    "/{job_id}/reconcile",
    response_model=ReconcileResponse,
    responses=problem_responses(400, 401, 403)
    | {409: problem_responses(409)[409] | {"description": "REPORT_JOB_IDENTITY_MISMATCH"}},
)
async def reconcile(job_id: UUID, body: ReconcileRequest, request: Request, response: Response):
    service = ReconciliationService(
        request.app.state.session_factory, JobLocks(request.app.state.engine)
    )
    result = await run_db(
        lambda: service.reconcile(
            job_id, body.student_id, body.period_from, body.period_to, body.period_type
        )
    )
    response.headers["Cache-Control"] = "no-store"
    payload = asdict(result)
    payload.pop("period_type", None)
    return payload
