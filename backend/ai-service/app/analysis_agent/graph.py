"""분석 대화 LangGraph (아키텍처 1.5, FN-AGT-02~10).

START → classify ─(범위 불명확·충돌)→ END [clarification]
              └→ retrieve ─(조회 실패)→ END [error]
                        └→ compute ─(기록 부족)→ insufficient → END
                                   ├(수학 점검·기록 밖 질문)→ unsupported → END
                                   ├(LLM 장애)→ fallback → END
                                   └→ answer ─(LLM 장애)→ fallback → END
                                             └→ check ─(대조 실패)→ fallback → END
                                                      └(통과)→ END [result: LLM]
"""

from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.analysis_agent.nodes import respond, retrieve, understand
from app.analysis_agent.state import AgentContext, AnalysisState

UNSUPPORTED_INTENTS = ("MATH_CHECK", "OTHER")


def after_classify(state: AnalysisState) -> str:
    return END if "clarification" in state else "retrieve"


def after_retrieve(state: AnalysisState) -> str:
    return END if "error" in state else "compute"


def after_compute(state: AnalysisState) -> str:
    if state.get("fallback_reason"):
        return "fallback"
    if state["computation"].insufficient:
        return "insufficient"
    if state["intent"] in UNSUPPORTED_INTENTS:
        return "unsupported"
    return "answer"


def after_answer(state: AnalysisState) -> str:
    return "fallback" if state.get("fallback_reason") else "check"


def after_check(state: AnalysisState) -> str:
    return END if "result" in state else "fallback"


@lru_cache
def build_graph() -> CompiledStateGraph:
    graph = StateGraph(AnalysisState, context_schema=AgentContext)
    graph.add_node("classify", understand.classify)
    graph.add_node("retrieve", retrieve.retrieve)
    graph.add_node("compute", retrieve.compute)
    graph.add_node("answer", respond.answer)
    graph.add_node("check", respond.check)
    graph.add_node("fallback", respond.fallback)
    graph.add_node("insufficient", respond.insufficient)
    graph.add_node("unsupported", respond.unsupported)

    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", after_classify, ["retrieve", END])
    graph.add_conditional_edges("retrieve", after_retrieve, ["compute", END])
    graph.add_conditional_edges(
        "compute", after_compute, ["insufficient", "unsupported", "fallback", "answer"]
    )
    graph.add_conditional_edges("answer", after_answer, ["fallback", "check"])
    graph.add_conditional_edges("check", after_check, ["fallback", END])
    for node in ("fallback", "insufficient", "unsupported"):
        graph.add_edge(node, END)
    return graph.compile(name="analysis_agent")
