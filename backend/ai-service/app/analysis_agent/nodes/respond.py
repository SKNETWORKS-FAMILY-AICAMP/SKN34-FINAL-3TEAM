"""답변 작성 → 대조 → 확정, 또는 코드 문장 (P16, FN-AGT-06·09).

LLM 답변은 대조를 통과해야만 확정. 실패하면 LLM 문장을 버리고 계산 수치·원문 템플릿.
"""

from langgraph.runtime import Runtime

from app.analysis_agent import prompts, templates
from app.analysis_agent.calculators import Computation
from app.analysis_agent.models import (
    AnalysisResult,
    Evidence,
    Fallback,
    LlmVersions,
    ResultScope,
    Scope,
    Verification,
)
from app.analysis_agent.nodes.events import status
from app.analysis_agent.state import AgentContext, AnalysisState
from app.analysis_agent.verification import verify
from app.llm.base import LlmUnavailable


async def answer(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    runtime.stream_writer(status("답변을 쓰는 중"))
    request = state["request"]
    try:
        result = await runtime.context.llm.generate(
            system=prompts.ANSWER_SYSTEM,
            user=prompts.build_answer_user(request, state["intent"], state["computation"]),
            output=prompts.AnswerDraft,
            call_type="ANALYSIS",
            prompt_version=prompts.PROMPT_VERSION,
            max_tokens=1024,
            deadline=runtime.context.deadline,
        )
    except LlmUnavailable:
        return {"fallback_reason": "AI_UNAVAILABLE"}
    return {"draft": result.data, "model": result.model}


async def check(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    runtime.stream_writer(status("숫자와 인용을 기록과 맞춰 보는 중"))
    draft = state["draft"]
    computation = state["computation"]
    checked = verify(draft.answer, draft.citations, computation)
    if not checked.passed:
        return {"verification": checked.verification, "fallback_reason": "VERIFICATION_FAILED"}
    return {
        "result": _result(
            state,
            text=draft.answer.strip(),
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
    return {
        "result": _result(
            state,
            text=text,
            source="TEMPLATE",
            evidence=templates.fallback_evidence(computation),
            verification=state.get("verification"),
            fallback=Fallback(reason=reason),
        )
    }


async def insufficient(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    """기록 부족 안내 (FN-AGT-09). 대체 응답이 아니라 정해진 안내라 fallback 없음."""
    computation = state["computation"]
    assert computation.insufficient is not None
    text = templates.insufficient_answer(
        computation.insufficient, computation, state["request"].scope
    )
    return {"result": _result(state, text=text, source="TEMPLATE", evidence=[])}


async def unsupported(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    """제공하지 않는 질문(수학 점검·기록 밖 질문) 안내 (FN-AGT-04·12)."""
    text = templates.unsupported_answer(
        state["intent"], state["computation"], state["request"].scope
    )
    return {"result": _result(state, text=text, source="TEMPLATE", evidence=[])}


def _result(
    state: AnalysisState,
    *,
    text: str,
    source: str,
    evidence: list[Evidence],
    verification: Verification | None = None,
    fallback: Fallback | None = None,
) -> AnalysisResult:
    computation: Computation = state["computation"]
    scope: Scope = state["request"].scope
    return AnalysisResult(
        answer=text,
        source=source,  # type: ignore[arg-type]
        fallback=fallback,
        scope=ResultScope.model_validate(
            {"childId": scope.student_id, "from": scope.from_, "to": scope.to}
        ),
        metrics=computation.metrics,
        evidence=evidence,
        verification=verification,
        record_count=computation.record_count,
        versions=LlmVersions(model=state.get("model"), prompt=prompts.PROMPT_VERSION),
    )
