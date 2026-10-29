"""답변 작성 → 대조 → 확정, 또는 코드 문장 (P16, FN-AGT-06·09).

LLM 답변은 조각마다 delta로 임시 표시하고, 대조를 통과해야만 result로 확정.
실패하면 LLM 문장(보낸 delta 포함)을 버리고 계산 수치·원문 템플릿.
"""

from langgraph.runtime import Runtime

from app.analysis_agent import prompts, templates
from app.analysis_agent.calculators import Computation
from app.analysis_agent.models import (
    AnalysisResult,
    Evidence,
    Fallback,
    LlmVersions,
    Notice,
    ResultScope,
    Scope,
    StreamError,
    Verification,
)
from app.analysis_agent.nodes.events import delta, status
from app.analysis_agent.state import AgentContext, AnalysisState
from app.analysis_agent.verification import verify
from app.llm.base import LlmUnavailable


async def answer(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    runtime.stream_writer(status("답변을 쓰는 중"))
    request = state["request"]
    stream = runtime.context.llm.stream(
        system=prompts.ANSWER_SYSTEM,
        user=prompts.build_answer_user(request, state["intent"], state["computation"]),
        call_type="ANALYSIS",
        prompt_version=prompts.PROMPT_VERSION,
        max_tokens=1024,
        deadline=runtime.context.deadline,
    )
    parts: list[str] = []
    try:
        async for text in stream:
            parts.append(text)
            runtime.stream_writer(delta(text))
    except LlmUnavailable:
        # 첫 조각 뒤 실패도 재시도 없이 규칙 응답 (보낸 delta는 core·web이 폐기)
        return {"fallback_reason": "AI_UNAVAILABLE"}
    return {"draft": "".join(parts), "model": stream.model}


async def check(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    runtime.stream_writer(status("숫자와 인용을 기록과 맞춰 보는 중"))
    draft = state["draft"]
    checked = verify(draft, state["computation"])
    if not checked.passed:
        return {"verification": checked.verification, "fallback_reason": "VERIFICATION_FAILED"}
    return {
        "result": _result(
            state,
            text=draft.strip(),
            source="LLM",
            evidence=checked.evidence,
            verification=checked.verification,
        )
    }


async def fallback(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    """규칙 응답 모드: 계산 수치·원문 목록 템플릿 (P16)."""
    reason = state["fallback_reason"]
    assert reason is not None
    computation = state["computation"]
    text = templates.fallback_answer(reason, computation, state["request"].scope)
    return _checked_template(
        state,
        text,
        fallback=Fallback(reason=reason, draft_verification=state.get("verification")),
    )


async def insufficient(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    """기록 부족 안내 (FN-AGT-09). 대체 응답이 아니라 정해진 안내라 fallback 없음."""
    computation = state["computation"]
    assert computation.insufficient is not None
    text = templates.insufficient_answer(
        computation.insufficient, computation, state["request"].scope
    )
    return _checked_template(state, text, notice=Notice(reason=computation.insufficient))


async def unsupported(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    """제공하지 않는 질문(수학 점검·기록 밖 질문) 안내 (FN-AGT-04·12)."""
    text = templates.unsupported_answer(
        state["intent"], state["computation"], state["request"].scope
    )
    return _checked_template(
        state,
        text,
        notice=Notice(reason="MATH_CHECK" if state["intent"] == "MATH_CHECK" else "UNSUPPORTED"),
    )


def _checked_template(
    state: AnalysisState,
    text: str,
    *,
    fallback: Fallback | None = None,
    notice: Notice | None = None,
) -> AnalysisState:
    checked = verify(text, state["computation"])
    if not checked.passed:
        return {
            "error": StreamError(
                code="FINAL_RESPONSE_VERIFICATION_FAILED",
                message="최종 안내를 기록과 대조하지 못했어요.",
                retryable=True,
            )
        }
    return {
        "result": _result(
            state,
            text=text,
            source="TEMPLATE",
            evidence=checked.evidence,
            verification=checked.verification,
            fallback=fallback,
            notice=notice,
        )
    }


def _result(
    state: AnalysisState,
    *,
    text: str,
    source: str,
    evidence: list[Evidence],
    verification: Verification,
    fallback: Fallback | None = None,
    notice: Notice | None = None,
) -> AnalysisResult:
    computation: Computation = state["computation"]
    scope: Scope = state["request"].scope
    return AnalysisResult(
        answer=text,
        source=source,  # type: ignore[arg-type]
        fallback=fallback,
        notice=notice,
        scope=ResultScope.model_validate(
            {"childId": scope.student_id, "from": scope.from_, "to": scope.to}
        ),
        metrics=computation.metrics,
        evidence=evidence,
        verification=verification,
        record_count=computation.record_count,
        versions=LlmVersions(model=state.get("model"), prompt=prompts.PROMPT_VERSION),
    )
