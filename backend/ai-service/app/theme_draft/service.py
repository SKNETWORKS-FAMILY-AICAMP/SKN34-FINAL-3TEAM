"""주간 테마 초안 1회 생성 (api-spec 4.2, class-diagram 5.5, #437).

- 요청 1번에 그래프를 한 번 끝까지 실행한다. 그래프 안에서 실패한 부분만 실패 사유를 넣어 상한까지
  다시 만들고, 마감(theme_draft_deadline)까지 남은 시간이 부족하면 다음 재생성을 시작하지 않는다.
- 끝내 실패하면 200 + failure. 형식 밖 LLM 응답은 502, 그 밖 실패·마감 초과는 503.
- 그래프(ThemeDraftRunner 구현)는 글 단계부터 차례로 붙인다. 붙기 전에는 503(준비 중)을 돌려준다.
"""

import time
from typing import Protocol

from app.config import Settings
from app.errors import ApiError
from app.theme_draft.models import ThemeDraftRequest, ThemeDraftResponse


class ThemeDraftRunner(Protocol):
    async def run(self, request: ThemeDraftRequest, deadline: float) -> ThemeDraftResponse: ...


class NotReadyRunner:
    """그래프가 붙기 전 자리. 재시도해도 결과가 같으므로 retryable=False."""

    async def run(self, request: ThemeDraftRequest, deadline: float) -> ThemeDraftResponse:
        raise ApiError(503, "AI_UNAVAILABLE", "테마 초안 생성 준비 중", retryable=False)


class ThemeDraftService:
    def __init__(self, runner: ThemeDraftRunner, settings: Settings) -> None:
        self._runner = runner
        self._settings = settings

    async def generate(self, request: ThemeDraftRequest) -> ThemeDraftResponse:
        deadline = time.monotonic() + self._settings.theme_draft_deadline
        return await self._runner.run(request, deadline)
