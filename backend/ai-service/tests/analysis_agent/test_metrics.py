from app.analysis_agent.metrics import compute, connective_count, sentence_count
from tests.analysis_agent.records_fixture import SCOPE, answer, attempt, records


def by_label(computation):
    return {metric.label: metric for metric in computation.metrics}


def test_inclusion_excludes_out_of_period_failed_only_and_deleted() -> None:
    computation = compute("COUNT", records(), SCOPE)
    assert computation.record_count == 3
    metrics = by_label(computation)
    assert metrics["집계 대상 시도 수"].count == 3
    assert metrics["완료한 시도 수"].count == 1


def test_ratio_hidden_below_five_and_shown_from_five() -> None:
    small = by_label(compute("COUNT", records(), SCOPE))["도움 없이 시작한 비율"]
    # t-3은 최초 답변 전에 도움을 열어 제외 → 3개 중 2개, 분모 5 미만이라 비율 없음
    assert (small.numerator, small.denominator, small.value) == (2, 3, None)
    assert small.state == "INSUFFICIENT_SAMPLE"

    many = [attempt(f"x-{i}", answer(f"b-{i}", 1, 21, "생각")) for i in range(5)]
    ratio = by_label(compute("COUNT", records(many), SCOPE))["도움 없이 시작한 비율"]
    assert (ratio.numerator, ratio.denominator, ratio.value, ratio.state) == (5, 5, 1.0, "OK")


def test_thinking_types_count_only_included_attempts() -> None:
    metrics = by_label(compute("THINKING_TYPES", records(), SCOPE))
    assert metrics["분석하기 시도 수"].count == 2  # t-4는 기간 밖
    assert metrics["문제 해결하기 시도 수"].count == 1


def test_changes_compare_first_and_revised() -> None:
    computation = compute("CHANGES", records(), SCOPE)
    metrics = by_label(computation)
    assert metrics["되묻기 후 다시 쓴 시도 수"].count == 1
    assert metrics["글자 수가 늘어난 시도"].numerator == 1
    assert metrics["까닭을 잇는 말이 늘어난 시도"].numerator == 1
    assert [s.evidence.answer_id for s in computation.sources] == ["a-1", "a-2"]
    assert computation.insufficient is None


def test_child_thoughts_use_latest_answer_per_attempt() -> None:
    computation = compute("CHILD_THOUGHTS", records(), SCOPE)
    assert [s.evidence.answer_id for s in computation.sources] == ["a-4", "a-3", "a-2"]


def test_reflections_and_insufficient_kinds() -> None:
    computation = compute("REFLECTIONS", records(), SCOPE)
    assert by_label(computation)["돌아보기를 쓴 시도"].numerator == 1
    assert computation.sources[0].text == "근거 찾기가 어려웠어"

    assert compute("COUNT", records([]), SCOPE).insufficient == "NO_RECORD"
    no_reflection = [attempt("y", answer("c", 1, 21, "생각"), status="COMPLETED")]
    assert compute("REFLECTIONS", records(no_reflection), SCOPE).insufficient == "NO_REFLECTIONS"


def test_text_rules() -> None:
    assert sentence_count("첫 문장. 둘째 문장?\n\n셋째") == 3
    assert connective_count("왜냐하면 비가 와서 그래서 때문에") == 3
