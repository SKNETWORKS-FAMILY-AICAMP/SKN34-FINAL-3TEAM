"""POST /internal/report-explanations 요청·응답 (API 명세서 4.2.3, FN-RPT-09).

JSON 필드는 camelCase.

scores는 learning modelScores.m2.scores 그대로(scoring 4.3.1): 서술 9개 키(hol 1~4, 나머지 1~5),
논술 {org, cont, exp} 0~3. 학생·시도·답변 ID와 이름은 받지 않음 (NFR-SEC-03).
scores는 선택 항목이며 범위를 검증한다. 문제 전문과 답안별 판정 항목과 함께 설명의 맥락으로 쓴다.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.followup.models import LlmVersions
from app.judgment.models import ApiModel

InputType = Literal["NARRATIVE", "ESSAY"]

# 항목 키 → 학부모에게 보일 이름. 순서는 동점일 때 고르는 순서 (ml/m2 README 항목 표)
ITEM_LABELS: dict[str, dict[str, str]] = {
    "NARRATIVE": {
        "hol": "총점",
        "task_1": "과제 수행",
        "content_1": "명료성",
        "content_2": "구체성",
        "content_3": "적절성",
        "organization_1": "연결성",
        "organization_2": "통일성",
        "expression_1": "어휘",
        "expression_2": "어법",
    },
    "ESSAY": {"org": "구성", "cont": "내용", "exp": "표현"},
}
# 항목별 점수 범위 (scoring 4.3.1). 서술 총점(hol)만 1~4
SCORE_RANGES: dict[str, dict[str, tuple[int, int]]] = {
    "NARRATIVE": {key: ((1, 4) if key == "hol" else (1, 5)) for key in ITEM_LABELS["NARRATIVE"]},
    "ESSAY": {key: (0, 3) for key in ITEM_LABELS["ESSAY"]},
}


class EssayAnswer(ApiModel):
    claim: str
    reasons: list[str]
    rebuttal: str

    def written_text(self) -> str:
        return "\n".join(
            part for part in (self.claim, *self.reasons, self.rebuttal) if part.strip()
        )


class CriterionJudgment(ApiModel):
    label: str = Field(min_length=1)
    requirement: str | None = None
    satisfied: bool = Field(strict=True)
    required: bool = Field(strict=True)
    quote: str | None = None

    def usable(self, text: str) -> bool:
        return bool(self.label.strip() and (self.quote is None or self.quote in text))


class ExplanationRequest(ApiModel):
    grade: int = Field(ge=3, le=6)
    input_type: InputType
    text: str = Field(min_length=1, max_length=50_000)
    topic: str | None = Field(default=None, max_length=2_000)
    scores: dict[str, int] | None = None
    question: str | None = Field(default=None, max_length=50_000)
    essay: EssayAnswer | None = None
    criteria: list[CriterionJudgment] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_text_and_scores(self) -> "ExplanationRequest":
        if not self.text.strip():
            raise ValueError("text is blank")
        if self.essay is not None and (
            self.input_type != "ESSAY" or self.essay.written_text() != self.text
        ):
            raise ValueError("essay fields must reproduce the submitted text")
        if self.scores is None:
            return self
        ranges = SCORE_RANGES[self.input_type]
        if set(self.scores) != set(ranges):
            raise ValueError(f"scores keys must be {sorted(ranges)}")
        for key, score in self.scores.items():
            low, high = ranges[key]
            if not low <= score <= high:
                raise ValueError(f"scores.{key} must be {low}~{high}")
        return self


class ExplanationDetail(BaseModel):
    """학부모에게 보여 줄 설명과 보완에 사용한 항목 번호·인용."""

    model_config = ConfigDict(extra="ignore")

    analysis: str = Field(description="상세 분석")
    improvement_points: str | None = Field(
        default=None, description="보완할 지점, 근거가 없으면 null"
    )
    next_steps: str | None = Field(default=None, description="개선 방안 한 문단")

    gap_criterion: int | None = Field(default=None, description="보완에 쓴 항목 번호, 아니면 null")
    gap_quote: str | None = Field(
        default=None, description="보완에서 인용한 학생 원문, 아니면 null"
    )

    @field_validator("gap_criterion", mode="before")
    @classmethod
    def valid_gap_number(cls, value: object) -> int | None:
        return value if type(value) is int and value > 0 else None

    @field_validator("gap_quote", mode="before")
    @classmethod
    def valid_gap_quote(cls, value: object) -> str | None:
        return value if isinstance(value, str) and value.strip() else None

    @field_validator("analysis", "improvement_points", "next_steps", mode="before")
    @classmethod
    def join_lists(cls, value: object) -> object:
        if isinstance(value, list):
            return " ".join(str(item).strip() for item in value if str(item).strip())
        return value


class Explanation(ApiModel):
    text: str
    quote: str | None  # 학생 글의 부분 문자열, 설명과 겹치는 문장이 없으면 null


class ActiveExplanationResponse(ApiModel):
    active: Literal[True] = True
    explanation: Explanation
    versions: LlmVersions  # model은 레지스트리 "이름@버전", prompt는 설명 프롬프트 버전


class InactiveExplanationResponse(ApiModel):
    """설명 모델이 활성이 아니거나 그 학년·입력 유형이 승인 범위 밖"""

    active: Literal[False] = False


ExplanationResponse = ActiveExplanationResponse | InactiveExplanationResponse
