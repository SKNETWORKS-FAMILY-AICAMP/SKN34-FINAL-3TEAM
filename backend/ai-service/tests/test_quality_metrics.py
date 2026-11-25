"""AI 품질 신호 카운터 (#1030): 경로마다 정확히 1회, 속성은 정해진 키와 코드값뿐."""

import pytest

from app import quality_metrics, tracing
from app.analysis_agent import templates
from app.analysis_agent.models import Verification
from app.analysis_agent.nodes import respond
from app.errors import ApiError
from app.llm.base import LlmError
from app.quality_metrics import ANALYSIS_FALLBACKS, GUARD_BLOCKED, JUDGMENT_RESULTS
from tests.analysis_agent.records_fixture import STUDENT
from tests.analysis_agent.test_nodes import run, state
from tests.fakes import FakeLlm
from tests.followup import test_service as followup
from tests.judgment import test_service as judgment
from tests.test_tracing import Telemetry

LEAK = "집중력 향상 때문일까?"  # followup make_request의 금지어
SAFE = "왜 그렇게 생각했는지 더 말해 볼까?"
KEYS = {
    JUDGMENT_RESULTS: {"result", "held_reason", "prompt_version"},
    ANALYSIS_FALLBACKS: {"reason"},
    GUARD_BLOCKED: {"guard"},
}


@pytest.fixture
def telemetry():
    recorded = Telemetry()
    tracing.install(recorded.tracer_provider, recorded.meter_provider)
    try:
        yield recorded
    finally:
        tracing.install()


def counts(telemetry: Telemetry, name: str) -> dict[tuple, int]:
    """속성 조합별 누적 건수. 한 번도 안 올렸으면 빈 dict."""
    return {
        tuple(sorted(point.attributes.items())): point.value for point in telemetry.points(name)
    }


def judged(**attributes: str) -> dict[tuple, int]:
    return {tuple(sorted(attributes.items())): 1}


# --- 판정 --------------------------------------------------------------------


def test_judgment_result_is_counted_once(telemetry) -> None:
    llm = FakeLlm(
        judgment.extraction(
            ("e1", "FOUND", "나는 찬성해"),
            ("e2", "FOUND", "쉬는 시간이 길면 더 잘 놀 수 있기 때문이야"),
        )
    )
    assert judgment.judge(llm).result == "CORRECT"
    assert counts(telemetry, JUDGMENT_RESULTS) == judged(
        result="CORRECT", held_reason="none", prompt_version="judge@2"
    )
    assert counts(telemetry, GUARD_BLOCKED) == {}


def test_held_before_llm_is_counted_without_prompt_version(telemetry) -> None:
    response = judgment.judge(FakeLlm(), judgment.make_request(answerText=" 몰 라 요 "))
    assert (response.result, response.held_reason) == ("HELD", "TOO_SHORT")
    assert counts(telemetry, JUDGMENT_RESULTS) == judged(
        result="HELD", held_reason="TOO_SHORT", prompt_version="none"
    )
    assert counts(telemetry, GUARD_BLOCKED) == {}


def test_quote_mismatch_is_held_and_guard_block(telemetry) -> None:
    llm = FakeLlm(
        judgment.extraction(("e1", "FOUND", "나는 찬성해"), ("e2", "FOUND", "시간이 절약되니까"))
    )
    assert judgment.judge(llm).held_reason == "QUOTE_MISMATCH"
    assert counts(telemetry, JUDGMENT_RESULTS) == judged(
        result="HELD", held_reason="QUOTE_MISMATCH", prompt_version="judge@2"
    )
    assert counts(telemetry, GUARD_BLOCKED) == judged(guard="judgment_quote")


def test_judgment_503_is_not_counted(telemetry) -> None:
    with pytest.raises(ApiError):
        judgment.judge(FakeLlm(LlmError("LLM_TIMEOUT", retryable=True)))
    assert counts(telemetry, JUDGMENT_RESULTS) == {}
    assert counts(telemetry, GUARD_BLOCKED) == {}


# --- 분석 대체 응답 ----------------------------------------------------------


@pytest.mark.parametrize(
    "reason,extra",
    [
        ("AI_UNAVAILABLE", {}),
        (
            "VERIFICATION_FAILED",
            {
                "verification": Verification(
                    numbers_matched=False, quotes_matched=True, content_allowed=True
                )
            },
        ),
    ],
)
def test_analysis_fallback_is_counted_once(telemetry, reason, extra) -> None:
    update, _ = run(respond.fallback, state("CHANGES", fallback_reason=reason, **extra))
    assert update["result"].fallback.reason == reason
    assert counts(telemetry, ANALYSIS_FALLBACKS) == judged(reason=reason)


@pytest.mark.parametrize(
    "node,current",
    [
        (respond.insufficient, state("COUNT", empty=True)),
        (respond.unsupported, state("MATH_CHECK")),
        (respond.unsupported, state("OTHER")),
    ],
)
def test_analysis_notice_is_not_fallback(telemetry, node, current) -> None:
    update, _ = run(node, current)
    assert update["result"].notice is not None
    assert counts(telemetry, ANALYSIS_FALLBACKS) == {}


def test_unverified_fallback_template_is_not_counted(telemetry, monkeypatch) -> None:
    monkeypatch.setattr(templates, "fallback_answer", lambda *args: "99999개 활동이에요.")
    update, _ = run(respond.fallback, state("CHANGES", fallback_reason="AI_UNAVAILABLE"))
    assert "error" in update
    assert counts(telemetry, ANALYSIS_FALLBACKS) == {}


# --- 되묻기 누출 차단 --------------------------------------------------------


@pytest.mark.parametrize(
    "steps,blocked",
    [
        ((SAFE,), 0),
        ((LEAK, SAFE), 1),  # 재생성으로 통과
        ((LEAK, LEAK), 2),  # 재생성도 누출 → 질문 은행
    ],
)
def test_followup_leak_counts_each_discarded_question(telemetry, steps, blocked) -> None:
    followup.create(FakeLlm(*(followup.question(text) for text in steps)))
    expected = {(("guard", "followup_leak"),): blocked} if blocked else {}
    assert counts(telemetry, GUARD_BLOCKED) == expected


def test_empty_followup_question_is_not_leak(telemetry) -> None:
    followup.create(FakeLlm(followup.question(" "), followup.question(SAFE)))
    assert counts(telemetry, GUARD_BLOCKED) == {}


# --- 속성 --------------------------------------------------------------------


def test_attributes_are_fixed_keys_without_text_or_ids(telemetry) -> None:
    judgment.judge(
        FakeLlm(
            judgment.extraction(
                ("e1", "FOUND", "나는 찬성해"), ("e2", "FOUND", "시간이 절약되니까")
            )
        )
    )
    run(respond.fallback, state("CHANGES", fallback_reason="AI_UNAVAILABLE"))
    followup.create(FakeLlm(followup.question(LEAK), followup.question(SAFE)))
    private = {judgment.ANSWER, LEAK, SAFE, STUDENT, "c-1"}  # 답변·질문 원문, 학생·대화 ID
    for name, keys in KEYS.items():
        points = telemetry.points(name)
        assert points, name
        for point in points:
            assert set(point.attributes) == keys
            assert not private & {str(value) for value in point.attributes.values()}
            assert all(len(str(value)) <= 40 for value in point.attributes.values())


def test_no_provider_is_noop() -> None:
    tracing.install()
    quality_metrics.judgment_result("HELD", "TOO_SHORT", None)
    quality_metrics.analysis_fallback("AI_UNAVAILABLE")
    quality_metrics.guard_blocked("followup_leak")
