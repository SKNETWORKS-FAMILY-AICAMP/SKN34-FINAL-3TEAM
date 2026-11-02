"""POST /internal/report-narratives 요청·응답 (API 명세서 4.2·4.2.1). JSON 필드는 camelCase.

입력 항목은 리포트 상세(3.4)·Metric(1.6)과 같은 형태. report가 계산·조회한 값을 그대로 받음.
"""

from datetime import date
from typing import Literal

from pydantic import Field

from app.followup.models import LlmVersions, ThinkingType
from app.judgment.models import ApiModel

RecordState = Literal["OK", "INSUFFICIENT_SAMPLE", "NO_RECORD"]


class Period(ApiModel):
    from_: date = Field(alias="from")
    to: date


class Metric(ApiModel):
    label: str
    value: float | None = None  # 분모 5 미만이면 null, 개수만 사용 (P08)
    count: int
    numerator: int
    denominator: int
    formula: str
    period: Period
    source_type: str = "RECORD"
    state: RecordState


class MissionRef(ApiModel):
    attempt_id: str
    title: str


class ThinkingTypeSummary(ApiModel):
    type: ThinkingType
    state: RecordState
    missions: list[MissionRef] = Field(default_factory=list)


class AnswerText(ApiModel):
    answer_id: str
    text: str


class ChangeCounts(ApiModel):
    """[최초, 마지막] 답변 값 (P08)."""

    chars: list[int] = Field(min_length=2, max_length=2)
    sentences: list[int] = Field(min_length=2, max_length=2)
    reason_connectives: list[int] = Field(min_length=2, max_length=2)


class Change(ApiModel):
    attempt_id: str
    followup: str | None = None
    first: AnswerText
    revised: AnswerText
    counts: ChangeCounts


class Reflection(ApiModel):
    attempt_id: str
    difficulty: str | None = None
    text: str | None = None
    written: bool


class Quote(ApiModel):
    """인용 후보. report가 보내는 `verified`는 대조 전 값이라 받지 않음."""

    attempt_id: str
    answer_id: str
    answer_version: int = Field(ge=1)
    text: str


class NarrativeRequest(ApiModel):
    metrics: list[Metric]
    thinking_types: list[ThinkingTypeSummary]
    changes: list[Change]
    reflections: list[Reflection]
    quotes: list[Quote]  # 인용 후보. citedQuotes는 이 안에서만 선택


class Narrative(ApiModel):
    text: str
    source: Literal["LLM"] = "LLM"  # 대조 실패 시 TEMPLATE 전환은 report (P16)
    model_explanation: None = None


class Citation(ApiModel):
    """서술에 옮긴 구절. quote는 같은 답변 원문의 부분 문자열."""

    attempt_id: str
    answer_id: str
    answer_version: int
    quote: str


class NarrativeResponse(ApiModel):
    narrative: Narrative
    evening_question: str
    cited_quotes: list[Citation]
    versions: LlmVersions
