"""질문 분류·범위 확인 (FN-AGT-03).

대상·기간이 골라 둔 범위와 다르거나 불명확하면 임의로 정하지 않고 clarification으로 끝냄.
LLM 장애면 분류 없이 기본 수치(COUNT)만 계산해 규칙 응답 모드로 (P16).
"""

from langgraph.runtime import Runtime

from app.analysis_agent import prompts
from app.analysis_agent.models import Clarification, ResultScope
from app.analysis_agent.nodes.events import status
from app.analysis_agent.state import AgentContext, AnalysisState
from app.llm.base import LlmUnavailable

CLARIFY_MESSAGES = {
    "OTHER_CHILD": (
        "지금은 골라 둔 자녀의 기록만 볼 수 있어요. 다른 자녀는 자녀를 바꾼 뒤 다시 물어봐 주세요."
    ),
    "DIFFERENT_PERIOD": "질문한 기간이 골라 둔 조회 기간과 달라요. 어느 기간을 볼지 골라 주세요.",
    "UNCLEAR": "어느 자녀의 어떤 기간 기록을 볼지 확인이 필요해요. 자녀와 기간을 골라 주세요.",
}


async def classify(state: AnalysisState, runtime: Runtime[AgentContext]) -> AnalysisState:
    runtime.stream_writer(status("질문을 확인하는 중"))
    request = state["request"]
    try:
        result = await runtime.context.llm.generate(
            system=prompts.CLASSIFY_SYSTEM,
            user=prompts.build_classify_user(request),
            output=prompts.Classification,
            call_type="ANALYSIS",
            prompt_version=prompts.PROMPT_VERSION,
            max_tokens=256,
            deadline=runtime.context.deadline,
        )
    except LlmUnavailable:
        return {"intent": "COUNT", "fallback_reason": "AI_UNAVAILABLE"}
    update: AnalysisState = {"intent": result.data.intent, "model": result.model}
    issue = result.data.scope_issue
    if issue != "NONE":
        scope = request.scope
        update["clarification"] = Clarification(
            reason=issue,
            message=CLARIFY_MESSAGES[issue],
            current=ResultScope.model_validate(
                {"childId": scope.student_id, "from": scope.from_, "to": scope.to}
            ),
        )
    return update
