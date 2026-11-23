"""#782 설계 v11 운영 그물: 그래프 전체를 마감 + 여유에서 끊는다(8차 측정에서 테마 하나가
끝나지 않음)."""

import asyncio
import time

import pytest

from app.config import get_settings
from app.errors import ApiError
from app.prompt_versions.registry import ActiveVersions
from app.theme_draft.models import ThemeDraftRequest
from app.theme_draft.service import ThemeDraftGraphRunner
from tests.theme_draft.helpers import request_body
from tests.theme_draft.test_graph import ScriptedLlm, review_llm


class HangingLlm(ScriptedLlm):
    """응답하지 않고 계속 기다리는 생성 모델(연결이 안 풀린 요청을 흉내)."""

    async def _request(self, request):  # type: ignore[no-untyped-def]
        await asyncio.Event().wait()
        raise AssertionError("닿지 않음")


def test_hanging_graph_is_cut_after_deadline_plus_grace() -> None:
    settings = get_settings().model_copy(update={"theme_draft_hang_grace": 0.2})
    runner = ThemeDraftGraphRunner(HangingLlm("gen", {}), review_llm(), settings, ActiveVersions())
    request = ThemeDraftRequest.model_validate(request_body())
    started = time.monotonic()
    with pytest.raises(ApiError) as caught:
        asyncio.run(runner.run(request, started + 0.3))
    assert caught.value.status == 503 and caught.value.extra.get("retryable") is True
    assert time.monotonic() - started < 5  # 마감 0.3초 + 여유 0.2초에서 끊김


def test_grace_keeps_total_inside_learning_wait() -> None:
    """learning은 테마 ai 호출을 16분(960초) 기다림(app.theme-draft.ai-read-timeout)."""
    settings = get_settings()
    assert settings.theme_draft_deadline + settings.theme_draft_hang_grace < 960
