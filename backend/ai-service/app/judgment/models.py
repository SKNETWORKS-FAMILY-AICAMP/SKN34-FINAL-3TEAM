"""POST /internal/judgments 요청·응답 (API 명세서 4.2). JSON 필드는 camelCase."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

JudgmentResult = Literal["CORRECT", "PARTIAL", "RETHINK", "HELD"]
HeldReason = Literal["INSUFFICIENT_EVIDENCE", "QUOTE_MISMATCH", "TOO_SHORT", "UNVERIFIED_SCOPE"]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RubricElement(ApiModel):
    element_id: str
    label: str
    description: str | None = None  # rubric_element.description NULL 허용
    points: int = Field(ge=0)
    judge_verified: bool
    good_thought: bool = False  # 들어가면 좋은 생각 = 필수 아님
    common_errors: list[str] | None = None  # rubric_element.common_errors NULL 허용


class Rubric(ApiModel):
    elements: list[RubricElement] = Field(min_length=1)


class Versions(ApiModel):
    mission: str | None = None
    rubric: str | None = None
    model: str | None = None
    prompt: str | None = None


class JudgmentRequest(ApiModel):
    answer_text: str
    # 고르기·수학 최종 답은 learning 규칙 판정, ai는 서술·논술·풀이 단계 (sequence-diagram 피드백)
    # 풀이 단계의 M1 수학 점검은 범위 밖, 같은 근거 추출·원문 대조로 판정
    input_type: Literal["NARRATIVE", "ESSAY", "SOLUTION_STEPS"]
    grade: int = Field(ge=3, le=6)  # 지원 학년 초3~6 (P03)
    rubric: Rubric
    versions: Versions = Field(default_factory=Versions)


class JudgmentElement(ApiModel):
    element_id: str
    quote: str | None
    verified: bool
    satisfied: bool


class JudgmentResponse(ApiModel):
    result: JudgmentResult
    # 보류(HELD)면 빈 목록: 보류를 낮은 수준으로 기록하지 않음 (FN-JDG-04)
    elements: list[JudgmentElement]
    held_reason: HeldReason | None
    # 검증 전 "AI 채점(시범)" 표시 (FN-JDG-03). 모든 요소가 judgeVerified면 false
    trial: bool
    versions: Versions
