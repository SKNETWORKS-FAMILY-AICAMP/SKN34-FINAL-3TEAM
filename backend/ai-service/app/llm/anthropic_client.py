"""Claude 제공자. 요청 1회만 담당하고 재시도는 LlmClient가 수행.

구조화 출력은 output_config.format(JSON 스키마)으로 강제하고, 검증은 직접 수행해
형식이 깨진 응답도 토큰 사용량을 남김.
"""

import anthropic
from pydantic import ValidationError

from app.llm.base import LlmClient, LlmError, LlmRequest, ProviderResponse, T, UsageRecorder

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
        recorder: UsageRecorder,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        super().__init__(model, max_retries, recorder)
        # SDK 자체 재시도는 끔 (재시도는 LlmClient 한 곳에서만)
        self._client = client or anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout, max_retries=0
        )
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
                **options,
            )
        except anthropic.APIConnectionError as exc:
            code = "LLM_TIMEOUT" if isinstance(exc, anthropic.APITimeoutError) else "LLM_CONNECTION"
            raise LlmError(code, retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise _status_error(exc.status_code) from exc

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
        try:
            data = request.output.model_validate_json(text)
        except ValidationError as exc:
            raise LlmError("LLM_INVALID_OUTPUT", retryable=True, **tokens) from exc
        return ProviderResponse(data, **tokens)


def _status_error(status: int) -> LlmError:
    if status == 429:
        return LlmError("LLM_RATE_LIMITED", retryable=True)
    if status in (408, 409) or status >= 500:
        return LlmError("LLM_SERVER_ERROR", retryable=True)
    if status in (401, 403):
        return LlmError("LLM_AUTH_FAILED", retryable=False)
    return LlmError("LLM_BAD_REQUEST", retryable=False)
