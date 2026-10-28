"""기록 조회와 수치 고르기.

도구 선택은 질문 유형 → 도구 표로 정함. 유형이 6가지로 정해져 있어 LLM 도구 선택보다 싸고
예측 가능함. 요약(집계 대상 시도 수 포함)은 모든 유형에서 조회하고, 나머지는 필요한 것만.
"""

import asyncio
from typing import Any

from langgraph.runtime import Runtime

from app.analysis_agent.metrics import THOUGHT_LIMIT
from app.analysis_agent.metrics import compute as compute_metrics
from app.analysis_agent.models import Intent, Records, Scope, StreamError
from app.analysis_agent.nodes.events import status
from app.analysis_agent.records import LearningRecords, RecordsUnavailable
from app.analysis_agent.state import AgentContext, AnalysisState

ERROR_MESSAGES = {
    "FORBIDDEN": "이 자녀의 기록을 조회할 권한이 없어요.",
    "RECORDS_NOT_READY": "기록을 집계하는 중이에요. 잠시 뒤 다시 물어봐 주세요.",
}
DEFAULT_ERROR = "기록을 불러오지 못했어요. 잠시 뒤 다시 물어봐 주세요."


async def retrieve(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    runtime.stream_writer(status("기록을 조회하는 중"))
    scope = state["request"].scope
    calls = tool_calls(state["intent"], runtime.context.records, scope)
    # 모두 끝까지 기다린 뒤 첫 실패를 씀 (나머지 실패가 처리되지 않은 채 남지 않게)
    results = await asyncio.gather(*calls.values(), return_exceptions=True)
    for result in results:
        if isinstance(result, RecordsUnavailable):
            # 조회 실패를 기록 없음으로 바꾸지 않음 (FN-AGT-10)
            message = ERROR_MESSAGES.get(result.code, DEFAULT_ERROR)
            return {
                "error": StreamError(code=result.code, message=message, retryable=result.retryable)
            }
        if isinstance(result, BaseException):
            raise result
    return {"records": Records(**dict(zip(calls, results, strict=True)))}


def tool_calls(intent: Intent, tools: LearningRecords, scope: Scope) -> dict[str, Any]:
    """질문 유형 → 조회할 도구. 키는 Records 필드 이름."""
    calls: dict[str, Any] = {"summary": tools.summary(scope)}
    if intent == "THINKING_TYPES":
        calls["thinking_types"] = tools.thinking_types(scope)
    elif intent == "CHILD_THOUGHTS":
        calls["attempts"] = tools.recent_attempts(scope, THOUGHT_LIMIT)
    elif intent == "CHANGES":
        calls["changes"] = tools.changes(scope)
        calls["activities"] = tools.thinking_activities(scope)  # 원문 근거의 미션 제목
    elif intent == "REFLECTIONS":
        calls["activities"] = tools.thinking_activities(scope)
    return calls


async def compute(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    runtime.stream_writer(status("수치를 계산하는 중"))
    computation = compute_metrics(state["intent"], state["records"], state["request"].scope)
    return {"computation": computation}
