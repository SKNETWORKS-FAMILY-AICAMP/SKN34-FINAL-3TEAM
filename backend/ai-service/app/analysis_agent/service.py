"""분석 대화 흐름: 범위 확인·기한·프롬프트 선택 → 그래프 실행 → 최종 상태를 이벤트로 (API 3.3·4.2).

이벤트: status* → delta* → result → done | clarification(종료) | error(종료).
delta는 LLM 답변 조각(대조 전 임시 표시). 확정 답변은 대조를 통과한 result.answer뿐.
core가 연결을 끊으면 이벤트 생성기가 취소되어 그래프·LLM 스트림도 멈춤.
"""

import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from pydantic import BaseModel

from app.analysis_agent.context import AgentContext
from app.analysis_agent.graph import build_graph
from app.analysis_agent.models import AnalysisRequest, StreamError
from app.analysis_agent.state import AnalysisState
from app.analysis_agent.template_settings import (
    TemplateProposal,
    TemplateProposalRequest,
    propose_template,
)
from app.analysis_agent.tools import RecordTools
from app.clients.learning_client import LearningClient
from app.config import Settings
from app.errors import ApiError
from app.llm.base import LlmClient
from app.prompt_versions.registry import ActiveVersions
from app.security import UserContext

logger = logging.getLogger(__name__)

Event = tuple[str, BaseModel | dict[str, Any]]


class AnalysisService:
    def __init__(
        self,
        llm: LlmClient,
        settings: Settings,
        versions: ActiveVersions,
        learning_factory: Callable[[UserContext], LearningClient] | None = None,
    ) -> None:
        self._llm = llm
        self._settings = settings
        self._versions = versions
        self._learning_factory = learning_factory or (
            lambda user: LearningClient(settings.learning_url, user)
        )

    def stream(self, body: AnalysisRequest, user: UserContext) -> AsyncIterator[Event]:
        """스트림 시작 전 확인(403·503)은 바로 실행해 일반 오류 응답으로 내보냄."""
        # 질문마다 권한 확인 (FN-AGT-02)
        user.require_student(body.scope.student_id)
        deadline = time.monotonic() + self._settings.analysis_deadline
        prompt = self._versions.prompt("analysis")
        # 프롬프트 선택 뒤에 연결을 만들어 선택 실패 시 닫을 연결이 없음
        tools = RecordTools(self._learning_factory(user), user)
        context = AgentContext(llm=self._llm, tools=tools, deadline=deadline, prompt=prompt)
        return self._events(body, context)

    async def propose_template(
        self, body: TemplateProposalRequest, user: UserContext
    ) -> TemplateProposal:
        if user.role != "PARENT" or not user.user_id:
            raise ApiError(403, "FORBIDDEN", "학부모 컨텍스트가 필요합니다.")
        return await propose_template(body, self._llm)

    async def _events(self, body: AnalysisRequest, context: AgentContext) -> AsyncIterator[Event]:
        try:
            async for event in self._run(body, context):
                yield event
        finally:
            await context.tools.aclose()

    async def _run(self, body: AnalysisRequest, context: AgentContext) -> AsyncIterator[Event]:
        final: AnalysisState = {}
        try:
            async for mode, chunk in build_graph().astream(
                {"request": body, "prompt_version": context.prompt.version},
                context=context,
                stream_mode=["custom", "values"],
            ):
                if mode == "custom":
                    yield chunk["event"], chunk["data"]
                else:
                    final = chunk
        except Exception:  # noqa: BLE001 - 스트림 도중 실패도 error 이벤트로 알림
            logger.exception("분석 대화 처리 실패")
            yield "error", _internal_error()
            return

        if "clarification" in final:
            yield "clarification", final["clarification"]
        elif "error" in final:
            yield "error", final["error"]
        elif "result" in final:
            yield "result", final["result"]
            yield "done", {}
        else:
            logger.error("분석 대화 그래프가 결과 없이 끝남: keys=%s", sorted(final))
            yield "error", _internal_error()


def _internal_error() -> StreamError:
    return StreamError(code="INTERNAL_ERROR", message="답변을 만들지 못했어요.", retryable=True)
