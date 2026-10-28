"""Internal report models; these do not define the #42 message payload contract."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any
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
    display_name: str | None = None
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
    items: tuple["ReportItem", ...] = ()
    narrative: dict[str, Any] | None = None
    verification: dict[str, bool] | None = None
    versions: dict[str, str | None] | None = None
    evening_question: str | None = None
    generated_at: datetime | None = None
    files: tuple["ReportFile", ...] = ()


@dataclass(frozen=True)
class ReportFile:
    format: str
    key: str
    size_bytes: int


class ItemType(StrEnum):
    METRIC = "METRIC"
    THINKING_TYPE = "THINKING_TYPE"
    CHANGE = "CHANGE"
    REFLECTION = "REFLECTION"
    QUOTE = "QUOTE"


@dataclass(frozen=True)
class EvidenceLink:
    attempt_id: UUID
    answer_id: UUID
    answer_version: int


@dataclass(frozen=True)
class ReportItem:
    type: ItemType
    seq: int
    payload: dict[str, Any]
    state: ReportState
    verified: bool
    evidence: tuple[EvidenceLink, ...] = ()


@dataclass(frozen=True)
class ReportEvent:
    event_type: str
    report: WeeklyReport
    failure_reason: str | None = None


class JobConflict(ValueError):
    """A job ID was reused for a different student or period."""


class GenerationBusy(RuntimeError):
    """Another worker owns the job; let EventConsumer retry the delivery."""
