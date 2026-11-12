"""POST /internal/judgments 요청·응답 (API 명세서 4.2). JSON 필드는 camelCase."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

JudgmentResult = Literal["CORRECT", "PARTIAL", "RETHINK", "HELD"]
HeldReason = Literal[
    "INSUFFICIENT_EVIDENCE",
    "QUOTE_MISMATCH",
    "TOO_SHORT",
    "UNVERIFIED_SCOPE",
    "MODEL_DISAGREEMENT",
    "LOW_CONFIDENCE",
]
EssayType = Literal["설명글", "글짓기", "주장", "찬성반대", "대안제시"]
# 교차 확인 생략 사유 (#305): 장애·5xx·시간 초과 / 4xx·계약 밖 응답
CrossCheckSkipped = Literal["SCORING_UNAVAILABLE", "SCORING_REJECTED"]


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


class Solution(ApiModel):
    steps: list[str] = Field(min_length=1)
    final_answer: str


class JudgmentRequest(ApiModel):
    answer_text: str
    # 고르기·수학 최종 답은 learning 규칙 판정, ai는 서술·논술·풀이 단계 (sequence-diagram 피드백)
    input_type: Literal["NARRATIVE", "ESSAY", "SOLUTION_STEPS"]
    grade: int = Field(ge=3, le=6)  # 지원 학년 초3~6 (P03)
    rubric: Rubric
    versions: Versions = Field(default_factory=Versions)
    # #69 교차 확인 입력 (api-spec 4.2.2). 없으면 해당 모델을 부르지 않음
    question: str | None = None  # M2 prompt·M1 problem
    keywords: list[str] = Field(default_factory=list)  # 서술 M2 핵심어 묶음
    essay_type: EssayType | None = None  # 논술 M2 글 종류
    essay_labels: list[str] = Field(default_factory=list, max_length=4)
    answer_key: str | None = None  # M1 정답
    solution: Solution | None = None  # M1 학생 풀이


class JudgmentElement(ApiModel):
    element_id: str
    quote: str | None
    verified: bool
    satisfied: bool


class ModelIdentity(ApiModel):
    name: str
    version: str
    revision: int = Field(ge=1)

    @property
    def label(self) -> str:
        return f"{self.name}@{self.version}"


class M2Observation(ApiModel):
    input_type: Literal["NARRATIVE", "ESSAY"]
    scores: dict[str, int]
    raw_scores: dict[str, float]
    model: ModelIdentity
    mean: float  # scores 평균, 불일치 판단 기준
    disagreement: bool  # LLM 결과와 불일치


class M1Observation(ApiModel):
    confidence: float
    model: ModelIdentity


class M2Preparation(ApiModel):
    rule_version: Literal["1112c"] = "1112c"
    copied: int = Field(ge=0)
    repeated: bool
    chars: int = Field(ge=0)
    labels_removed: int = Field(ge=0)
    short: bool
    truncated: bool = False
    notices: list[
        Literal[
            "COPIED_REMOVED",
            "REPEATED_REMOVED",
            "SHORT_ANSWER",
            "EMPTY_AFTER_CLEANING",
            "ESSAY_TOO_SHORT",
            "ESSAY_ORIGINALLY_SHORT",
        ]
    ] = Field(default_factory=list)


class ModelScores(ApiModel):
    """judgment.model_scores에 그대로 저장하는 AI 관찰. 학생 화면에 보이지 않음."""

    m2: M2Observation | None = None
    m2_preparation: M2Preparation | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    m1: M1Observation | None = None
    # scoring 실패로 교차 확인 없이 LLM 판정만 쓴 경우 사유 (#305). 정상이면 null
    skipped: CrossCheckSkipped | None = None


class JudgmentResponse(ApiModel):
    result: JudgmentResult
    # 보류(HELD)면 빈 목록: 보류를 낮은 수준으로 기록하지 않음 (FN-JDG-04)
    elements: list[JudgmentElement]
    held_reason: HeldReason | None
    # 검증 전 "AI 채점(시범)" 표시 (FN-JDG-03). 모든 요소가 judgeVerified면 false
    trial: bool
    versions: Versions
    # 활성 M2·M1 결과. 부르지 않았거나 비활성이면 null (api-spec 4.2.2)
    model_scores: ModelScores | None = None
