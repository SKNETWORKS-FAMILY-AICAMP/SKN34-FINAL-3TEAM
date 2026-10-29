"""분석 대화 그래프의 상태와 실행 컨텍스트.

ai-service는 대화를 저장하지 않으므로 체크포인터 없이 요청마다 처음부터 실행.
이전 대화는 core가 history로 넘김.
범위 확인은 clarification 후 종료 → 사용자가 고른 범위로 core가 다시 요청.
"""

from dataclasses import dataclass
from typing import TypedDict

from app.analysis_agent.metrics import Computation
from app.analysis_agent.models import (
    AnalysisRequest,
    AnalysisResult,
    Clarification,
    FallbackReason,
    Intent,
    Records,
    StreamError,
    Verification,
)
from app.analysis_agent.prompts import AnswerDraft
from app.analysis_agent.records import LearningRecords
from app.llm.base import LlmClient


class AnalysisState(TypedDict, total=False):
    request: AnalysisRequest
    intent: Intent
    model: str | None  # 마지막으로 응답한 LLM 모델
    fallback_reason: FallbackReason | None
    clarification: Clarification
    records: Records
    computation: Computation
    draft: AnswerDraft
    verification: Verification
    # 끝 상태: 셋 중 하나가 채워지면 종료
    result: AnalysisResult
    error: StreamError


@dataclass(frozen=True)
class AgentContext:
    llm: LlmClient
    records: LearningRecords
    deadline: float  # time.monotonic 기준 전체 마감 (P12 분석 대화 전체 120초 안)
