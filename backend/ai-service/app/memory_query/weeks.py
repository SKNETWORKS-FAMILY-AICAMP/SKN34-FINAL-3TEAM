"""질문의 "N월 N째 주" 기간을 코드가 계산 (#877, 결정 기록 16.9, api-spec 4.2.7).

LLM은 달력을 보지 않고 첫 월요일을 세야 해서 이 표현을 기간으로 내지 못했다
(memory@2에서 36건 모두 null).
같은 질문이면 같은 기간이 나오게 서비스가 칸 검사 뒤 LLM 값을 이 계산값으로 덮어쓴다.

- 첫째 주: 그달 1일 ~ 첫 월요일이 든 주 끝. 1일이 월요일이면 그 주 [1일, 8일)
- k째 주(k ≥ 2): k번째 월요일 주 [월요일, +7일). 다음 달 1일에서 자름
- 마지막 주(기준안): 월~금 중 3일 이상이 그달에 든 마지막 월요일 주. 다음 달 1일에서 자름
- 연도: "작년·지난해"는 작년, "올해"는 올해,
  그 밖의 "○월"은 이번 달보다 뒤면 작년(프롬프트 "○월" 규칙과 같음)
- 그달에 없는 주("10월 다섯째 주")·주 표현이 두 개 이상: 기간 null(짐작하지 않음)
- 오늘보다 뒤인 주도 그대로 낸다. 진행 주 이후 자르기는 learning이 한다
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.memory_query.models import MemoryQueryPeriod

_ORDINALS = {"첫": 1, "둘": 2, "두": 2, "셋": 3, "세": 3, "넷": 4, "네": 4, "다섯": 5}
# 몇째 주: 첫째 주·첫 주·첫 번째 주·둘째주·두 번째 주·마지막 주·1주차·2번째 주
# "두 주"·"2주"는 기간 길이("2주 전")와 헷갈려 받지 않는다
_ORDINAL = (
    r"(?P<ord>첫\s*(?:번\s*)?째|첫|둘째|셋째|넷째|다섯\s*째|(?:두|세|네|다섯)\s*번\s*째|마지막"
    r"|[1-5]\s*(?:번\s*)?째|[1-5](?=\s*주\s*차))"
)
# "주말"·"주문"·"주제"·"주인"은 주가 아님
_WEEK_WORD = r"\s*주(?:\s*차)?(?![말문제인])"
_ORDINAL_WEEK = re.compile(_ORDINAL + _WEEK_WORD)
_MONTH = (
    r"(?:(?P<year>작년|지난해|올해)\s*)?"
    r"(?:(?<!\d)(?P<month>1[0-2]|0?[1-9])\s*월|(?P<rel>지난|저번|이번|요번)\s*달)"
)
_FULL = re.compile(_MONTH + r"\s*(?:의\s*)?" + _ORDINAL + _WEEK_WORD)


@dataclass(frozen=True)
class WeekMatch:
    period: MemoryQueryPeriod | None  # None이면 기간을 정할 수 없음(LLM 값도 버림)
    words: frozenset[str]  # 키워드에서 뺄 표현 조각(공백 없이 비교)

    def covers(self, keyword: str) -> bool:
        return keyword.replace(" ", "") in self.words


def _ordinal(text: str) -> int | str:
    text = re.sub(r"\s+", "", text)
    if text == "마지막":
        return "last"
    if text[0].isdigit():
        return int(text[0])
    for word, number in _ORDINALS.items():
        if text.startswith(word) and (len(text) == len(word) or text[len(word)] in "째번"):
            return number
    raise ValueError(text)


def _next_month(day: date) -> date:
    return date(day.year + day.month // 12, day.month % 12 + 1, 1)


def _first_monday(first: date) -> date:
    return first + timedelta(days=(7 - first.weekday()) % 7)


def week_period(year: int, month: int, which: int | str) -> MemoryQueryPeriod | None:
    first = date(year, month, 1)
    end = _next_month(first)
    monday = _first_monday(first)
    if which == "last":
        # 그달의 마지막 날이 든 주부터 거꾸로, 월~금 중 그달 날이 3일 이상인 첫 주
        start = end - timedelta(days=1)
        start -= timedelta(days=start.weekday())
        while sum(first <= start + timedelta(days=i) < end for i in range(5)) < 3:
            start -= timedelta(days=7)
        return MemoryQueryPeriod(from_=start, to=min(start + timedelta(days=7), end))
    if which == 1:
        return MemoryQueryPeriod(from_=first, to=monday + timedelta(days=7))
    start = monday + timedelta(days=7 * (int(which) - 1))
    if start >= end:
        return None  # 그달에 k번째 월요일이 없음
    return MemoryQueryPeriod(from_=start, to=min(start + timedelta(days=7), end))


def _year_month(match: re.Match[str], today: date) -> tuple[int, int]:
    rel = match["rel"]
    if rel is not None:
        if rel in ("지난", "저번"):
            return (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        return today.year, today.month
    month = int(match["month"])
    year = match["year"]
    if year in ("작년", "지난해"):
        return today.year - 1, month
    if year == "올해":
        return today.year, month
    return (today.year - 1, month) if month > today.month else (today.year, month)


def week_of_month(query: str, today: date) -> WeekMatch | None:
    """몇째 주 표현이 없으면 None(LLM 값 그대로). 있으면 계산한 기간(정할 수 없으면 기간 None)."""
    full = list(_FULL.finditer(query))
    if not full:
        return None
    pieces = {"주", "주차"}
    for match in [*full, *_ORDINAL_WEEK.finditer(query)]:
        whole = match.group(0)
        pieces |= {whole, *whole.split()}
        pieces.add(re.sub(r"\s+", "", match["ord"]))
        for name in ("year", "month", "rel"):
            if name in match.re.groupindex and match[name]:
                pieces.add(match[name] + ("월" if name == "month" else ""))
        if "rel" in match.re.groupindex and match["rel"]:
            pieces.add(match["rel"] + "달")
    words = frozenset(piece.replace(" ", "") for piece in pieces)
    if len(full) > 1 or len(list(_ORDINAL_WEEK.finditer(query))) > 1:
        return WeekMatch(None, words)
    match = full[0]
    year, month = _year_month(match, today)
    return WeekMatch(week_period(year, month, _ordinal(match["ord"])), words)
