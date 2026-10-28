"""Internal report models; these do not define the #42 message payload contract."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID


class ReportStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ReportState(StrEnum):
    OK = "OK"
    NO_RECORD = "NO_RECORD"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


@dataclass(frozen=True)
class GenerateReport:
    job_id: UUID
    student_id: UUID
    period_from: date
    period_to: date
    trigger: str
    narrative_enabled: bool
    requested_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.period_from > self.period_to:
            raise ValueError("Report period is reversed")
        if not self.trigger:
            raise ValueError("Report trigger is required")
        if self.requested_at is not None and self.requested_at.utcoffset() is None:
            raise ValueError("Report request time must have an offset")


@dataclass(frozen=True)
class WeeklyReport:
    id: UUID
    job_id: UUID
    student_id: UUID
    period_from: date
    period_to: date
    revision: int
    status: ReportStatus
    state: ReportState | None


@dataclass(frozen=True)
class GenerationResult:
    state: ReportState
    inclusion_rule: str | None = None


@dataclass(frozen=True)
class ReportEvent:
    event_type: str
    report: WeeklyReport
    failure_reason: str | None = None


class JobConflict(ValueError):
    """A job ID was reused for a different student or period."""


class GenerationBusy(RuntimeError):
    """Another worker owns the job; let EventConsumer retry the delivery."""
