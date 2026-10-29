from app.analysis_agent.calculators import compute
from app.analysis_agent.verification import verify
from tests.analysis_agent.records_fixture import SCOPE, records

CHANGES = compute("CHANGES", records(), SCOPE)  # sources: a-1, a-2


def test_passes_when_numbers_and_quotes_match() -> None:
    checked = verify(
        "이번 주 3개 시도 중 1개에서 답을 다시 썼어요. 처음엔 “나는 찬성해.”라고 썼어요.",
        CHANGES,
    )
    assert checked.passed
    assert checked.evidence[0].answer_id == "a-1"  # 따옴표 구간이 처음 들어맞는 원문
    assert checked.evidence[0].quote == "나는 찬성해."
    assert checked.evidence[0].kind == "ANSWER"


def test_quote_links_to_containing_source() -> None:
    checked = verify("“왜냐하면 쉬는 시간이 길면”이라는 까닭을 더했어요.", CHANGES)
    assert checked.passed
    assert [e.answer_id for e in checked.evidence] == ["a-2"]


def test_same_source_quoted_twice_is_one_evidence() -> None:
    # core는 같은 answerId 근거가 두 번 오면 거부함
    checked = verify("“나는 찬성해.”라고 했고 “왜냐하면 쉬는 시간이 길면”이라고 더했어요.", CHANGES)
    assert checked.passed
    assert [e.answer_id for e in checked.evidence] == ["a-1", "a-2"]
    twice = verify("“왜냐하면”이라고 시작해 “더 잘 놀 수 있어”라고 썼어요.", CHANGES)
    assert [e.answer_id for e in twice.evidence] == ["a-2"]
    assert twice.evidence[0].quote == "왜냐하면"


def test_number_not_in_computation_fails() -> None:
    checked = verify("7개 시도에서 답을 다시 썼어요.", CHANGES)
    assert not checked.verification.numbers_matched


def test_korean_count_words_fail() -> None:
    assert not verify("세 번 다시 썼어요.", CHANGES).verification.numbers_matched


def test_numbers_inside_quotes_and_period_dates_are_allowed() -> None:
    checked = verify("10월 20일부터 26일까지 1개 시도를 다시 썼어요.", CHANGES)
    assert checked.verification.numbers_matched


def test_quote_not_in_source_fails() -> None:
    checked = verify("아이는 “나는 반대해”라고 썼어요.", CHANGES)
    assert not checked.verification.quotes_matched
    assert checked.evidence == []


def test_level_words_fail() -> None:
    checked = verify("사고력이 좋아졌어요.", CHANGES)
    assert not checked.verification.content_allowed
    assert not checked.passed
