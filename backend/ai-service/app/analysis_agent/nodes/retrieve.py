"""기록 조회와 수치 계산.

도구 선택은 질문 유형 → 도구 표로 정함. 유형이 6가지로 정해져 있어 LLM 도구 선택보다 싸고
예측 가능함. 시도 목록은 집계 대상 판정(P08)에 항상 필요해 모든 유형에서 조회.
"""

import asyncio

from langgraph.runtime import Runtime

from app.analysis_agent.metrics import compute as compute_metrics
from app.analysis_agent.models import Records, StreamError
from app.analysis_agent.nodes.events import status
from app.analysis_agent.records import RecordsUnavailable
from app.analysis_agent.state import AgentContext, AnalysisState

ERROR_MESSAGES = {
    "FORBIDDEN": "이 자녀의 기록을 조회할 권한이 없어요.",
    "RECORDS_NOT_READY": "기록을 집계하는 중이에요. 잠시 뒤 다시 물어봐 주세요.",
}
DEFAULT_ERROR = "기록을 불러오지 못했어요. 잠시 뒤 다시 물어봐 주세요."


async def retrieve(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    runtime.stream_writer(status("기록을 조회하는 중"))
    scope = state["request"].scope
    tools = runtime.context.records
    intent = state["intent"]
    try:
        attempts, thinking_types, changes = await asyncio.gather(
            tools.attempts(scope),
            tools.thinking_types(scope) if intent == "THINKING_TYPES" else _none(),
            tools.changes(scope) if intent == "CHANGES" else _none(),
        )
    except RecordsUnavailable as exc:
        # 조회 실패를 기록 없음으로 바꾸지 않음 (FN-AGT-10)
        message = ERROR_MESSAGES.get(exc.code, DEFAULT_ERROR)
        return {"error": StreamError(code=exc.code, message=message, retryable=exc.retryable)}
    return {"records": Records(attempts=attempts, thinking_types=thinking_types, changes=changes)}


async def compute(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    runtime.stream_writer(status("수치를 계산하는 중"))
    computation = compute_metrics(state["intent"], state["records"], state["request"].scope)
    return {"computation": computation}


async def _none() -> None:
    return None
