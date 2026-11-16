"""POST /internal/memory-queries 요청·응답 (api-spec 4.2.7, FN-RET-12, #681).

JSON 필드는 camelCase. 질문은 learning이 닉네임을 가린 뒤 보내며 학생 이름·ID는 받지 않는다
(NFR-SEC-03). 정의 밖 칸은 400이라 ID를 실수로 넣어도 LLM까지 가지 않는다.
"""

import re
from datetime import date

from pydantic import ConfigDict, Field, field_validator

from app.followup.models import LlmVersions
from app.judgment.models import ApiModel

QUERY_MAX_CHARS = 200  # 공개 검색 질문(2.12)과 같음
KEYWORDS_MAX = 5
KEYWORD_MAX_CHARS = 20
SEARCH_TEXT_MAX_CHARS = 200
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


class MemoryQueryRequest(ApiModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=QUERY_MAX_CHARS)
    today: date  # KST 날짜 yyyy-MM-dd, "지난주" 같은 상대 기간 계산 기준

    @field_validator("query")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("공백만일 수 없음")
        return value

    @field_validator("today", mode="before")
    @classmethod
    def _day_string(cls, value: object) -> object:
        # 숫자(유닉스 시각)·시각 포함 글자 등 느슨한 변환을 막고 yyyy-MM-dd만 받음
        if not isinstance(value, str) or not _DAY.fullmatch(value):
            raise ValueError("yyyy-MM-dd 형식이어야 함")
        return value


class MemoryQueryPeriod(ApiModel):
    """반열림 구간 [from, to). from < to"""

    from_: date = Field(alias="from")
    to: date


class MemoryQueryResponse(ApiModel):
    keywords: list[str]  # 0~5개, 각 1~20자, 중복 없음
    period: MemoryQueryPeriod | None  # 질문에 기간 표현이 있을 때만
    search_text: str  # 요청 표현을 뺀 검색용 문장 1~200자
    versions: LlmVersions  # model은 실제 LLM 모델 ID, prompt는 memoryQuery 버전
