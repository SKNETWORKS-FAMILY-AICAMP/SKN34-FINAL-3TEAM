"""POST /internal/analysis/stream 요청·응답과 learning 기록 형태 (API 명세서 1.6·3.3·4.2).

result에서 messageId·scope.changed는 core가 붙임 (ai는 대화 저장소를 모름).
"""

from datetime import date
from typing import Literal

from pydantic import ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from app.judgment.models import ApiModel

Intent = Literal[
    "COUNT",  # 숫자 (몇 번·몇 개)
    "THINKING_TYPES",  # 유형별 활동
    "CHILD_THOUGHTS",  # 아이가 쓴 생각
    "CHANGES",  # 되묻기 전후 변화
    "REFLECTIONS",  # 돌아보기
    "MATH_CHECK",  # 수학 점검 (M1 활성 범위에서만, 현재 미제공)
    "OTHER",  # 기록 분석 밖 질문
]
ScopeIssue = Literal["NONE", "OTHER_CHILD", "DIFFERENT_PERIOD", "UNCLEAR"]
FallbackReason = Literal["VERIFICATION_FAILED", "AI_UNAVAILABLE"]
QueryState = Literal["OK", "NO_RECORD", "INSUFFICIENT_SAMPLE", "PROCESSING", "FAILED"]


# ---------------------------------------------------------------------------
# 요청 (core → ai)
# ---------------------------------------------------------------------------


class Scope(ApiModel):
    """core가 권한·범위를 확인해 넘긴 자녀·기간. 그래프는 이 값만 조회에 씀 (FN-AGT-03)."""

    student_id: str = Field(min_length=1)
    from_: date = Field(alias="from")
    to: date

    @model_validator(mode="after")
    def _ordered(self) -> "Scope":
        if self.from_ > self.to:
            raise ValueError("from은 to보다 늦을 수 없음")
        return self


class Turn(ApiModel):
    """같은 대화의 이전 질문·답변. 맥락 파악에만 쓰고 이전 범위의 기록은 섞지 않음 (FN-AGT-08)."""

    role: Literal["USER", "ASSISTANT"]
    text: str


class AnalysisRequest(ApiModel):
    conversation_id: str
    question: str = Field(min_length=1, max_length=1000)
    scope: Scope
    history: list[Turn] = Field(default_factory=list, max_length=20)


# ---------------------------------------------------------------------------
# 응답 (SSE event: result)
# ---------------------------------------------------------------------------


class Period(ApiModel):
    from_: date = Field(alias="from")
    to: date


class Metric(ApiModel):
    label: str
    value: float | None  # 분모 5 미만이면 null (P08)
    count: int
    numerator: int | None
    denominator: int | None
    formula: str
    period: Period
    source_type: Literal["RECORD"] = "RECORD"
    state: QueryState


class Evidence(ApiModel):
    attempt_id: str
    mission_title: str
    answer_id: str | None  # 돌아보기 인용은 답변 ID 없음
    answer_version: int | None
    submitted_at: str | None
    quote: str
    available: bool = True


class Verification(ApiModel):
    numbers_matched: bool
    quotes_matched: bool
    content_allowed: bool  # 레벨·등급·사고력 단정 표현 없음 (report 검증 메타데이터와 같은 이름)


class Fallback(ApiModel):
    reason: FallbackReason


class ResultScope(ApiModel):
    child_id: str
    from_: date = Field(alias="from")
    to: date


class LlmVersions(ApiModel):
    model: str | None
    prompt: str


class AnalysisResult(ApiModel):
    answer: str
    source: Literal["LLM", "TEMPLATE"]
    fallback: Fallback | None
    scope: ResultScope
    metrics: list[Metric]
    evidence: list[Evidence]
    verification: Verification | None  # LLM 답변을 검사하지 않은 경우 null
    record_count: int
    versions: LlmVersions


class Clarification(ApiModel):
    """범위 확인 요청. 보낸 뒤 스트림 종료, 사용자 선택을 scope에 담아 다시 질문 (API 3.3)."""

    reason: Literal["OTHER_CHILD", "DIFFERENT_PERIOD", "UNCLEAR"]
    message: str
    current: ResultScope


class StreamError(ApiModel):
    code: str
    message: str
    retryable: bool


# ---------------------------------------------------------------------------
# learning 기록 (API 4.1·4.1.1 구현안, learning 구현 전이라 필요한 필드만 읽음)
# ---------------------------------------------------------------------------


class RecordModel(ApiModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class AnswerFeedback(RecordModel):
    status: Literal["PENDING", "RUNNING", "DONE", "FAILED"]


class RecordAnswer(RecordModel):
    answer_id: str
    version: int
    submitted_at: str  # ISO-8601 오프셋 포함
    text: str | None
    feedback: AnswerFeedback | None = None


class HintUsage(RecordModel):
    opened_at: str


class Reflection(RecordModel):
    difficulty: Literal["EASY", "NORMAL", "HARD"]
    text: str | None = None
    created_at: str | None = None


class MissionRef(RecordModel):
    title: str
    thinking_type: str


class RecordAttempt(RecordModel):
    attempt_id: str
    available: bool = True  # 삭제 표식 {attemptId, available:false}
    mission: MissionRef | None = None
    status: Literal["IN_PROGRESS", "COMPLETED"] | None = None
    answers: list[RecordAnswer] = Field(default_factory=list)
    hint_usages: list[HintUsage] = Field(default_factory=list)
    completed_at: str | None = None
    reflection: Reflection | None = None


class ThinkingTypeMission(RecordModel):
    attempt_id: str
    title: str


class ThinkingTypeItem(RecordModel):
    type: str
    missions: list[ThinkingTypeMission] = Field(default_factory=list)


class ChangeAnswer(RecordModel):
    answer_id: str
    text: str | None


class RecordChange(RecordModel):
    attempt_id: str
    followup: str | None = None
    first: ChangeAnswer
    revised: ChangeAnswer


class Records(RecordModel):
    """도구가 가져온 원본. 질문 유형에 필요한 것만 채워짐."""

    attempts: list[RecordAttempt] = Field(default_factory=list)
    thinking_types: list[ThinkingTypeItem] | None = None
    changes: list[RecordChange] | None = None
