"""분석 대화 그래프 실행 컨텍스트 (노드가 쓰는 LLM·기록 도구·기한·프롬프트·오늘 날짜)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone

from app.analysis_agent.tools import RecordTools
from app.llm.base import LlmClient
from app.prompt_versions.models import PromptChoice

# 한국 시간. 서머타임이 없어 고정 오프셋으로 충분하고 tzdata 패키지가 필요 없음
KST = timezone(timedelta(hours=9), "KST")


def kst_today(now: datetime | None = None) -> date:
    """요청 시각 기준 한국 날짜. now는 시간대가 있는 시각(기본은 현재 UTC)."""
    return (now or datetime.now(UTC)).astimezone(KST).date()


@dataclass(frozen=True)
class AgentContext:
    llm: LlmClient
    tools: RecordTools
    deadline: float  # time.monotonic 기준 전체 마감 (P12 분석 대화 전체 120초 안)
    prompt: PromptChoice
    today: date  # 요청 시작 때 정한 한국 날짜. "오늘·어제" 같은 질문 해석 기준 (#454)
