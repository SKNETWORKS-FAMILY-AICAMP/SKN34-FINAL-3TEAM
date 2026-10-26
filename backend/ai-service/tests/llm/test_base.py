import asyncio

import pytest
from pydantic import BaseModel

from app.llm.base import (
    LlmClient,
    LlmError,
    LlmRequest,
    LlmUnavailable,
    LlmUsage,
    ProviderResponse,
    T,
    UnconfiguredLlm,
)


class Answer(BaseModel):
    value: str


class ScriptedLlm(LlmClient):
    """정해 둔 순서대로 응답하거나 실패하는 가짜 제공자."""

    def __init__(self, steps: list[LlmError | Answer], max_retries: int = 2) -> None:
        self.usages: list[LlmUsage] = []
        super().__init__("fake-model", max_retries, self.usages.append, backoff_seconds=0)
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
    assert [(u.model, u.input_tokens, u.error_code) for u in usages] == [
        ("claude-sonnet-5-5", None, "LLM_NOT_CONFIGURED")
    ]
