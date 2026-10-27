"""LLM 제공자 모음과 선택. 판정·되묻기는 base.LlmClient.generate만 사용하고 제공자를 모름.

목차
  1. Claude          AnthropicLlm          LLM_PROVIDER=anthropic
  2. OpenAI·sLLM     OpenAICompatibleLlm   LLM_PROVIDER=openai (vLLM·Ollama는 OPENAI_BASE_URL 지정)
  3. 제공자 선택      create_llm·get_llm    제공자 추가 시 여기에 분기 1개 추가

각 제공자는 요청 1회만 담당 (재시도·타임아웃·사용량 기록은 base.py).
구조화 출력은 JSON 스키마로 요청하고 검증은 직접 수행해, 형식이 깨진 응답도 토큰 사용량을 남김.
"""

import json
from typing import Any, Literal

import anthropic
import openai
from fastapi import Request
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.llm.base import (
    LlmClient,
    LlmError,
    LlmRequest,
    ProviderResponse,
    T,
    UnconfiguredLlm,
    UsageRecorder,
    status_error,
)

# ---------------------------------------------------------------------------
# 1. Claude
# ---------------------------------------------------------------------------

# fallbacks="default": 안전 거절 시 Anthropic이 거절 유형별 권장 모델로 재처리
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicLlm(LlmClient):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        effort: str,
        fallback: bool,
        timeout: float,
        max_retries: int,
        backoff_seconds: float,
        recorder: UsageRecorder,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        super().__init__(model, max_retries, recorder, backoff_seconds, timeout)
        # SDK 자체 재시도는 끔 (재시도는 LlmClient 한 곳에서만), 타임아웃은 요청마다 지정
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key, max_retries=0)
        self._effort = effort
        self._fallback = fallback

    async def _request(self, request: LlmRequest[T]) -> ProviderResponse[T]:
        options = {"betas": [FALLBACK_BETA], "fallbacks": "default"} if self._fallback else {}
        try:
            response = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=request.max_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.user}],
                output_config={
                    "effort": self._effort,
                    "format": {
                        "type": "json_schema",
                        "schema": anthropic.transform_schema(request.output),
                    },
                },
                timeout=request.timeout,
                **options,
            )
        except anthropic.APIConnectionError as exc:
            code = "LLM_TIMEOUT" if isinstance(exc, anthropic.APITimeoutError) else "LLM_CONNECTION"
            raise LlmError(code, retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise status_error(exc.status_code) from exc

        tokens = {
            "model": response.model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        if response.stop_reason == "refusal":
            raise LlmError("LLM_REFUSED", retryable=False, **tokens)
        text = next((block.text for block in response.content if block.type == "text"), None)
        if response.stop_reason == "max_tokens" or text is None:
            raise LlmError("LLM_INVALID_OUTPUT", retryable=True, **tokens)
        return ProviderResponse(_validate(request, text, tokens), **tokens)


# ---------------------------------------------------------------------------
# 2. OpenAI·sLLM (OpenAI 호환 서버)
# ---------------------------------------------------------------------------

JsonMode = Literal["json_schema", "json_object"]
# sLLM 서버는 키를 요구하지 않는 경우가 많지만 SDK는 빈 키를 허용하지 않음
NO_KEY = "not-needed"


class OpenAICompatibleLlm(LlmClient):
    """base_url을 비우면 OpenAI, sLLM 서버 주소를 넣으면 그 서버.

    JSON 출력은 json_schema(스키마 강제, 기본) 또는 json_object(JSON 모드, 스키마 강제를
    지원하지 않는 sLLM 서버용).
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str | None,
        json_mode: JsonMode,
        timeout: float,
        max_retries: int,
        backoff_seconds: float,
        recorder: UsageRecorder,
        client: openai.AsyncOpenAI | None = None,
    ) -> None:
        super().__init__(model, max_retries, recorder, backoff_seconds, timeout)
        # SDK 자체 재시도는 끔 (재시도는 LlmClient 한 곳에서만), 타임아웃은 요청마다 지정
        self._client = client or openai.AsyncOpenAI(
            api_key=api_key or NO_KEY, base_url=base_url or None, max_retries=0
        )
        self._json_mode = json_mode

    async def _request(self, request: LlmRequest[T]) -> ProviderResponse[T]:
        system, response_format = self._output_format(request)
        try:
            completion = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": request.user},
                ],
                response_format=response_format,  # type: ignore[arg-type]
                max_completion_tokens=request.max_tokens,
                timeout=request.timeout,
            )
        except openai.APIConnectionError as exc:
            code = "LLM_TIMEOUT" if isinstance(exc, openai.APITimeoutError) else "LLM_CONNECTION"
            raise LlmError(code, retryable=True) from exc
        except openai.APIStatusError as exc:
            raise status_error(exc.status_code) from exc

        usage = completion.usage
        tokens: dict[str, Any] = {
            "model": completion.model or self.model,
            "input_tokens": usage.prompt_tokens if usage else None,
            "output_tokens": usage.completion_tokens if usage else None,
        }
        choice = completion.choices[0] if completion.choices else None
        if choice is None:
            raise LlmError("LLM_INVALID_OUTPUT", retryable=True, **tokens)
        if choice.message.refusal or choice.finish_reason == "content_filter":
            raise LlmError("LLM_REFUSED", retryable=False, **tokens)
        if choice.finish_reason == "length" or not choice.message.content:
            raise LlmError("LLM_INVALID_OUTPUT", retryable=True, **tokens)
        return ProviderResponse(_validate(request, choice.message.content, tokens), **tokens)

    def _output_format(self, request: LlmRequest[T]) -> tuple[str, dict[str, Any]]:
        schema = strict_schema(request.output)
        if self._json_mode == "json_object":
            # JSON 모드는 스키마를 강제하지 않으므로 지시문에 스키마를 넣음
            system = (
                f"{request.system}\n답은 아래 JSON 스키마를 따르는 JSON 객체 하나로만 한다.\n"
                f"{json.dumps(schema, ensure_ascii=False)}"
            )
            return system, {"type": "json_object"}
        return request.system, {
            "type": "json_schema",
            "json_schema": {"name": request.output.__name__, "schema": schema, "strict": True},
        }


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """pydantic 스키마 → OpenAI strict 형식.

    모든 객체의 필드를 필수로, 정의 밖 필드 금지, 기본값 제거.
    """
    schema = model.model_json_schema()
    _make_strict(schema)
    for definition in schema.get("$defs", {}).values():
        _make_strict(definition)
    return schema


def _make_strict(node: dict[str, Any]) -> None:
    node.pop("default", None)
    properties = node.get("properties")
    if properties is not None:
        node["additionalProperties"] = False
        node["required"] = list(properties)
        for child in properties.values():
            _make_strict(child)
    if isinstance(node.get("items"), dict):
        _make_strict(node["items"])
    for key in ("anyOf", "allOf", "oneOf"):
        for child in node.get(key, []):
            _make_strict(child)


def _validate(request: LlmRequest[T], text: str, tokens: dict[str, Any]) -> T:
    """제공자 공통: 받은 JSON을 요청한 출력 형식으로 검증. 실패는 재시도 대상."""
    try:
        return request.output.model_validate_json(text)
    except ValidationError as exc:
        raise LlmError("LLM_INVALID_OUTPUT", retryable=True, **tokens) from exc


# ---------------------------------------------------------------------------
# 3. 제공자 선택 (LLM_PROVIDER)
# ---------------------------------------------------------------------------


def create_llm(settings: Settings, recorder: UsageRecorder) -> LlmClient:
    """키·모델이 없으면 UnconfiguredLlm: 서버는 기동하고 판정·되묻기만 503 AI_UNAVAILABLE."""
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
    if settings.llm_provider == "openai":
        # OpenAI는 키 필수, sLLM 서버(base_url 지정)는 키 없이도 가능. 모델은 항상 필수
        base_url = settings.openai_base_url or None
        if not settings.openai_model or not (settings.openai_api_key or base_url):
            return UnconfiguredLlm(settings.openai_model or "openai", recorder)
        return OpenAICompatibleLlm(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=base_url,
            json_mode=settings.openai_json_mode,
            timeout=settings.llm_timeout,
            max_retries=settings.llm_max_retries,
            backoff_seconds=settings.llm_retry_backoff,
            recorder=recorder,
        )
    raise ValueError(f"지원하지 않는 LLM_PROVIDER: {settings.llm_provider}")


def get_llm(request: Request) -> LlmClient:
    """라우터 의존성: 기동 시 만든 app.state.llm. 테스트는 dependency_overrides로 교체."""
    return request.app.state.llm
