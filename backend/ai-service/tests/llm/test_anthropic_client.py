import asyncio
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import BaseModel

from app.config import Settings
from app.llm.anthropic_client import FALLBACK_BETA, AnthropicLlm
from app.llm.base import LlmError, LlmRequest, LlmUsage, UnconfiguredLlm
from app.llm.factory import create_llm

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


class Answer(BaseModel):
    value: str


class FakeMessages:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def message(text: str | None, stop_reason: str = "end_turn") -> SimpleNamespace:
    content = [SimpleNamespace(type="thinking", thinking="")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        model="claude-sonnet-5-5",
        stop_reason=stop_reason,
        content=content,
        usage=SimpleNamespace(input_tokens=120, output_tokens=30),
    )


def make_llm(result: Any, fallback: bool = True) -> tuple[AnthropicLlm, FakeMessages]:
    messages = FakeMessages(result)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    llm = AnthropicLlm(
        api_key="k",
        model="claude-sonnet-5-5",
        effort="medium",
        fallback=fallback,
        timeout=30,
        max_retries=0,
        backoff_seconds=0,
        recorder=lambda _: None,
        client=client,  # type: ignore[arg-type]
    )
    return llm, messages


def request_once(llm: AnthropicLlm):
    request = LlmRequest("system", "user", Answer, "JUDGMENT", "judge@1", 1024, 7.5)
    return asyncio.run(llm._request(request))


def test_parses_structured_output_with_usage() -> None:
    llm, messages = make_llm(message('{"value": "ok"}'))
    response = request_once(llm)
    assert response.data == Answer(value="ok")
    assert (response.model, response.input_tokens, response.output_tokens) == (
        "claude-sonnet-5-5",
        120,
        30,
    )
    assert messages.kwargs["output_config"]["effort"] == "medium"
    assert messages.kwargs["output_config"]["format"]["type"] == "json_schema"
    assert messages.kwargs["betas"] == [FALLBACK_BETA]
    assert messages.kwargs["fallbacks"] == "default"
    assert messages.kwargs["timeout"] == 7.5  # 요청마다 지정한 타임아웃


def test_fallback_disabled_sends_no_beta() -> None:
    llm, messages = make_llm(message('{"value": "ok"}'), fallback=False)
    request_once(llm)
    assert "betas" not in messages.kwargs
    assert "fallbacks" not in messages.kwargs


@pytest.mark.parametrize(
    ("result", "code", "retryable"),
    [
        (message('{"wrong": 1}'), "LLM_INVALID_OUTPUT", True),
        (message('{"value": "cut'), "LLM_INVALID_OUTPUT", True),
        (message('{"value": "o', stop_reason="max_tokens"), "LLM_INVALID_OUTPUT", True),
        (message(None, stop_reason="refusal"), "LLM_REFUSED", False),
    ],
)
def test_bad_responses_keep_token_usage(result: Any, code: str, retryable: bool) -> None:
    llm, _ = make_llm(result)
    with pytest.raises(LlmError) as exc:
        request_once(llm)
    assert (exc.value.code, exc.value.retryable) == (code, retryable)
    assert (exc.value.input_tokens, exc.value.output_tokens) == (120, 30)


def status_error(status: int) -> anthropic.APIStatusError:
    return anthropic.APIStatusError(
        "error", response=httpx2.Response(status, request=REQUEST), body=None
    )


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (anthropic.APITimeoutError(request=REQUEST), "LLM_TIMEOUT", True),
        (anthropic.APIConnectionError(request=REQUEST), "LLM_CONNECTION", True),
        (status_error(429), "LLM_RATE_LIMITED", True),
        (status_error(529), "LLM_SERVER_ERROR", True),
        (status_error(401), "LLM_AUTH_FAILED", False),
        (status_error(400), "LLM_BAD_REQUEST", False),
    ],
)
def test_sdk_errors_are_classified(error: Exception, code: str, retryable: bool) -> None:
    llm, _ = make_llm(error)
    with pytest.raises(LlmError) as exc:
        request_once(llm)
    assert (exc.value.code, exc.value.retryable) == (code, retryable)


def recorder(_: LlmUsage) -> None:
    pass


def test_factory_without_key_returns_unconfigured() -> None:
    llm = create_llm(Settings(internal_token="t", anthropic_api_key=None), recorder)
    assert isinstance(llm, UnconfiguredLlm)
    assert llm.model == "claude-sonnet-5-5"


def test_factory_disables_sdk_retries_and_uses_configured_backoff() -> None:
    settings = Settings(internal_token="t", anthropic_api_key="k", llm_retry_backoff=1.5)
    llm = create_llm(settings, recorder)
    assert isinstance(llm, AnthropicLlm)
    assert llm._client.max_retries == 0
    assert llm._backoff_seconds == 1.5
    assert llm._timeout == 15.0  # LLM 1회 15초 (P12)


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        create_llm(Settings(internal_token="t", llm_provider="unknown"), recorder)
