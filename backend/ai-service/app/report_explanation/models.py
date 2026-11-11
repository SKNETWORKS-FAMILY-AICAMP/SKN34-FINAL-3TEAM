"""POST /internal/report-explanations 요청·응답 (API 명세서 4.2.3, FN-RPT-09).

JSON 필드는 camelCase.

scores는 learning modelScores.m2.scores 그대로(scoring 4.3.1): 서술 9개 키(hol 1~4, 나머지 1~5),
논술 {org, cont, exp} 0~3. 학생·시도·답변 ID와 이름은 받지 않음 (NFR-SEC-03).
"""

from typing import Literal

from pydantic import Field, model_validator

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


class ExplanationRequest(ApiModel):
    grade: int = Field(ge=3, le=6)
    input_type: InputType
    text: str = Field(min_length=1, max_length=50_000)
    scores: dict[str, int]

    @model_validator(mode="after")
    def check_text_and_scores(self) -> "ExplanationRequest":
        if not self.text.strip():
            raise ValueError("text is blank")
        ranges = SCORE_RANGES[self.input_type]
        if set(self.scores) != set(ranges):
            raise ValueError(f"scores keys must be {sorted(ranges)}")
        for key, score in self.scores.items():
            low, high = ranges[key]
            if not low <= score <= high:
                raise ValueError(f"scores.{key} must be {low}~{high}")
        return self


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
