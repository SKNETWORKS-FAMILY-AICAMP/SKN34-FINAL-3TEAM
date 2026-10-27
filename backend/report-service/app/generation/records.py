"""Normalized records for P06/P08. No HTTP framework or student draft/memo fields."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from uuid import UUID

KST = timezone(timedelta(hours=9))


class ThinkingType(StrEnum):
    ANALYZE = "ANALYZE"
    EVALUATE = "EVALUATE"
    CREATE = "CREATE"
    SOLVE = "SOLVE"
    REFLECT = "REFLECT"


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError("Report period is reversed")

    def includes(self, instant: datetime) -> bool:
        if instant.utcoffset() is None:
            raise ValueError("Record timestamps must have an offset")
        return self.start <= instant.astimezone(KST).date() <= self.end

    def at_or_before_end(self, instant: datetime) -> bool:
        if instant.utcoffset() is None:
            raise ValueError("Record timestamps must have an offset")
        return instant < datetime.combine(self.end + timedelta(days=1), time(), KST)

    def payload(self) -> dict[str, str]:
        return {"from": self.start.isoformat(), "to": self.end.isoformat()}


@dataclass(frozen=True)
class AnswerRecord:
    id: UUID
    version: int
    submitted_at: datetime
    text: str | None
    process_status: str


@dataclass(frozen=True)
class ReflectionRecord:
    difficulty: str
    text: str | None
    created_at: datetime


@dataclass(frozen=True)
class AttemptRecord:
    id: UUID
    student_id: UUID
    mission_title: str
    thinking_type: ThinkingType
    status: str
    answers: tuple[AnswerRecord, ...]
    hint_opened_at: tuple[datetime, ...]
    completed_at: datetime | None = None
    reflection: ReflectionRecord | None = None


@dataclass(frozen=True)
class ThinkingMission:
    type: ThinkingType
    attempt_id: UUID
    title: str


@dataclass(frozen=True)
class ChangePair:
    attempt_id: UUID
    followup: str
    first_answer_id: UUID
    first_text: str
    revised_answer_id: UUID
    revised_text: str


@dataclass(frozen=True)
class LearningRecords:
    student_id: UUID
    period: Period
    attempts: tuple[AttemptRecord, ...]
    thinking_missions: tuple[ThinkingMission, ...]
    changes: tuple[ChangePair, ...]


class RecordContractError(ValueError):
    """Incomplete/inconsistent upstream records must never become a NO_RECORD result."""


@dataclass(frozen=True)
class EvidenceRecord:
    answer_id: UUID
    attempt_id: UUID
    version: int
    text: str | None
    available: bool
    mission_title: str | None = None
    submitted_at: datetime | None = None
