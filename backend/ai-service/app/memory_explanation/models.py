"""POST /internal/memory-explanations 요청·응답 (api-spec 4.2.6, FN-RET-13).

JSON 필드는 camelCase. 근거는 요청 안 번호(no)로만 지칭하고 학생 이름·학생·시도·답변 ID는
받지 않는다(NFR-SEC-03). 정의 밖 칸은 400이라 ID를 실수로 넣어도 LLM까지 가지 않는다.
글자 수 상한은 기준안(#565): 질문은 공개 검색 질문(2.12)과 같은 200자, 근거 칸은 넉넉히 둠.
"""

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.followup.models import LlmVersions
from app.judgment.models import ApiModel

EVIDENCE_MAX = 3  # 검색 결과 카드 최대 3개 (P27 기준안)
QUERY_MAX_CHARS = 200
THEME_TITLE_MAX_CHARS = 200
MISSION_QUESTION_MAX_CHARS = 2000
ANSWER_EXCERPT_MAX_CHARS = 2000
WEEK_LABEL_MAX_CHARS = 50


class _Forbid(ApiModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*")
    @classmethod
    def _not_blank(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("공백만일 수 없음")
        return value


class MemoryEvidence(_Forbid):
    no: int = Field(ge=1, le=EVIDENCE_MAX)
    theme_title: str = Field(min_length=1, max_length=THEME_TITLE_MAX_CHARS)
    mission_question: str = Field(min_length=1, max_length=MISSION_QUESTION_MAX_CHARS)
    answer_excerpt: str = Field(min_length=1, max_length=ANSWER_EXCERPT_MAX_CHARS)
    week_label: str = Field(min_length=1, max_length=WEEK_LABEL_MAX_CHARS)


class MemoryExplanationRequest(_Forbid):
    query: str = Field(min_length=1, max_length=QUERY_MAX_CHARS)
    evidence: list[MemoryEvidence] = Field(min_length=1, max_length=EVIDENCE_MAX)

    @model_validator(mode="after")
    def _unique_numbers(self) -> "MemoryExplanationRequest":
        numbers = [item.no for item in self.evidence]
        if len(numbers) != len(set(numbers)):
            raise ValueError("evidence.no는 겹칠 수 없음")
        return self


class MemoryExplanationResponse(ApiModel):
    text: str  # 2~3문장, 문장 끝마다 근거 번호 표시 "[1]"
    citations: list[int]  # 본문에 쓴 근거 번호(오름차순, 중복 없음, 요청 번호 안)
    versions: LlmVersions  # model은 실제 LLM 모델 ID, prompt는 memoryExplanation 버전
