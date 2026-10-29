from app.analysis_agent.calculators import compute
from app.analysis_agent.prompts import Citation
from app.analysis_agent.verification import verify
from tests.analysis_agent.records_fixture import SCOPE, records

CHANGES = compute("CHANGES", records(), SCOPE)  # sources: S1=a-1, S2=a-2


def test_passes_when_numbers_and_quotes_match() -> None:
    checked = verify(
        "이번 주 3개 시도 중 1개에서 답을 다시 썼어요. 처음엔 “나는 찬성해.”라고 썼어요.",
        [Citation(source_id="S1", quote="나는 찬성해.")],
        CHANGES,
    )
    assert checked.passed
    assert checked.evidence[0].answer_id == "a-1"
    assert checked.evidence[0].quote == "나는 찬성해."


def test_number_not_in_computation_fails() -> None:
    checked = verify("7개 시도에서 답을 다시 썼어요.", [], CHANGES)
    assert not checked.verification.numbers_matched


def test_korean_count_words_fail() -> None:
    assert not verify("세 번 다시 썼어요.", [], CHANGES).verification.numbers_matched


def test_numbers_inside_quotes_and_period_dates_are_allowed() -> None:
    checked = verify("10월 20일부터 26일까지 1개 시도를 다시 썼어요.", [], CHANGES)
    assert checked.verification.numbers_matched


def test_quote_not_in_source_fails() -> None:
    checked = verify("아이는 “나는 반대해”라고 썼어요.", [], CHANGES)
    assert not checked.verification.quotes_matched
    unknown = verify("다시 썼어요.", [Citation(source_id="S9", quote="나는 찬성해.")], CHANGES)
    assert not unknown.verification.quotes_matched


def test_level_words_fail() -> None:
    checked = verify("사고력이 좋아졌어요.", [], CHANGES)
    assert not checked.verification.content_allowed
    assert not checked.passed
