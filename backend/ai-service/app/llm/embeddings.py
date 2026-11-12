"""임베딩 제공자 (#467, api-spec 4.2.4 계약 C6).

목차
  1. 공통           EmbeddingClient        재시도·사용량 기록 (base.LlmClient와 같은 방식)
  2. OpenAI         OpenAIEmbeddingClient  EMBEDDING_PROVIDER=openai
  3. 가짜·미설정    FakeEmbeddingClient·UnconfiguredEmbeddingClient
  4. 제공자 선택    create_embedder·get_embedder

타임아웃·재시도·대기는 LLM 공통 설정(P12)을 그대로 쓴다. 요청 1회 = 사용량 1건
(callType은 요청 purpose로 정함: KNOWLEDGE → KNOWLEDGE_EMBEDDING, MEMORY → MEMORY_EMBEDDING #565).
임베딩은 출력 토큰이 없어 outputTokens는 0으로 남긴다.
OPENAI_BASE_URL은 sLLM 대화용이라 쓰지 않고 항상 OpenAI 기본 주소로 보낸다.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import openai
from fastapi import Request

from app.config import Settings
from app.knowledge.contracts import EmbeddingPurpose
from app.knowledge.fake import FAKE_EMBEDDING_MODEL, fake_vector
from app.llm.base import LlmError, LlmUnavailable, LlmUsage, UsageRecorder, status_error
from app.llm.providers import OPENAI_DEFAULT_BASE_URL

CALL_TYPES: dict[EmbeddingPurpose, str] = {
    "KNOWLEDGE": "KNOWLEDGE_EMBEDDING",
    "MEMORY": "MEMORY_EMBEDDING",
}


@dataclass(frozen=True)
class Embeddings:
    """요청 texts와 같은 순서·같은 개수의 벡터."""

    model: str
    dimensions: int
    vectors: list[list[float]]


@dataclass(frozen=True)
class ProviderEmbeddings:
    """제공자 요청 1회의 결과 (모델은 제공자가 응답한 이름)."""

    model: str
    vectors: list[list[float]]
    input_tokens: int | None


# ---------------------------------------------------------------------------
# 1. 공통
# ---------------------------------------------------------------------------


class EmbeddingClient(ABC):
    def __init__(
        self,
        *,
        model: str,
        dimensions: int,
        max_retries: int,
        backoff_seconds: float,
        timeout: float,
        recorder: UsageRecorder | None,
    ) -> None:
        self._model = model
        self._dimensions = dimensions
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._timeout = timeout
        self._recorder = recorder

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str], purpose: EmbeddingPurpose = "KNOWLEDGE") -> Embeddings:
        """재시도까지 실패하면 LlmUnavailable. 개수·차원이 다르면 LLM_INVALID_OUTPUT."""
        call_type = CALL_TYPES[purpose]
        for attempt in range(self._max_retries + 1):
            started = time.monotonic()
            try:
                response = await self._request(texts, self._timeout)
                if len(response.vectors) != len(texts) or any(
                    len(vector) != self._dimensions for vector in response.vectors
                ):
                    raise LlmError(
                        "LLM_INVALID_OUTPUT",
                        retryable=True,
                        model=response.model,
                        input_tokens=response.input_tokens,
                    )
            except LlmError as exc:
                if exc.sent:
                    self._record(call_type, started, exc.model, exc.input_tokens, exc.code)
                if not exc.retryable or attempt == self._max_retries:
                    raise LlmUnavailable(exc.code, exc.retryable) from exc
            else:
                self._record(call_type, started, response.model, response.input_tokens, None)
                return Embeddings(response.model, self._dimensions, response.vectors)
            await asyncio.sleep(self._backoff_seconds * 2**attempt)
        raise AssertionError("unreachable")

    @abstractmethod
    async def _request(self, texts: list[str], timeout: float) -> ProviderEmbeddings:
        """요청 1회. 실패는 LlmError로 변환해 던짐."""

    def _record(
        self,
        call_type: str,
        started: float,
        model: str | None,
        input_tokens: int | None,
        error: str | None,
    ) -> None:
        if self._recorder is None:
            return
        self._recorder(
            LlmUsage(
                call_type=call_type,
                model=model or self._model,
                prompt_version=None,
                input_tokens=input_tokens,
                output_tokens=0 if input_tokens is not None else None,
                latency_ms=int((time.monotonic() - started) * 1000),
                success=error is None,
                error_code=error,
            )
        )


# ---------------------------------------------------------------------------
# 2. OpenAI
# ---------------------------------------------------------------------------


class OpenAIEmbeddingClient(EmbeddingClient):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        max_retries: int,
        backoff_seconds: float,
        timeout: float,
        recorder: UsageRecorder,
        client: openai.AsyncOpenAI | None = None,
    ) -> None:
        super().__init__(
            model=model,
            dimensions=dimensions,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            timeout=timeout,
            recorder=recorder,
        )
        # SDK 자체 재시도는 끔 (재시도는 EmbeddingClient 한 곳에서만)
        self._client = client or openai.AsyncOpenAI(
            api_key=api_key, base_url=OPENAI_DEFAULT_BASE_URL, max_retries=0
        )

    async def _request(self, texts: list[str], timeout: float) -> ProviderEmbeddings:
        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=texts,
                dimensions=self._dimensions,
                encoding_format="float",
                timeout=timeout,
            )
        except openai.APIConnectionError as exc:
            code = "LLM_TIMEOUT" if isinstance(exc, openai.APITimeoutError) else "LLM_CONNECTION"
            raise LlmError(code, retryable=True) from exc
        except openai.APIStatusError as exc:
            raise status_error(exc.status_code) from exc
        # 응답 순서는 index 기준 (요청 texts와 같은 순서로 맞춤)
        items = sorted(response.data, key=lambda item: item.index)
        return ProviderEmbeddings(
            model=response.model or self._model,
            vectors=[list(item.embedding) for item in items],
            input_tokens=response.usage.prompt_tokens if response.usage else None,
        )


# ---------------------------------------------------------------------------
# 3. 가짜·미설정
# ---------------------------------------------------------------------------


class FakeEmbeddingClient(EmbeddingClient):
    """개발용 (api-spec 4.2.4 가짜 규칙 fake-bigram-v1). 외부 호출이 없어 사용량을 남기지 않음."""

    def __init__(self, dimensions: int) -> None:
        super().__init__(
            model=FAKE_EMBEDDING_MODEL,
            dimensions=dimensions,
            max_retries=0,
            backoff_seconds=0,
            timeout=1,
            recorder=None,
        )

    async def _request(self, texts: list[str], timeout: float) -> ProviderEmbeddings:
        vectors = [fake_vector(text, self._dimensions) for text in texts]
        return ProviderEmbeddings(self._model, vectors, None)


class UnconfiguredEmbeddingClient(EmbeddingClient):
    """OpenAI 키 미설정. 서버는 기동하고 임베딩만 503 (재시도 무의미, 사용량 없음)."""

    def __init__(self, model: str, dimensions: int) -> None:
        super().__init__(
            model=model,
            dimensions=dimensions,
            max_retries=0,
            backoff_seconds=0,
            timeout=1,
            recorder=None,
        )

    async def _request(self, texts: list[str], timeout: float) -> ProviderEmbeddings:
        raise LlmError("LLM_NOT_CONFIGURED", retryable=False, sent=False)


# ---------------------------------------------------------------------------
# 4. 제공자 선택 (EMBEDDING_PROVIDER)
# ---------------------------------------------------------------------------


def create_embedder(settings: Settings, recorder: UsageRecorder) -> EmbeddingClient:
    if settings.embedding_provider == "fake":
        return FakeEmbeddingClient(settings.embedding_dimensions)
    if not settings.openai_api_key:
        return UnconfiguredEmbeddingClient(settings.embedding_model, settings.embedding_dimensions)
    return OpenAIEmbeddingClient(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        max_retries=settings.llm_max_retries,
        backoff_seconds=settings.llm_retry_backoff,
        timeout=settings.llm_timeout,
        recorder=recorder,
    )


def get_embedder(request: Request) -> EmbeddingClient:
    """라우터 의존성: 기동 시 만든 app.state.embedder. 테스트는 dependency_overrides로 교체."""
    return request.app.state.embedder
