"""LLM 변환 결과 칸 규칙 검사 (api-spec 4.2.7). 위반은 서비스가 502 AI_BAD_RESPONSE로 바꿈.

앞뒤 공백 제거와 같은 낱말 중복 제거만 고쳐 주고,
그 밖의 규칙 위반은 고치지 않고 사유 코드를 돌려준다.
learning은 502를 받으면 원문 질문으로 검색하므로 애매한 결과를 억지로 살리지 않는다.
사유 코드에는 원문을 넣지 않는다(NFR-SEC-05).
"""

from dataclasses import dataclass
from datetime import date

from app.memory_query.models import (
    KEYWORD_MAX_CHARS,
    KEYWORDS_MAX,
    SEARCH_TEXT_MAX_CHARS,
    MemoryQueryPeriod,
)
from app.memory_query.prompts import GeneratedMemoryQuery


@dataclass(frozen=True)
class Checked:
    keywords: list[str]
    period: MemoryQueryPeriod | None
    search_text: str


@dataclass(frozen=True)
class Problem:
    reason: str


def _day(value: str) -> date | None:
    text = value.strip()
    if len(text) != 10:  # yyyy-MM-dd만 (fromisoformat은 20261116 같은 형식도 받음)
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def check(generated: GeneratedMemoryQuery) -> Checked | Problem:
    keywords: list[str] = []
    for raw in generated.keywords:
        keyword = raw.strip()
        if not keyword:
            return Problem("KEYWORD_EMPTY")
        if len(keyword) > KEYWORD_MAX_CHARS:
            return Problem("KEYWORD_TOO_LONG")
        if keyword not in keywords:
            keywords.append(keyword)
    if len(keywords) > KEYWORDS_MAX:
        return Problem("TOO_MANY_KEYWORDS")

    period = None
    if generated.period is not None:
        start = _day(generated.period.from_date)
        end = _day(generated.period.to_date)
        if start is None or end is None:
            return Problem("PERIOD_NOT_DATE")
        if start >= end:
            return Problem("PERIOD_NOT_ORDERED")
        period = MemoryQueryPeriod(from_=start, to=end)

    search_text = generated.search_text.strip()
    if not search_text:
        return Problem("SEARCH_TEXT_EMPTY")
    if len(search_text) > SEARCH_TEXT_MAX_CHARS:
        return Problem("SEARCH_TEXT_TOO_LONG")
    return Checked(keywords, period, search_text)
