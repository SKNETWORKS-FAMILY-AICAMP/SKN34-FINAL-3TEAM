"""Report query responses, matching API 1.6/3.4 with explicit null/absence handling."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.generation.models import ReportState, ReportStatus
from app.generation.records import ThinkingType


class Response(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PeriodResponse(Response):
    from_: date = Field(alias="from")
    to: date


class ItemResponse(Response):
    item_id: UUID | None = None


class Metric(ItemResponse):
    label: str
    value: float | None
    count: int = Field(ge=0)
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    formula: str
    period: PeriodResponse
    source_type: Literal["RECORD", "RULE", "ANSWER_KEY", "AI_OBSERVATION"]
    state: ReportState


class Mission(Response):
    attempt_id: UUID
    title: str


class Thinking(ItemResponse):
    type: ThinkingType
    state: ReportState
    missions: list[Mission]
    summary: str | None = None


class TextAnswer(Response):
    answer_id: UUID
    text: str


class Change(ItemResponse):
    attempt_id: UUID
    followup: str
    first: TextAnswer
    revised: TextAnswer
    counts: "ChangeCounts"


class ChangeCounts(Response):
    chars: tuple[int, int]
    sentences: tuple[int, int]
    reason_connectives: tuple[int, int]


class Reflection(ItemResponse):
    attempt_id: UUID
    written: bool
    difficulty: str | None
    text: str | None


class Quote(ItemResponse):
    attempt_id: UUID
    answer_id: UUID
    text: str | None
    verified: bool


class Revision(Response):
    revision: int = Field(ge=1)
    generated_at: AwareDatetime | None


class ReportSummary(Response):
    report_id: UUID
    child_id: UUID
    period: PeriodResponse
    revision: int = Field(ge=1)
    status: ReportStatus
    state: ReportState | None


class ReportPage(Response):
    items: list[ReportSummary]
    page: int
    size: int
    total_elements: int


class Narrative(Response):
    text: str
    source: Literal["LLM", "TEMPLATE"]
    model_explanation: str | None = None


class Verification(Response):
    numbers_matched: bool
    quotes_matched: bool
    content_allowed: bool | None = None


class Versions(Response):
    prompt: str | None
    model: str | None


class ReportDetail(ReportSummary):
    revisions: list[Revision]
    inclusion_rule: str | None
    metrics: list[Metric]
    thinking_types: list[Thinking]
    changes: list[Change]
    reflections: list[Reflection]
    quotes: list[Quote]
    evening_question: str | None
    narrative: Narrative | None
    verification: Verification
    versions: Versions
    generated_at: AwareDatetime | None


class Evidence(Response):
    attempt_id: UUID
    answer_id: UUID
    answer_version: int
    available: bool
    quote: str | None = None
    mission_title: str | None = None
    submitted_at: AwareDatetime | None = None


class EvidencePage(Response):
    items: list[Evidence]


class Download(Response):
    url: str
    expires_at: AwareDatetime
