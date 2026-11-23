"""몇째 주 기간 계산 (#877, 결정 기록 16.9). 2026년 달력 기준, 기간은 반열림 [from, to)."""

from datetime import date

import pytest

from app.memory_query.weeks import week_of_month

TODAY = date(2026, 11, 18)  # 수요일, memory@2 기준일


def period(query: str, today: date = TODAY) -> tuple[str, str] | None:
    match = week_of_month(query, today)
    assert match is not None, query
    if match.period is None:
        return None
    return match.period.from_.isoformat(), match.period.to.isoformat()


def test_first_week_runs_from_first_day_to_end_of_first_monday_week() -> None:
    assert period("10월 첫째 주에 한 거") == ("2026-10-01", "2026-10-12")  # 1일 목요일


def test_first_week_when_first_day_is_weekend() -> None:
    assert period("11월 첫째 주") == ("2026-11-01", "2026-11-09")  # 1일 일요일
    assert period("8월 첫째 주") == ("2026-08-01", "2026-08-10")  # 1일 토요일


def test_first_week_when_first_day_is_monday() -> None:
    assert period("6월 첫째 주") == ("2026-06-01", "2026-06-08")


def test_later_weeks_are_monday_to_sunday() -> None:
    assert period("8월 둘째 주") == ("2026-08-10", "2026-08-17")
    assert period("10월 셋째 주") == ("2026-10-19", "2026-10-26")
    assert period("6월 둘째 주") == ("2026-06-08", "2026-06-15")
    assert period("9월 둘째 주") == ("2026-09-14", "2026-09-21")  # 1일 화요일: 첫째 주가 9/1~9/13


def test_last_week() -> None:
    # 기준안: 월~금 중 3일 이상이 그달에 든 마지막 월요일 주, 다음 달 1일에서 자름
    assert period("6월 마지막 주") == ("2026-06-22", "2026-06-29")  # 6/29 주는 6월 평일 2일
    assert period("8월 마지막 주") == ("2026-08-24", "2026-08-31")  # 8/31 주는 8월 평일 1일
    assert period("9월 마지막 주") == ("2026-09-28", "2026-10-01")  # 9월 평일 3일
    assert period("10월 마지막 주") == ("2026-10-26", "2026-11-01")
    assert period("11월 마지막 주") == ("2026-11-23", "2026-11-30")


@pytest.mark.parametrize(
    "query", ["10월 다섯째 주에 한 거", "10월 첫째 주랑 둘째 주", "10월 첫째 주랑 11월 둘째 주"]
)
def test_missing_week_and_two_week_phrases_are_null(query: str) -> None:
    # 2026-10은 월요일이 4개라 다섯째 주가 없음. 주 표현이 두 개면 하나로 정하지 않음
    assert period(query) is None


def test_year_rules() -> None:
    assert period("12월 첫째 주") == ("2025-12-01", "2025-12-08")  # 이번 달보다 뒤면 작년
    assert period("작년 10월 첫째 주") == ("2025-10-01", "2025-10-13")
    assert period("올해 10월 첫째 주") == ("2026-10-01", "2026-10-12")
    assert period("지난달 첫째 주") == ("2026-10-01", "2026-10-12")
    assert period("저번 달 둘째 주") == ("2026-10-12", "2026-10-19")
    assert period("이번 달 둘째 주") == ("2026-11-09", "2026-11-16")
    assert period("지난달 마지막 주", date(2027, 1, 5)) == ("2026-12-28", "2027-01-01")
    # 오늘보다 뒤인 주도 그대로(자르기는 learning)
    assert period("11월 넷째 주") == ("2026-11-23", "2026-11-30")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("10월 첫째주", ("2026-10-01", "2026-10-12")),
        ("10월 첫 주", ("2026-10-01", "2026-10-12")),
        ("10월 첫번째 주", ("2026-10-01", "2026-10-12")),
        ("10월 첫 번째 주", ("2026-10-01", "2026-10-12")),
        ("10월 1주차", ("2026-10-01", "2026-10-12")),
        ("10월의 두 번째 주", ("2026-10-12", "2026-10-19")),
        ("10월 2번째 주", ("2026-10-12", "2026-10-19")),
        ("10월 셋째주", ("2026-10-19", "2026-10-26")),
        ("10월 넷째 주차", ("2026-10-26", "2026-11-01")),
    ],
)
def test_spelling_variants(query: str, expected: tuple[str, str]) -> None:
    assert period(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "지난주에 한 거",
        "이번 주",
        "2주 전에 쓴 글",
        "10월에 한 문제",
        "10월 첫째 날",
        "10월 첫째 주말",
        "첫째 주에 한 거",
    ],
)
def test_not_week_of_month(query: str) -> None:
    assert week_of_month(query, TODAY) is None


def test_memory_at_2_labels() -> None:
    # evaluation/datasets/memory@2/queries.jsonl의 사람이 정한 기간(기준일 2026-11-18).
    # 평가셋 파일은 읽지 않고 값만 옮김
    labels = {
        "10월 첫째 주에 별자리 한 거": ("2026-10-01", "2026-10-12"),  # p104
        "10월 첫째 주에 한 것": ("2026-10-01", "2026-10-12"),  # p113
        "11월 첫째 주에 한 거": ("2026-11-01", "2026-11-09"),  # p115
        "8월 첫째 주에 한 문제": ("2026-08-01", "2026-08-10"),  # p117
        "1월 첫째 주에 한 것": ("2026-01-01", "2026-01-12"),  # p119
        "8월 둘째 주에 고양이 나온 글": ("2026-08-10", "2026-08-17"),  # p120
    }
    for query, expected in labels.items():
        assert period(query) == expected, query


def test_week_words_cover_expression_pieces_only() -> None:
    match = week_of_month("지난달 첫째 주에 고양이", TODAY)
    assert match is not None
    for word in ("지난달", "첫째", "주", "첫째 주", "첫째주"):
        assert match.covers(word), word
    assert not match.covers("고양이")
