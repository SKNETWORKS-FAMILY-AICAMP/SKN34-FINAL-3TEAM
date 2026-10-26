"""설정(LLM_PROVIDER)으로 제공자 선택. 제공자 추가 시 여기에 분기 1개 추가."""

from fastapi import Request

from app.config import Settings
from app.llm.anthropic_client import AnthropicLlm
from app.llm.base import LlmClient, UnconfiguredLlm, UsageRecorder


def get_llm(request: Request) -> LlmClient:
    """라우터 의존성: 기동 시 만든 app.state.llm. 테스트는 dependency_overrides로 교체."""
    return request.app.state.llm


def create_llm(settings: Settings, recorder: UsageRecorder) -> LlmClient:
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            return UnconfiguredLlm(settings.anthropic_model, recorder)
        return AnthropicLlm(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            effort=settings.anthropic_effort,
            fallback=settings.anthropic_fallback,
            timeout=settings.llm_timeout,
            max_retries=settings.llm_max_retries,
            backoff_seconds=settings.llm_retry_backoff,
            recorder=recorder,
        )
    raise ValueError(f"지원하지 않는 LLM_PROVIDER: {settings.llm_provider}")
