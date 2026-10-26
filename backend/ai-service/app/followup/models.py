"""POST /internal/followups 요청·응답 (API 명세서 4.2). JSON 필드는 camelCase."""

from typing import Literal

from pydantic import Field

from app.judgment.models import ApiModel, HeldReason, JudgmentResult

FollowupType = Literal["ONE_STEP_MORE", "TELL_MORE", "LOOK_AGAIN"]
ThinkingType = Literal["ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT"]


class TimelineItem(ApiModel):
    """현재 학습 시도의 제출 답변·되묻기 질문 (순서대로, 다른 시도 제외)."""

    kind: Literal["ANSWER", "FOLLOWUP"]
    text: str


class ElementResult(ApiModel):
    element_id: str
    satisfied: bool


class JudgmentSummary(ApiModel):
    result: JudgmentResult
    held_reason: HeldReason | None = None
    elements: list[ElementResult] = Field(default_factory=list)


class FollowupRubricElement(ApiModel):
    element_id: str
    label: str
    description: str | None = None
    good_thought: bool = False


class FollowupRubric(ApiModel):
    elements: list[FollowupRubricElement] = Field(min_length=1)
    # 유출 검사 입력 (FN-JDG-06). 정답 키·금지어는 LLM에 "쓰지 말 표현"으로 전달,
    # 예시 답은 LLM에 보내지 않고 코드 검사에만 사용
    answer_key: list[str] | None = None
    forbidden_terms: list[str] | None = None
    example_answer: str | None = None


class Mission(ApiModel):
    title: str
    question: str
    thinking_type: ThinkingType


class FollowupRequest(ApiModel):
    timeline: list[TimelineItem] = Field(min_length=1)
    judgment: JudgmentSummary
    rubric: FollowupRubric
    mission: Mission


class LeakCheck(ApiModel):
    passed: bool


class LlmVersions(ApiModel):
    model: str
    prompt: str


class FollowupResponse(ApiModel):
    type: FollowupType
    question: str
    source: Literal["LLM", "LLM_RETRY"]
    leak_check: LeakCheck
    versions: LlmVersions
