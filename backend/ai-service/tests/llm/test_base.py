import asyncio
import time
from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from app.llm.base import (
    LlmClient,
    LlmError,
    LlmRequest,
    LlmUnavailable,
    LlmUsage,
    ProviderResponse,
    StreamEnd,
    T,
    UnconfiguredLlm,
)


class Answer(BaseModel):
    value: str


class ScriptedLlm(LlmClient):
    """정해 둔 순서대로 응답하거나 실패하는 가짜 제공자."""

    def __init__(self, steps: list[LlmError | Answer], max_retries: int = 2) -> None:
        self.usages: list[LlmUsage] = []
        super().__init__(
            "fake-model", max_retries, self.usages.append, backoff_seconds=0, timeout=15
        )
        self._steps = steps
        self.calls = 0

    async def _request(self, request: LlmRequest[T]) -> ProviderResponse[T]:
        step = self._steps[self.calls]
        self.calls += 1
        if isinstance(step, LlmError):
            raise step
        return ProviderResponse(step, "fake-model", 10, 5)


def generate(llm: LlmClient):
    return asyncio.run(
        llm.generate(
            system="s", user="u", output=Answer, call_type="JUDGMENT", prompt_version="judge@1"
        )
    )


def test_success_records_one_usage() -> None:
    llm = ScriptedLlm([Answer(value="ok")])
    result = generate(llm)
    assert result.data.value == "ok"
    assert llm.usages == [
        LlmUsage("JUDGMENT", "fake-model", "judge@1", 10, 5, llm.usages[0].latency_ms, True, None)
    ]


def test_retryable_error_is_retried_and_each_attempt_recorded() -> None:
    llm = ScriptedLlm([LlmError("LLM_TIMEOUT", retryable=True), Answer(value="ok")])
    assert generate(llm).data.value == "ok"
    assert llm.calls == 2
    assert [(u.success, u.error_code) for u in llm.usages] == [
        (False, "LLM_TIMEOUT"),
        (True, None),
    ]


def test_non_retryable_error_fails_immediately() -> None:
    llm = ScriptedLlm([LlmError("LLM_REFUSED", retryable=False), Answer(value="ok")])
    with pytest.raises(LlmUnavailable) as exc:
        generate(llm)
    assert (exc.value.code, exc.value.retryable) == ("LLM_REFUSED", False)
    assert llm.calls == 1


def test_retries_exhausted_raises_unavailable() -> None:
    llm = ScriptedLlm([LlmError("LLM_SERVER_ERROR", retryable=True)] * 3, max_retries=2)
    with pytest.raises(LlmUnavailable) as exc:
        generate(llm)
    assert (exc.value.code, exc.value.retryable) == ("LLM_SERVER_ERROR", True)
    assert llm.calls == 3
    assert len(llm.usages) == 3


def test_recorder_failure_does_not_break_call() -> None:
    llm = ScriptedLlm([Answer(value="ok")])

    def broken(_: LlmUsage) -> None:
        raise RuntimeError("broker down")

    llm._recorder = broken
    assert generate(llm).data.value == "ok"


def test_unconfigured_llm_is_unavailable_without_retry() -> None:
    usages: list[LlmUsage] = []
    with pytest.raises(LlmUnavailable) as exc:
        generate(UnconfiguredLlm("claude-sonnet-5-5", usages.append))
    assert (exc.value.code, exc.value.retryable) == ("LLM_NOT_CONFIGURED", False)
    assert usages == []  # 실제 LLM 호출이 없으므로 사용량 미기록 (NFR-PRF-02 "호출마다")


def test_deadline_cuts_timeout_and_stops_retry() -> None:
    llm = ScriptedLlm([LlmError("LLM_TIMEOUT", retryable=True), Answer(value="ok")])
    requests: list[LlmRequest] = []
    original = llm._request

    async def capture(request: LlmRequest[T]) -> ProviderResponse[T]:
        requests.append(request)
        return await original(request)

    llm._request = capture  # type: ignore[method-assign]
    deadline = time.monotonic() + 3
    result = asyncio.run(
        llm.generate(
            system="s",
            user="u",
            output=Answer,
            call_type="FOLLOWUP",
            prompt_version="followup@3",
            deadline=deadline,
        )
    )
    assert result.data.value == "ok"
    assert all(0 < request.timeout <= 3 for request in requests)  # 15초 대신 남은 시간


def test_expired_deadline_sends_no_request() -> None:
    llm = ScriptedLlm([Answer(value="ok")])
    with pytest.raises(LlmUnavailable) as exc:
        asyncio.run(
            llm.generate(
                system="s",
                user="u",
                output=Answer,
                call_type="FOLLOWUP",
                prompt_version="followup@3",
                deadline=time.monotonic() - 1,
            )
        )
    assert (exc.value.code, exc.value.retryable) == ("LLM_DEADLINE_EXCEEDED", True)
    assert (llm.calls, llm.usages) == (0, [])


# --- 스트리밍 (분석 대화 답변) ------------------------------------------------


class StreamingLlm(ScriptedLlm):
    """stream 단계: 조각·실패 목록. 목록 끝까지 가면 StreamEnd."""

    def __init__(self, streams: list[list[str | LlmError]], max_retries: int = 1) -> None:
        super().__init__([], max_retries)
        self._streams = streams
        self.requests: list[LlmRequest] = []

    async def _stream(self, request: LlmRequest) -> AsyncIterator[str | StreamEnd]:
        self.requests.append(request)
        for item in self._streams[len(self.requests) - 1]:
            if isinstance(item, LlmError):
                raise item
            yield item
        yield StreamEnd("fake-model", 10, 5)


def collect(llm: LlmClient, deadline: float | None = None) -> tuple[list[str], str | None]:
    async def run() -> tuple[list[str], str | None]:
        stream = llm.stream(
            system="s",
            user="u",
            call_type="ANALYSIS",
            prompt_version="analysis@2",
            deadline=deadline,
        )
        return [text async for text in stream], stream.model

    return asyncio.run(run())


def test_stream_yields_chunks_and_records_one_usage() -> None:
    llm = StreamingLlm([["안녕", "하세요"]])
    assert collect(llm) == (["안녕", "하세요"], "fake-model")
    assert [(u.call_type, u.success, u.input_tokens) for u in llm.usages] == [
        ("ANALYSIS", True, 10)
    ]


def test_stream_failure_before_first_chunk_is_retried() -> None:
    llm = StreamingLlm([[LlmError("LLM_SERVER_ERROR", retryable=True)], ["ok"]])
    assert collect(llm)[0] == ["ok"]
    assert [(u.success, u.error_code) for u in llm.usages] == [
        (False, "LLM_SERVER_ERROR"),
        (True, None),
    ]


def test_stream_failure_after_first_chunk_is_not_retried() -> None:
    llm = StreamingLlm([["앞", LlmError("LLM_CONNECTION", retryable=True)], ["ok"]])
    got: list[str] = []

    async def run() -> None:
        async for text in llm.stream(
            system="s", user="u", call_type="ANALYSIS", prompt_version="analysis@2"
        ):
            got.append(text)

    with pytest.raises(LlmUnavailable) as exc:
        asyncio.run(run())
    assert (exc.value.code, got, len(llm.requests)) == ("LLM_CONNECTION", ["앞"], 1)
    assert [u.error_code for u in llm.usages] == ["LLM_CONNECTION"]


def test_stream_without_end_is_invalid_output() -> None:
    class Truncated(StreamingLlm):
        async def _stream(self, request: LlmRequest) -> AsyncIterator[str | StreamEnd]:
            self.requests.append(request)
            return
            yield ""

    with pytest.raises(LlmUnavailable) as exc:
        collect(Truncated([], max_retries=0))
    assert exc.value.code == "LLM_INVALID_OUTPUT"


def test_stream_stalls_past_timeout() -> None:
    class Stalled(StreamingLlm):
        async def _stream(self, request: LlmRequest) -> AsyncIterator[str | StreamEnd]:
            self.requests.append(request)
            yield "앞"
            await asyncio.sleep(5)
            yield StreamEnd("fake-model", 1, 1)

    llm = Stalled([], max_retries=0)
    with pytest.raises(LlmUnavailable) as exc:
        collect(llm, deadline=time.monotonic() + 0.2)
    assert exc.value.code == "LLM_TIMEOUT"
    assert 0 < llm.requests[0].timeout <= 0.2  # 15초 대신 남은 시간


def test_unconfigured_stream_is_unavailable_without_usage() -> None:
    usages: list[LlmUsage] = []
    with pytest.raises(LlmUnavailable) as exc:
        collect(UnconfiguredLlm("gpt", usages.append))
    assert (exc.value.code, usages) == ("LLM_NOT_CONFIGURED", [])
