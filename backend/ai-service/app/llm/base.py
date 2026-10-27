"""LLM 공통 인터페이스 (아키텍처 2.1 제공자 교체 지점).

판정·되묻기는 LlmClient.generate만 사용하고 어떤 제공자인지 모름.
재시도는 여기에서만 수행 (아키텍처 1.3), 제공자 구현은 요청 1회만 담당.
요청마다 사용량을 recorder로 넘김 (재시도 포함 요청 1회 = 1건, NFR-PRF-02).
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class LlmRequest(Generic[T]):
    system: str
    user: str
    output: type[T]
    call_type: str
    prompt_version: str
    max_tokens: int
    timeout: float  # 이번 요청 1회의 타임아웃(초). 마감이 있으면 남은 시간으로 줄어듦


@dataclass(frozen=True)
class ProviderResponse(Generic[T]):
    """제공자 요청 1회의 결과."""

    data: T
    model: str
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True)
class LlmResult(Generic[T]):
    data: T
    model: str


@dataclass(frozen=True)
class LlmUsage:
    """llm.usage.recorded 이벤트 data (contracts/events/llm.usage.recorded.v1.schema.json)."""

    call_type: str
    model: str
    prompt_version: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    success: bool
    error_code: str | None


UsageRecorder = Callable[[LlmUsage], None]


class LlmError(Exception):
    """제공자 요청 1회 실패. retryable이면 LlmClient가 재시도.

    sent=False는 LLM에 요청을 보내지 않은 실패(키 미설정 등)라 사용량을 기록하지 않음.
    """

    def __init__(
        self,
        code: str,
        retryable: bool,
        *,
        model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        sent: bool = True,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.sent = sent


class LlmUnavailable(Exception):
    """재시도까지 실패. 서비스가 503 AI_UNAVAILABLE로 변환 (판정 보류와 구분)."""

    def __init__(self, code: str, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class LlmClient(ABC):
    def __init__(
        self,
        model: str,
        max_retries: int,
        recorder: UsageRecorder,
        backoff_seconds: float,
        timeout: float,
    ) -> None:
        self._model = model
        self._max_retries = max_retries
        self._recorder = recorder
        self._backoff_seconds = backoff_seconds
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        *,
        system: str,
        user: str,
        output: type[T],
        call_type: str,
        prompt_version: str,
        max_tokens: int = 4096,
        deadline: float | None = None,
    ) -> LlmResult[T]:
        """deadline(time.monotonic 기준 시각)이 있으면 그 안에서만 요청·재시도.

        남은 시간이 없으면 요청하지 않고 LLM_DEADLINE_EXCEEDED로 실패 (사용량 기록 없음).
        """
        for attempt in range(self._max_retries + 1):
            timeout = self._timeout
            if deadline is not None:
                timeout = min(timeout, deadline - time.monotonic())
                if timeout <= 0:
                    raise LlmUnavailable("LLM_DEADLINE_EXCEEDED", retryable=True)
            request = LlmRequest(
                system, user, output, call_type, prompt_version, max_tokens, timeout
            )
            started = time.monotonic()
            try:
                response = await self._request(request)
            except LlmError as exc:
                if exc.sent:
                    self._record(
                        request, started, exc.model, exc.input_tokens, exc.output_tokens, exc
                    )
                if not exc.retryable or attempt == self._max_retries:
                    raise LlmUnavailable(exc.code, exc.retryable) from exc
                await asyncio.sleep(self._backoff_seconds * 2**attempt)
                continue
            self._record(
                request, started, response.model, response.input_tokens, response.output_tokens
            )
            return LlmResult(response.data, response.model)
        raise AssertionError("unreachable")

    @abstractmethod
    async def _request(self, request: LlmRequest[T]) -> ProviderResponse[T]:
        """요청 1회. 실패는 LlmError로 변환해 던짐."""

    def _record(
        self,
        request: LlmRequest[T],
        started: float,
        model: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        error: LlmError | None = None,
    ) -> None:
        usage = LlmUsage(
            call_type=request.call_type,
            model=model or self._model,
            prompt_version=request.prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=int((time.monotonic() - started) * 1000),
            success=error is None,
            error_code=error.code if error else None,
        )
        try:
            self._recorder(usage)
        except Exception:  # noqa: BLE001 - 사용량 기록 실패가 응답을 막지 않음 (best-effort)
            logger.warning("LLM 사용량 기록 실패: call_type=%s", request.call_type, exc_info=True)


def status_error(status: int) -> LlmError:
    """제공자 HTTP 상태 코드 → 공통 오류 코드 (제공자 공통)."""
    if status == 429:
        return LlmError("LLM_RATE_LIMITED", retryable=True)
    if status in (408, 409) or status >= 500:
        return LlmError("LLM_SERVER_ERROR", retryable=True)
    if status in (401, 403):
        return LlmError("LLM_AUTH_FAILED", retryable=False)
    return LlmError("LLM_BAD_REQUEST", retryable=False)


class UnconfiguredLlm(LlmClient):
    """API 키·모델 미설정. 서버는 기동하고 호출 시 503 (재시도 무의미)."""

    def __init__(self, model: str, recorder: UsageRecorder) -> None:
        super().__init__(model, max_retries=0, recorder=recorder, backoff_seconds=0, timeout=0)

    async def _request(self, request: LlmRequest[T]) -> ProviderResponse[T]:
        raise LlmError("LLM_NOT_CONFIGURED", retryable=False, sent=False)
