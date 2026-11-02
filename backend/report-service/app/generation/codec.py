"""#42 v1 payload adapter; canonical contracts remain in contracts/events/."""

import re
from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator

from app.generation.models import GenerateReport, ReportEvent, ReportStatus
from app.messaging.contracts import InvalidEvent, uuid_text
from app.messaging.envelope import EventEnvelope


class GenerateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobId: UUID
    studentId: UUID
    periodFrom: date
    periodTo: date
    trigger: Literal["SCHEDULE", "REGENERATE", "ADMIN_RETRY"]
    narrativeEnabled: StrictBool

    @field_validator("jobId", "studentId", mode="before")
    @classmethod
    def uuid_field(cls, value):
        return uuid_text(value)

    @field_validator("periodFrom", "periodTo", mode="before")
    @classmethod
    def date_field(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Expected ISO date")
        return date.fromisoformat(value)


class ReportV1Codec:
    def decode(self, envelope) -> GenerateReport:
        try:
            if (envelope.type, envelope.source, envelope.dataschema) != (
                "report.generate",
                "core-service",
                "report.generate.v1",
            ):
                raise ValueError("Unsupported message identity")
            data = GenerateData.model_validate(envelope.data)
            if uuid_text(envelope.subject) != data.studentId:
                raise ValueError("Student identity mismatch")
            if data.periodFrom.weekday() != 0 or data.periodTo != data.periodFrom + timedelta(
                days=6
            ):
                raise ValueError("Expected a Monday-to-Sunday period")
            if envelope.time.utcoffset() is None:
                raise ValueError("Missing time offset")
            return GenerateReport(
                data.jobId,
                data.studentId,
                data.periodFrom,
                data.periodTo,
                data.trigger,
                data.narrativeEnabled,
                requested_at=envelope.time,
            )
        except (ValueError, TypeError, AttributeError, OverflowError):
            raise InvalidEvent("Invalid report.generate v1 contract") from None

    def encode(self, event: ReportEvent, traceparent: str | None):
        statuses = {
            "report.started": ReportStatus.RUNNING,
            "report.completed": ReportStatus.COMPLETED,
            "report.failed": ReportStatus.FAILED,
        }
        if statuses.get(event.event_type) != event.report.status:
            raise ValueError("Lifecycle type and state mismatch")
        data = {
            "jobId": str(event.report.job_id),
            "studentId": str(event.report.student_id),
            "reportId": str(event.report.id),
        }
        if event.event_type == "report.failed":
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", event.failure_reason or ""):
                raise ValueError("Failure reason must be a safe error code")
            data["failureReason"] = event.failure_reason
        elif event.failure_reason is not None:
            raise ValueError("Only failed events carry a failure reason")
        return EventEnvelope(
            type=event.event_type,
            source="report-service",
            subject=str(event.report.student_id),
            dataschema=f"{event.event_type}.v1",
            traceparent=traceparent,
            data=data,
        )
