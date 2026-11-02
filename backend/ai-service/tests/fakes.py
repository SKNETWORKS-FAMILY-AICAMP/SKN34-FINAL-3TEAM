"""테스트용 가짜 LLM. 실제 API를 호출하지 않음 (CI에서 실제 호출 없음)."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from app.llm.base import (
    LlmClient,
    LlmError,
    LlmRequest,
    LlmUsage,
    ProviderResponse,
    StreamEnd,
    T,
)

Step = BaseModel | LlmError | str | list[str | LlmError]


class FakeLlm(LlmClient):
    """정해 둔 순서대로 응답하거나 실패. delay초만큼 걸리는 척함.

    generate 단계: BaseModel(응답)·LlmError(실패)
    stream 단계: str(조각 여러 개로 나눠 보냄)·list(조각·실패를 순서대로)·LlmError(첫 조각 전 실패)
    """

    def __init__(self, *steps: Step, max_retries: int = 0, delay: float = 0) -> None:
        self.usages: list[LlmUsage] = []
        super().__init__(
            "fake-model", max_retries, self.usages.append, backoff_seconds=0, timeout=15
        )
        self._steps = list(steps)
        self._delay = delay
        self.requests: list[LlmRequest] = []

    async def _request(self, request: LlmRequest[T]) -> ProviderResponse[T]:
        step = self._next(request)
        await asyncio.sleep(self._delay)
        if isinstance(step, LlmError):
            raise step
        assert isinstance(step, BaseModel)
        return ProviderResponse(
            request.output.model_validate(step.model_dump()), "fake-model", 10, 5
        )

    async def _stream(self, request: LlmRequest[Any]) -> AsyncIterator[str | StreamEnd]:
        step = self._next(request)
        if isinstance(step, str):
            size = max(1, len(step) // 3)
            step = [step[i : i + size] for i in range(0, len(step), size)]
        elif isinstance(step, LlmError):
            step = [step]
        assert isinstance(step, list)
        for item in step:
            await asyncio.sleep(self._delay)
            if isinstance(item, LlmError):
                raise item
            yield item
        yield StreamEnd("fake-model", 10, 5)

    def _next(self, request: LlmRequest[Any]) -> Step:
        self.requests.append(request)
        return self._steps[len(self.requests) - 1]
