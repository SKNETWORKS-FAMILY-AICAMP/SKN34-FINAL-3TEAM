"""분석 대화 그래프 실행 컨텍스트 (노드가 쓰는 LLM·기록 도구·기한·프롬프트)."""

from dataclasses import dataclass

from app.analysis_agent.tools import RecordTools
from app.llm.base import LlmClient
from app.prompt_versions.models import PromptChoice


@dataclass(frozen=True)
class AgentContext:
    llm: LlmClient
    tools: RecordTools
    deadline: float  # time.monotonic 기준 전체 마감 (P12 분석 대화 전체 120초 안)
    prompt: PromptChoice
