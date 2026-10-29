import pytest

from app.analysis_agent.calculators import compute, count_metric, ratio_metric
from app.analysis_agent.models import Period
from tests.analysis_agent.records_fixture import PERIOD, SCOPE, records

PERIOD_ = Period.model_validate(PERIOD)


def by_label(computation):
    return {metric.label: metric for metric in computation.metrics}


def test_count_uses_learning_summary_as_is() -> None:
    computation = compute("COUNT", records(), SCOPE)
    assert computation.record_count == 3
    assert [m.label for m in computation.metrics] == [
        "학습한 활동",
        "완료한 활동",
        "도움 없이 시작한 활동",
        "되묻기 후 생각을 더한 활동",
    ]
    assert computation.metrics[2].value is None  # 분모 5 미만은 learning이 비율을 비움


def test_thinking_types_count_missions_and_skip_unobserved() -> None:
    metrics = by_label(compute("THINKING_TYPES", records(), SCOPE))
    assert metrics["분석하기 활동"].count == 2
    assert metrics["문제 해결하기 활동"].count == 1
    assert "따져 보기 활동" not in metrics


def test_changes_use_learning_counts() -> None:
    computation = compute("CHANGES", records(), SCOPE)
    metrics = by_label(computation)
    assert metrics["되묻기 후 생각을 더한 활동"].numerator == 1
    grew = metrics["글자 수가 늘어난 시도"]
    assert (grew.numerator, grew.denominator, grew.value) == (1, 1, None)
    assert [s.evidence.answer_id for s in computation.sources] == ["a-1", "a-2"]
    assert computation.sources[0].evidence.mission_title == "쉬는 시간 토론"
    assert computation.insufficient is None


def test_child_thoughts_use_latest_answer_per_attempt() -> None:
    computation = compute("CHILD_THOUGHTS", records(), SCOPE)
    assert [s.evidence.answer_id for s in computation.sources] == ["a-4", "a-3", "a-2"]
    assert computation.sources[2].evidence.answer_version == 2


def test_reflections() -> None:
    computation = compute("REFLECTIONS", records(), SCOPE)
    metrics = by_label(computation)
    assert metrics["돌아보기를 쓴 활동"].count == 1
    assert metrics["난이도 어려웠어 돌아보기"].count == 1
    assert computation.sources[0].text == "근거 찾기가 어려웠어"
    assert computation.sources[0].evidence.answer_id is None


def test_insufficient_kinds() -> None:
    assert compute("COUNT", records(empty=True), SCOPE).insufficient == "NO_RECORD"
    no_changes = records().model_copy(update={"changes": []})
    assert compute("CHANGES", no_changes, SCOPE).insufficient == "NO_CHANGES"
    no_reflection = records().model_copy(update={"activities": []})
    assert compute("REFLECTIONS", no_reflection, SCOPE).insufficient == "NO_REFLECTIONS"


@pytest.mark.parametrize(
    ("numerator", "denominator", "value", "state"),
    [
        (0, 0, None, "NO_RECORD"),  # 분모 0은 0%가 아니라 기록 없음
        (2, 4, None, "INSUFFICIENT_SAMPLE"),  # 분모 5 미만은 비율 비움
        (2, 5, 0.4, "OK"),
    ],
)
def test_ratio_metric_matches_learning_rule(numerator, denominator, value, state) -> None:
    metric = ratio_metric("늘어난 시도", numerator, denominator, "늘어난 수 / 시도 수", PERIOD_)
    assert (metric.value, metric.state) == (value, state)
    assert (metric.numerator, metric.denominator, metric.count) == (
        numerator,
        denominator,
        numerator,
    )
    assert metric.formula == "늘어난 수 / 시도 수"
    assert metric.period == PERIOD_


def test_count_metric_has_no_ratio() -> None:
    metric = count_metric("돌아보기를 쓴 활동", 0, "기간 안에 쓴 돌아보기 수", PERIOD_)
    assert (metric.value, metric.count, metric.state) == (None, 0, "NO_RECORD")
    assert (metric.numerator, metric.denominator) == (0, 0)
