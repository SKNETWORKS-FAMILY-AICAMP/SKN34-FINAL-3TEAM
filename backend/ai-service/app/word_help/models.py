"""POST /internal/word-helps 요청·응답 (api-spec 2.2.1·4.2.7, FN-LRN-21, #599).

JSON 필드는 camelCase. 학생 이름·답·ID는 받지 않는다(NFR-SEC-03). 정의 밖 칸은 400이라
ID를 실수로 넣어도 LLM까지 가지 않는다. leak은 마무리 전 시도만 learning이 채운다.
"""

from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from app.judgment.models import ApiModel

QUESTION_MAX_CHARS = 100
MISSION_TEXT_MAX_CHARS = 4000
SUBJECT_MAX_CHARS = 20

WordHelpState = Literal["EXPLAINED", "DICTIONARY_ONLY", "NOT_FOUND", "DEFERRED", "OUT_OF_SCOPE"]
DictionarySource = Literal["표준국어대사전", "온용어"]


class _Forbid(ApiModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*")
    @classmethod
    def _not_blank(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("공백만일 수 없음")
        return value


class WordHelpLeak(_Forbid):
    """유출 검사 값. answerKey는 학생에게 보이는 정답 글자(되묻기 rubric.answerKey와 같은 뜻)"""

    answer_key: list[str] = Field(default_factory=list, max_length=50)
    forbidden_terms: list[str] = Field(default_factory=list, max_length=100)
    example_answer: str | None = Field(default=None, max_length=4000)


class WordHelpRequest(_Forbid):
    question: str = Field(min_length=1, max_length=QUESTION_MAX_CHARS)
    mission_text: str = Field(min_length=1, max_length=MISSION_TEXT_MAX_CHARS)
    grade: int = Field(ge=3, le=6)
    subject: str = Field(min_length=1, max_length=SUBJECT_MAX_CHARS)
    leak: WordHelpLeak | None = None


class WordSense(ApiModel):
    definition: str
    source: DictionarySource


class WordHelpVersions(ApiModel):
    prompt: str
    model: str | None  # LLM을 부르지 않았으면(유출 미리 검사·사전 없음) None


class WordHelpResponse(ApiModel):
    state: WordHelpState
    headword: str | None
    text: str
    example: str | None
    senses: list[WordSense]
    versions: WordHelpVersions
