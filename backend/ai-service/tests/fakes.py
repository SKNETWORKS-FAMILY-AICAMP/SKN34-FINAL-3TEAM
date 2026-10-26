"""테스트용 가짜 LLM. 실제 API를 호출하지 않음 (CI에서 실제 호출 없음)."""

from pydantic import BaseModel

from app.llm.base import LlmClient, LlmError, LlmRequest, LlmUsage, ProviderResponse, T


class FakeLlm(LlmClient):
    """정해 둔 순서대로 응답(BaseModel)하거나 실패(LlmError)."""

    def __init__(self, *steps: BaseModel | LlmError, max_retries: int = 0) -> None:
        self.usages: list[LlmUsage] = []
        super().__init__("fake-model", max_retries, self.usages.append, backoff_seconds=0)
        self._steps = list(steps)
        self.requests: list[LlmRequest] = []

    async def _request(self, request: LlmRequest[T]) -> ProviderResponse[T]:
        self.requests.append(request)
        step = self._steps[len(self.requests) - 1]
        if isinstance(step, LlmError):
            raise step
        return ProviderResponse(
            request.output.model_validate(step.model_dump()), "fake-model", 10, 5
        )
