"""임베딩 제공자 시험 (#467). 실제 OpenAI를 부르지 않고 SDK 응답 모양만 흉내 낸다."""

import asyncio
from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest

from app.config import Settings
from app.knowledge.fake import FAKE_EMBEDDING_MODEL, fake_vector
from app.llm.base import LlmError, LlmUnavailable, LlmUsage
from app.llm.embeddings import (
    FakeEmbeddingClient,
    OpenAIEmbeddingClient,
    UnconfiguredEmbeddingClient,
    create_embedder,
)

REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/embeddings")
DIMS = 4


def response(vectors: list[list[float]], order: list[int] | None = None) -> SimpleNamespace:
    """order로 data 항목 순서를 섞어 보냄 (index는 원래 위치)."""
    indexes = order or list(range(len(vectors)))
    return SimpleNamespace(
        model="text-embedding-3-small",
        data=[SimpleNamespace(index=i, embedding=vectors[i]) for i in indexes],
        usage=SimpleNamespace(prompt_tokens=12, total_tokens=12),
    )


class FakeEmbeddings:
    def __init__(self, *results: Any) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make(*results: Any, max_retries: int = 0) -> tuple[OpenAIEmbeddingClient, FakeEmbeddings, list]:
    embeddings = FakeEmbeddings(*results)
    usages: list[LlmUsage] = []
    client = OpenAIEmbeddingClient(
        api_key="k",
        model="text-embedding-3-small",
        dimensions=DIMS,
        max_retries=max_retries,
        backoff_seconds=0,
        timeout=15,
        recorder=usages.append,
        client=SimpleNamespace(embeddings=embeddings),  # type: ignore[arg-type]
    )
    return client, embeddings, usages


def vec(n: float) -> list[float]:
    return [n] * DIMS


def status_error(status: int) -> openai.APIStatusError:
    return openai.APIStatusError(
        "error", response=httpx2.Response(status, request=REQUEST), body=None
    )


def test_keeps_request_order_and_records_usage() -> None:
    client, embeddings, usages = make(response([vec(0), vec(1), vec(2)], order=[2, 0, 1]))
    result = asyncio.run(client.embed(["a", "b", "c"]))
    assert result.vectors == [vec(0), vec(1), vec(2)]
    assert (result.model, result.dimensions) == ("text-embedding-3-small", DIMS)
    call = embeddings.calls[0]
    assert call["input"] == ["a", "b", "c"]
    assert (call["model"], call["dimensions"], call["timeout"]) == (
        "text-embedding-3-small",
        DIMS,
        15,
    )
    [usage] = usages
    assert usage.call_type == "KNOWLEDGE_EMBEDDING"
    assert (usage.input_tokens, usage.output_tokens, usage.prompt_version) == (12, 0, None)
    assert usage.success and usage.error_code is None


def test_memory_purpose_records_memory_embedding() -> None:
    client, _, usages = make(response([vec(0)]), status_error(500))
    asyncio.run(client.embed(["추억 문서"], "MEMORY"))
    with pytest.raises(LlmUnavailable):
        asyncio.run(client.embed(["추억 문서"], "MEMORY"))
    assert [(u.call_type, u.success) for u in usages] == [
        ("MEMORY_EMBEDDING", True),
        ("MEMORY_EMBEDDING", False),
    ]


@pytest.mark.parametrize(
    "bad",
    [response([vec(0)]), response([vec(0), [0.0] * (DIMS + 1)])],
    ids=["count", "dimensions"],
)
def test_count_or_dimension_mismatch_is_invalid_output_with_usage(bad: Any) -> None:
    client, _, usages = make(bad)
    with pytest.raises(LlmUnavailable) as exc:
        asyncio.run(client.embed(["a", "b"]))
    assert (exc.value.code, exc.value.retryable) == ("LLM_INVALID_OUTPUT", True)
    [usage] = usages
    assert not usage.success and usage.error_code == "LLM_INVALID_OUTPUT"
    assert usage.input_tokens == 12


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (openai.APITimeoutError(request=REQUEST), "LLM_TIMEOUT", True),
        (openai.APIConnectionError(request=REQUEST), "LLM_CONNECTION", True),
        (status_error(429), "LLM_RATE_LIMITED", True),
        (status_error(500), "LLM_SERVER_ERROR", True),
        (status_error(401), "LLM_AUTH_FAILED", False),
        (status_error(400), "LLM_BAD_REQUEST", False),
    ],
)
def test_sdk_errors_are_classified_and_recorded(
    error: Exception, code: str, retryable: bool
) -> None:
    client, _, usages = make(error)
    with pytest.raises(LlmUnavailable) as exc:
        asyncio.run(client.embed(["a"]))
    assert (exc.value.code, exc.value.retryable) == (code, retryable)
    assert [(u.success, u.error_code, u.call_type) for u in usages] == [
        (False, code, "KNOWLEDGE_EMBEDDING")
    ]


def test_retryable_failure_retries_once_and_records_each_request() -> None:
    client, embeddings, usages = make(status_error(503), response([vec(1)]), max_retries=1)
    result = asyncio.run(client.embed(["a"]))
    assert result.vectors == [vec(1)]
    assert len(embeddings.calls) == 2
    assert [u.success for u in usages] == [False, True]


def test_non_retryable_failure_does_not_retry() -> None:
    client, embeddings, _ = make(status_error(401), response([vec(1)]), max_retries=1)
    with pytest.raises(LlmUnavailable):
        asyncio.run(client.embed(["a"]))
    assert len(embeddings.calls) == 1


def test_fake_client_uses_contract_rule_without_usage() -> None:
    result = asyncio.run(FakeEmbeddingClient(8).embed(["분수의 덧셈", "분수의 덧셈"]))
    assert result.model == FAKE_EMBEDDING_MODEL
    assert result.vectors[0] == result.vectors[1] == fake_vector("분수의 덧셈", 8)


def test_unconfigured_client_fails_without_sending() -> None:
    with pytest.raises(LlmUnavailable) as exc:
        asyncio.run(UnconfiguredEmbeddingClient("m", 8).embed(["a"]))
    assert (exc.value.code, exc.value.retryable) == ("LLM_NOT_CONFIGURED", False)


def settings(**overrides: Any) -> Settings:
    return Settings(internal_token="t", **overrides)


def test_factory_defaults_and_shared_llm_policy() -> None:
    client = create_embedder(settings(openai_api_key="k", openai_base_url="http://sllm/v1"), print)
    assert isinstance(client, OpenAIEmbeddingClient)
    assert (client.model, client.dimensions) == ("text-embedding-3-small", 1536)
    assert (client._timeout, client._max_retries, client._backoff_seconds) == (15.0, 1, 1.0)
    # OPENAI_BASE_URL(sLLM 대화용)은 쓰지 않음
    assert str(client._client.base_url).startswith("https://api.openai.com/v1")
    assert client._client.max_retries == 0


def test_factory_without_key_is_unconfigured_and_fake_needs_no_key() -> None:
    assert isinstance(create_embedder(settings(), print), UnconfiguredEmbeddingClient)
    fake = create_embedder(settings(embedding_provider="fake"), print)
    assert isinstance(fake, FakeEmbeddingClient)


def test_llm_error_without_send_is_not_recorded() -> None:
    client, _, usages = make(LlmError("LLM_NOT_CONFIGURED", retryable=False, sent=False))
    with pytest.raises(LlmUnavailable):
        asyncio.run(client.embed(["a"]))
    assert usages == []
