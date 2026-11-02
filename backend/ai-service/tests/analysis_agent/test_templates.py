"""코드로 만드는 답변 문장 (규칙 응답·기록 부족·미지원 안내)."""

import pytest

from app.analysis_agent import templates
from app.analysis_agent.calculators import Computation, Source, compute
from app.analysis_agent.models import Evidence, Metric
from tests.analysis_agent.records_fixture import SCOPE, metric, records

PERIOD_LINE = "조회 기간은 2026-10-20부터 2026-10-26까지예요."


def source(index: int, text: str) -> Source:
    evidence = Evidence(
        kind="ANSWER",
        attempt_id=f"t-{index}",
        mission_title=f"미션 {index}",
        answer_id=f"a-{index}",
        answer_version=1,
        submitted_at=None,
        quote=text,
    )
    return Source(evidence, text)


@pytest.mark.parametrize(
    "reason,head",
    [
        ("VERIFICATION_FAILED", "AI 답변의 숫자·인용을 기록과 맞춰 보지 못해"),
        ("AI_UNAVAILABLE", "지금은 AI 답변을 만들 수 없어"),
    ],
)
def test_fallback_answer_lists_metrics_and_quotes(reason, head) -> None:
    text = templates.fallback_answer(reason, compute("CHANGES", records(), SCOPE), SCOPE)
    lines = text.split("\n")
    assert lines[0].startswith(head)
    assert lines[1] == PERIOD_LINE
    assert "- 학습한 활동: 3개" in lines
    assert "- 글자 수가 늘어난 시도: 1개 중 1개 (기록이 적어 비율은 표시하지 않아요)" in lines
    assert lines[-3:] == [
        "아이가 쓴 글:",
        "- 쉬는 시간 토론: 「나는 찬성해.」",
        "- 쉬는 시간 토론: 「나는 찬성해. 왜냐하면 쉬는 시간이 길면 더 잘 놀 수 있어.」",
    ]


def test_fallback_answer_without_sources_has_no_quote_block() -> None:
    text = templates.fallback_answer("AI_UNAVAILABLE", compute("COUNT", records(), SCOPE), SCOPE)
    assert "아이가 쓴 글:" not in text
    assert text.split("\n")[-1].startswith("- ")


def test_fallback_evidence_is_cut_and_limited() -> None:
    long_text = "가" * 100
    computation = Computation([], [source(i, long_text) for i in range(7)], 7)
    evidence = templates.fallback_evidence(computation)
    assert len(evidence) == 5
    assert all(e.quote == "가" * 60 for e in evidence)
    assert [e.answer_id for e in evidence] == [f"a-{i}" for i in range(5)]
    assert computation.sources[0].evidence.quote == long_text  # 원본은 그대로


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("NO_RECORD", "이 기간에 답변을 제출한 시도가 없어 분석할 기록이 없어요."),
        (
            "NO_CHANGES",
            "답변을 제출한 시도 4개 중 되묻기 뒤에 답변을 다시 쓴 시도가 없어 "
            "전후를 비교할 수 없어요.",
        ),
        ("NO_REFLECTIONS", "답변을 제출한 시도 4개 중 돌아보기를 쓴 시도가 없어요."),
    ],
)
def test_insufficient_answer(kind, reason) -> None:
    text = templates.insufficient_answer(kind, Computation([], [], 4, kind), SCOPE)
    assert text == f"{PERIOD_LINE} {reason} 기간을 넓히거나 다른 내용을 물어봐 주세요."


@pytest.mark.parametrize(
    "intent,head",
    [
        ("MATH_CHECK", "수학 풀이 점검은 아직 제공하지 않아요."),
        ("OTHER", "이 질문은 학습 기록으로 답할 수 없어요."),
    ],
)
def test_unsupported_answer(intent, head) -> None:
    text = templates.unsupported_answer(intent, Computation([], [], 3), SCOPE)
    assert text == (
        f"{head} {PERIOD_LINE} 답변을 제출한 시도는 3개예요. "
        f"{templates.AVAILABLE}에 대해 물어봐 주세요."
    )


@pytest.mark.parametrize(
    "numerator,denominator,formula,expected",
    [
        (3, 3, "기간 내 답변 제출이 있는 시도 수", "지표: 3개"),
        (0, 0, "분자 / 분모", "지표: 해당하는 시도가 없어요"),
        (1, 2, "분자 / 분모", "지표: 2개 중 1개 (기록이 적어 비율은 표시하지 않아요)"),
        (3, 6, "분자 / 분모", "지표: 6개 중 3개 (50%)"),
    ],
)
def test_metric_line(numerator, denominator, formula, expected) -> None:
    line = templates.metric_line(
        Metric.model_validate(metric("지표", numerator, denominator, formula))
    )
    assert line == expected
