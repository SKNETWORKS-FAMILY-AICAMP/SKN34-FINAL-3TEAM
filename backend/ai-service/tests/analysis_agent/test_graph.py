"""분석 대화 그래프 분기 함수 (상태 → 다음 노드)."""

import pytest
from langgraph.graph import END

from app.analysis_agent.calculators import Computation
from app.analysis_agent.graph import (
    after_answer,
    after_check,
    after_classify,
    after_compute,
    after_retrieve,
    build_graph,
)


def computation(insufficient: str | None = None) -> Computation:
    return Computation([], [], 0, insufficient)


def test_classify_ends_on_clarification() -> None:
    assert after_classify({"clarification": object()}) == END
    assert after_classify({"intent": "COUNT"}) == "retrieve"


def test_retrieve_ends_on_error() -> None:
    assert after_retrieve({"error": object()}) == END
    assert after_retrieve({"records": object()}) == "compute"


@pytest.mark.parametrize(
    "fallback_reason,insufficient,intent,expected",
    [
        ("AI_UNAVAILABLE", "NO_RECORD", "COUNT", "fallback"),  # LLM 장애가 기록 부족보다 먼저
        (None, "NO_RECORD", "MATH_CHECK", "insufficient"),  # 기록 부족이 미지원보다 먼저
        (None, None, "MATH_CHECK", "unsupported"),
        (None, None, "OTHER", "unsupported"),
        (None, None, "CHANGES", "answer"),
    ],
)
def test_compute_branches(fallback_reason, insufficient, intent, expected) -> None:
    state = {
        "fallback_reason": fallback_reason,
        "computation": computation(insufficient),
        "intent": intent,
    }
    assert after_compute(state) == expected


def test_answer_and_check_branches() -> None:
    assert after_answer({"fallback_reason": "AI_UNAVAILABLE"}) == "fallback"
    assert after_answer({"draft": "답변"}) == "check"
    assert after_check({"result": object()}) == END
    assert after_check({"fallback_reason": "VERIFICATION_FAILED"}) == "fallback"


def test_graph_has_all_nodes() -> None:
    assert set(build_graph().get_graph().nodes) == {
        "__start__",
        "__end__",
        "classify",
        "retrieve",
        "compute",
        "answer",
        "check",
        "fallback",
        "insufficient",
        "unsupported",
    }
