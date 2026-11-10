"""Report query responses, matching API 1.6/3.4 with explicit null/absence handling."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.generation.models import PeriodType, ReportState, ReportStatus
from app.generation.records import ThinkingType
from app.generation.template_settings import TemplateSettings
from app.generation.theme_summary import ThemeSummary


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
    answer_id: UUID | None = None
    text: str | None


class Change(ItemResponse):
    attempt_id: UUID
    followup: str | None = Field(
        description="원문 되묻기. 없으면 null이며 질문을 만들어 채우지 않음."
    )
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
    difficulty: Literal["쉬웠어요", "보통", "어려웠어요"] | None = Field(
        description="표시용 난이도. 내부 EASY/NORMAL/HARD 코드와 구분하며 미작성은 null."
    )
    text: str | None


class Quote(ItemResponse):
    attempt_id: UUID
    answer_id: UUID
    text: str | None
    verified: bool


class Revision(Response):
    revision: int = Field(ge=1)
    generated_at: AwareDatetime | None


class DailyFollowup(Response):
    question: str
    answer: str | None


class DailyElement(Response):
    label: str
    satisfied: bool


class DailyReflection(Response):
    written: bool
    difficulty: str | None
    text: str | None


class DailyQuote(Response):
    answer_id: UUID
    text: str
    verified: bool


class DailyProblem(ItemResponse):
    mission_id: UUID
    attempt_id: UUID
    title: str
    context: Literal["THEME_DAY", "THEME_REVIEW", "EXTRA"] | None
    judgment: Literal["CORRECT", "PARTIAL", "RETHINK", "HELD"] | None
    followups: list[DailyFollowup]
    final_answer: str | None
    elements: list[DailyElement]
    reflection: DailyReflection
    quotes: list[DailyQuote]


class ReportSummary(Response):
    period_type: PeriodType = PeriodType.WEEKLY
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


class TemplateSnapshot(Response):
    settings: TemplateSettings
    revision: int = Field(ge=0)


class Versions(Response):
    template: TemplateSnapshot | None = None
    prompt: str | None
    model: str | None


class ReportDetail(ReportSummary):
    explanations: "ReportExplanations | None" = None
    problems: list[DailyProblem] = Field(default_factory=list)
    theme_summary: ThemeSummary | None = None
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


class ReportExplanation(Response):
    attempt_id: UUID
    answer_id: UUID
    answer_version: int = Field(ge=1)
    mission_title: str
    thinking_type: ThinkingType
    quote: str | None
    text: str


class ReportExplanations(Response):
    state: Literal["INCLUDED", "NOT_INCLUDED", "NO_TARGET"]
    items: list[ReportExplanation] = Field(max_length=3)


class Evidence(Response):
    attempt_id: UUID
    answer_id: UUID
    answer_version: int
    available: bool
    quote: str | None = None
    mission_title: str | None = None
    submitted_at: AwareDatetime | None = None


class CorrectionImpactItem(Response):
    report_id: UUID
    period_type: PeriodType
    period_from: date
    revision: int


class CorrectionImpact(Response):
    items: list[CorrectionImpactItem]


class EvidencePage(Response):
    items: list[Evidence]


class Download(Response):
    url: str
    expires_at: AwareDatetime
