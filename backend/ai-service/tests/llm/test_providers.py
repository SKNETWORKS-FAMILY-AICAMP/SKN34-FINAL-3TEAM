import asyncio
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import openai
import pytest
from pydantic import BaseModel

from app.config import Settings
from app.llm.base import LlmError, LlmRequest, LlmUsage, UnconfiguredLlm
from app.llm.providers import (
    FALLBACK_BETA,
    NO_KEY,
    AnthropicLlm,
    OpenAICompatibleLlm,
    create_llm,
    strict_schema,
)

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


# --- OpenAI·sLLM -------------------------------------------------------------

OPENAI_REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")


class FakeCompletions:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def completion(
    content: str | None, finish_reason: str = "stop", refusal: str | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        model="gpt-test",
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content, refusal=refusal),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=90, completion_tokens=12),
    )


def make_openai(
    result: Any, json_mode: str = "json_schema"
) -> tuple[OpenAICompatibleLlm, FakeCompletions]:
    completions = FakeCompletions(result)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    llm = OpenAICompatibleLlm(
        api_key="k",
        model="gpt-test",
        base_url=None,
        json_mode=json_mode,  # type: ignore[arg-type]
        timeout=15,
        max_retries=0,
        backoff_seconds=0,
        recorder=recorder,
        client=client,  # type: ignore[arg-type]
    )
    return llm, completions


def openai_once(llm: OpenAICompatibleLlm):
    request = LlmRequest("system", "user", Answer, "FOLLOWUP", "followup@4", 1024, 7.5)
    return asyncio.run(llm._request(request))


def test_openai_parses_structured_output_with_usage() -> None:
    llm, completions = make_openai(completion('{"value": "ok"}'))
    response = openai_once(llm)
    assert response.data == Answer(value="ok")
    assert (response.model, response.input_tokens, response.output_tokens) == ("gpt-test", 90, 12)
    response_format = completions.kwargs["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert completions.kwargs["timeout"] == 7.5
    assert completions.kwargs["max_completion_tokens"] == 1024
    assert completions.kwargs["messages"][0] == {"role": "system", "content": "system"}


def test_openai_json_object_mode_puts_schema_in_system() -> None:
    # 스키마 강제를 지원하지 않는 sLLM 서버용
    llm, completions = make_openai(completion('{"value": "ok"}'), json_mode="json_object")
    openai_once(llm)
    assert completions.kwargs["response_format"] == {"type": "json_object"}
    assert '"value"' in completions.kwargs["messages"][0]["content"]


@pytest.mark.parametrize(
    ("result", "code", "retryable"),
    [
        (completion('{"wrong": 1}'), "LLM_INVALID_OUTPUT", True),
        (completion('{"value": "o', finish_reason="length"), "LLM_INVALID_OUTPUT", True),
        (completion(None), "LLM_INVALID_OUTPUT", True),
        (completion(None, refusal="거절"), "LLM_REFUSED", False),
        (completion(None, finish_reason="content_filter"), "LLM_REFUSED", False),
    ],
)
def test_openai_bad_responses_keep_token_usage(result: Any, code: str, retryable: bool) -> None:
    llm, _ = make_openai(result)
    with pytest.raises(LlmError) as exc:
        openai_once(llm)
    assert (exc.value.code, exc.value.retryable) == (code, retryable)
    assert (exc.value.input_tokens, exc.value.output_tokens) == (90, 12)


def openai_status_error(status: int) -> openai.APIStatusError:
    return openai.APIStatusError(
        "error", response=httpx2.Response(status, request=OPENAI_REQUEST), body=None
    )


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (openai.APITimeoutError(request=OPENAI_REQUEST), "LLM_TIMEOUT", True),
        (openai.APIConnectionError(request=OPENAI_REQUEST), "LLM_CONNECTION", True),
        (openai_status_error(429), "LLM_RATE_LIMITED", True),
        (openai_status_error(500), "LLM_SERVER_ERROR", True),
        (openai_status_error(401), "LLM_AUTH_FAILED", False),
        (openai_status_error(400), "LLM_BAD_REQUEST", False),
    ],
)
def test_openai_sdk_errors_are_classified(error: Exception, code: str, retryable: bool) -> None:
    llm, _ = make_openai(error)
    with pytest.raises(LlmError) as exc:
        openai_once(llm)
    assert (exc.value.code, exc.value.retryable) == (code, retryable)


def test_strict_schema_requires_every_field_and_forbids_extra() -> None:
    from app.judgment.extractor import Extraction

    schema = strict_schema(Extraction)
    assert schema["required"] == ["elements"]  # 기본값 있는 필드도 필수로
    assert schema["additionalProperties"] is False
    evidence = schema["$defs"]["ElementEvidence"]
    assert evidence["additionalProperties"] is False
    assert set(evidence["required"]) == {"elementId", "status", "quote"}
    assert "default" not in schema["properties"]["elements"]


def openai_settings(**overrides: Any) -> Settings:
    return Settings(internal_token="t", llm_provider="openai", **overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {},  # 키 없음 (모델은 기본값 gpt-6-luna)
        {"openai_api_key": "k", "openai_model": ""},  # 모델 비움
        {"openai_model": "gpt-test"},  # OpenAI인데 키 없음
        {"openai_model": "gpt-test", "openai_base_url": ""},  # compose의 빈 주소
    ],
)
def test_openai_without_key_or_model_is_unconfigured(overrides: dict[str, Any]) -> None:
    # 키 없이도 서버는 기동하고 판정·되묻기만 503 AI_UNAVAILABLE
    assert isinstance(create_llm(openai_settings(**overrides), recorder), UnconfiguredLlm)


def test_openai_factory_uses_shared_policy() -> None:
    llm = create_llm(openai_settings(openai_api_key="k", openai_model="gpt-test"), recorder)
    assert isinstance(llm, OpenAICompatibleLlm)
    assert (llm.model, llm._client.max_retries, llm._timeout, llm._max_retries) == (
        "gpt-test",
        0,  # SDK 재시도 끔
        15.0,  # LLM 1회 15초 (P12)
        1,  # 재시도 1회 (P12)
    )


def test_sllm_server_works_without_key() -> None:
    settings = openai_settings(openai_model="qwen", openai_base_url="http://vllm:8000/v1")
    llm = create_llm(settings, recorder)
    assert isinstance(llm, OpenAICompatibleLlm)
    assert str(llm._client.base_url).startswith("http://vllm:8000/v1")
    assert llm._client.api_key == NO_KEY


def test_openai_default_model_is_gpt_6_luna() -> None:
    llm = create_llm(openai_settings(openai_api_key="k"), recorder)
    assert isinstance(llm, OpenAICompatibleLlm)
    assert llm.model == "gpt-6-luna"
