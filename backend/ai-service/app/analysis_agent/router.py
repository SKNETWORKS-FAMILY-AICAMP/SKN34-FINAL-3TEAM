"""POST /internal/analysis/stream (SSE, API 명세서 3.3·4.2).

이벤트: status* → result → done | clarification(종료) | error(종료).
delta는 보내지 않음: 답변은 숫자·인용 대조를 통과한 뒤에만 보여 주므로 임시 텍스트를 흘리지 않음.
"""

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.analysis_agent.graph import build_graph
from app.analysis_agent.models import AnalysisRequest, StreamError
from app.analysis_agent.records import HttpLearningRecords, LearningRecords
from app.analysis_agent.state import AgentContext, AnalysisState
from app.config import get_settings
from app.llm.base import LlmClient
from app.llm.providers import get_llm
from app.security import UserContext, get_user_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/analysis", tags=["analysis"])


def get_learning_records(
    user: Annotated[UserContext, Depends(get_user_context)],
) -> LearningRecords:
    return HttpLearningRecords(get_settings().learning_url, user)


@router.post("/stream")
async def stream(
    body: AnalysisRequest,
    user: Annotated[UserContext, Depends(get_user_context)],
    llm: Annotated[LlmClient, Depends(get_llm)],
    records: Annotated[LearningRecords, Depends(get_learning_records)],
) -> StreamingResponse:
    # 질문마다 권한 확인 (FN-AGT-02). 스트림 시작 전이라 일반 403 응답
    user.require_student(body.scope.student_id)
    deadline = time.monotonic() + get_settings().analysis_deadline
    context = AgentContext(llm=llm, records=records, deadline=deadline)
    return StreamingResponse(
        _events(body, context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _events(body: AnalysisRequest, context: AgentContext) -> AsyncIterator[str]:
    try:
        async for event in _run(body, context):
            yield event
    finally:
        await context.records.aclose()


async def _run(body: AnalysisRequest, context: AgentContext) -> AsyncIterator[str]:
    final: AnalysisState = {}
    try:
        async for mode, chunk in build_graph().astream(
            {"request": body}, context=context, stream_mode=["custom", "values"]
        ):
            if mode == "custom":
                yield sse(chunk["event"], chunk["data"])
            else:
                final = chunk
    except Exception:  # noqa: BLE001 - 스트림 도중 실패도 error 이벤트로 알림
        logger.exception("분석 대화 처리 실패")
        error = StreamError(
            code="INTERNAL_ERROR", message="답변을 만들지 못했어요.", retryable=True
        )
        yield sse("error", error)
        return

    if "clarification" in final:
        yield sse("clarification", final["clarification"])
    elif "error" in final:
        yield sse("error", final["error"])
    elif "result" in final:
        yield sse("result", final["result"])
        yield sse("done", {})
    else:
        logger.error("분석 대화 그래프가 결과 없이 끝남: keys=%s", sorted(final))
        error = StreamError(
            code="INTERNAL_ERROR", message="답변을 만들지 못했어요.", retryable=True
        )
        yield sse("error", error)


def sse(event: str, data: BaseModel | dict[str, Any]) -> str:
    payload = data.model_dump(mode="json", by_alias=True) if isinstance(data, BaseModel) else data
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
