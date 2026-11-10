"""LLM 공통 인터페이스 (아키텍처 2.1 제공자 교체 지점).

판정·되묻기는 LlmClient.generate만, 분석 대화 답변은 stream도 사용하고 어떤 제공자인지 모름.
재시도는 여기에서만 수행 (아키텍처 1.3), 제공자 구현은 요청 1회만 담당.
요청마다 사용량을 recorder로 넘김 (재시도 포함 요청 1회 = 1건, NFR-PRF-02).
"""

import asyncio
import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from langfuse import Langfuse
from pydantic import BaseModel

from app.security import current_user_context

logger = logging.getLogger(__name__)
TRACEPARENT = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}")

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
    # user 글 뒤에 붙이는 그림(PNG·JPEG·WebP 바이트). 테마 그림 검토·화자 위치(#437)만 씀
    images: tuple[bytes, ...] = ()


@dataclass(frozen=True)
class ProviderResponse(Generic[T]):
    """제공자 요청 1회의 결과."""

    data: T
    model: str
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True)
class StreamEnd:
    """제공자 스트림 1회의 마지막 항목. 텍스트 조각 뒤에 한 번 보냄."""

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
        self.langfuse: Langfuse | None = None

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
        timeout: float | None = None,
        max_retries: int | None = None,
        images: Sequence[bytes] | None = None,
    ) -> LlmResult[T]:
        """deadline(time.monotonic 기준 시각)이 있으면 그 안에서만 요청·재시도.

        남은 시간이 없으면 요청하지 않고 LLM_DEADLINE_EXCEEDED로 실패 (사용량 기록 없음).
        timeout·max_retries를 주면 이 호출만 기본값(P12 15초·1회) 대신 씀 (미션 초안 #353)
        images를 주면 user 글 뒤에 그림을 함께 보냄(테마 그림 검토·화자 위치 #437)
        """
        retries = self._max_retries if max_retries is None else max_retries
        for attempt in range(retries + 1):
            timeout_this = self._timeout if timeout is None else timeout
            if deadline is not None:
                timeout_this = min(timeout_this, deadline - time.monotonic())
                if timeout_this <= 0:
                    raise LlmUnavailable("LLM_DEADLINE_EXCEEDED", retryable=True)
            request = LlmRequest(
                system,
                user,
                output,
                call_type,
                prompt_version,
                max_tokens,
                timeout_this,
                tuple(images or ()),
            )
            started = time.monotonic()
            observation = self._start_observation(request)
            retry = False
            try:
                try:
                    response = await self._request(request)
                except LlmError as exc:
                    if exc.sent:
                        self._record(
                            request,
                            started,
                            exc.model,
                            exc.input_tokens,
                            exc.output_tokens,
                            exc,
                            observation=observation,
                        )
                    if not exc.retryable or attempt == retries:
                        raise LlmUnavailable(exc.code, exc.retryable) from exc
                    retry = True
                else:
                    self._record(
                        request,
                        started,
                        response.model,
                        response.input_tokens,
                        response.output_tokens,
                        observation=observation,
                    )
                    return LlmResult(response.data, response.model)
            finally:
                self._end_observation(observation)
            if retry:
                await asyncio.sleep(self._backoff_seconds * 2**attempt)
        raise AssertionError("unreachable")

    def stream(
        self,
        *,
        system: str,
        user: str,
        call_type: str,
        prompt_version: str,
        max_tokens: int = 4096,
        deadline: float | None = None,
    ) -> "LlmTextStream":
        """일반 텍스트를 조각으로 받음. 재시도는 첫 조각 전 실패만 (첫 조각 뒤 실패는 바로 실패)."""
        return LlmTextStream(self, system, user, call_type, prompt_version, max_tokens, deadline)

    @abstractmethod
    async def _request(self, request: LlmRequest[T]) -> ProviderResponse[T]:
        """요청 1회. 실패는 LlmError로 변환해 던짐."""

    def _stream(self, request: LlmRequest[Any]) -> AsyncIterator[str | StreamEnd]:
        """스트림 요청 1회: 텍스트 조각들 → StreamEnd. 실패는 LlmError로 변환해 던짐."""
        raise NotImplementedError

    def _start_observation(self, request: LlmRequest[Any]) -> Any:
        """원문 없이 제공자 요청 1회의 generation만 만든다."""
        if self.langfuse is None:
            return None
        context = current_user_context()
        trace_context = None
        if context and context.traceparent:
            match = TRACEPARENT.fullmatch(context.traceparent.lower())
            if match and int(match.group(1), 16) and int(match.group(2), 16):
                trace_context = {"trace_id": match.group(1), "parent_span_id": match.group(2)}
        try:
            return self.langfuse.start_observation(
                name=f"llm.{request.call_type.lower()}",
                as_type="generation",
                trace_context=trace_context,
                model=self._model,
                metadata={"callType": request.call_type, "promptVersion": request.prompt_version},
            )
        except Exception:  # noqa: BLE001 - 관측 장애가 LLM 호출을 막지 않음
            logger.warning("Langfuse observation 시작 실패: call_type=%s", request.call_type)
            return None

    def _end_observation(self, observation: Any) -> None:
        if observation is None:
            return
        try:
            observation.end()
        except Exception:  # noqa: BLE001 - 관측 장애가 LLM 결과를 바꾸지 않음
            logger.warning("Langfuse observation 종료 실패")

    def _record(
        self,
        request: LlmRequest[T],
        started: float,
        model: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        error: LlmError | None = None,
        *,
        observation: Any = None,
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
        if observation is not None:
            try:
                details = {}
                if input_tokens is not None:
                    details["input"] = input_tokens
                if output_tokens is not None:
                    details["output"] = output_tokens
                observation.update(
                    model=usage.model,
                    usage_details=details or None,
                    level="ERROR" if error else "DEFAULT",
                    status_message=error.code if error else None,
                )
            except Exception:  # noqa: BLE001 - 관측 장애가 사용량 이벤트를 막지 않음
                logger.warning("Langfuse observation 갱신 실패: call_type=%s", request.call_type)
        try:
            self._recorder(usage)
        except Exception:  # noqa: BLE001 - 사용량 기록 실패가 응답을 막지 않음 (best-effort)
            logger.warning("LLM 사용량 기록 실패: call_type=%s", request.call_type, exc_info=True)


class LlmTextStream:
    """LlmClient.stream 결과. async for로 조각을 받고, 끝나면 model에 응답한 모델 ID."""

    def __init__(
        self,
        llm: LlmClient,
        system: str,
        user: str,
        call_type: str,
        prompt_version: str,
        max_tokens: int,
        deadline: float | None,
    ) -> None:
        self._llm = llm
        self._args = (system, user, call_type, prompt_version, max_tokens)
        self._deadline = deadline
        self.model: str | None = None

    async def __aiter__(self) -> AsyncIterator[str]:
        llm = self._llm
        system, user, call_type, prompt_version, max_tokens = self._args
        for attempt in range(llm._max_retries + 1):
            timeout = llm._timeout
            if self._deadline is not None:
                timeout = min(timeout, self._deadline - time.monotonic())
                if timeout <= 0:
                    raise LlmUnavailable("LLM_DEADLINE_EXCEEDED", retryable=True)
            request = LlmRequest(
                system, user, BaseModel, call_type, prompt_version, max_tokens, timeout
            )
            started = time.monotonic()
            observation = llm._start_observation(request)
            sent = False  # 조각을 하나라도 넘겼으면 재시도하지 않음 (받은 쪽이 이미 표시)
            retry = False
            try:
                async for item in _within(llm._stream(request), started + timeout):
                    if isinstance(item, StreamEnd):
                        llm._record(
                            request,
                            started,
                            item.model,
                            item.input_tokens,
                            item.output_tokens,
                            observation=observation,
                        )
                        self.model = item.model
                        return
                    sent = True
                    yield item
                raise LlmError("LLM_INVALID_OUTPUT", retryable=True)  # StreamEnd 없이 끝남
            except LlmError as exc:
                if exc.sent:
                    llm._record(
                        request,
                        started,
                        exc.model,
                        exc.input_tokens,
                        exc.output_tokens,
                        exc,
                        observation=observation,
                    )
                if sent or not exc.retryable or attempt == llm._max_retries:
                    raise LlmUnavailable(exc.code, exc.retryable) from exc
                retry = True
            finally:
                llm._end_observation(observation)
            if retry:
                await asyncio.sleep(llm._backoff_seconds * 2**attempt)
        raise AssertionError("unreachable")


async def _within[I](items: AsyncIterator[I], until: float) -> AsyncIterator[I]:
    """요청 1회 타임아웃: until(time.monotonic 기준)까지 다음 조각이 오지 않으면 LLM_TIMEOUT."""
    iterator = aiter(items)
    try:
        while True:
            try:
                item = await asyncio.wait_for(anext(iterator), until - time.monotonic())
            except StopAsyncIteration:
                return
            except TimeoutError as exc:
                raise LlmError("LLM_TIMEOUT", retryable=True) from exc
            yield item
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()


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
        # 요청을 보내지 않으므로 타임아웃은 의미 없음 (0이면 스트림이 시작 전에 시간 초과)
        super().__init__(model, max_retries=0, recorder=recorder, backoff_seconds=0, timeout=1)

    async def _request(self, request: LlmRequest[T]) -> ProviderResponse[T]:
        raise LlmError("LLM_NOT_CONFIGURED", retryable=False, sent=False)

    async def _stream(self, request: LlmRequest[Any]) -> AsyncIterator[str | StreamEnd]:
        raise LlmError("LLM_NOT_CONFIGURED", retryable=False, sent=False)
        yield ""  # 비동기 생성기로 만들기 위한 줄 (실행되지 않음)
