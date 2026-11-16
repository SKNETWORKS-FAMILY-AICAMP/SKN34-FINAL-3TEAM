"""미션 초안 서비스의 테마용 최소 확장(#437).

주지 않으면 /internal/mission-drafts와 같게 동작한다.
"""

import asyncio
import time

from app.config import get_settings
from app.mission_draft import checks
from app.mission_draft.prompts import build_user
from app.mission_draft.service import MissionDraftService
from tests.fakes import FakeLlm
from tests.mission_draft.helpers import make_request, narrative_draft


def test_defaults_keep_mission_draft_behavior() -> None:
    llm = FakeLlm(narrative_draft())
    settings = get_settings()
    request = make_request()
    started = time.monotonic()
    response = asyncio.run(MissionDraftService(llm, settings).generate(request))
    (sent,) = llm.requests
    limit = checks.question_limit(settings.mission_draft_question_max_chars, request.grade_min)
    assert sent.user == build_user(request, limit)
    assert sent.call_type == "MISSION_DRAFT" and llm.usages[0].call_type == "MISSION_DRAFT"
    assert sent.timeout <= settings.mission_draft_llm_timeout
    assert (
        sent.timeout
        > min(settings.mission_draft_llm_timeout, settings.mission_draft_deadline)
        - (time.monotonic() - started)
        - 1
    )
    assert response.checks.passed


def test_theme_extras_append_text_and_change_call_type_and_time() -> None:
    llm = FakeLlm(narrative_draft())
    settings = get_settings()
    request = make_request()
    deadline = time.monotonic() + 600
    asyncio.run(
        MissionDraftService(llm, settings).generate(
            request,
            extra_user="테마 이야기 조각",
            call_type="THEME_DRAFT",
            deadline=deadline,
            timeout=180,
        )
    )
    (sent,) = llm.requests
    limit = checks.question_limit(settings.mission_draft_question_max_chars, request.grade_min)
    assert sent.user == build_user(request, limit) + "\n테마 이야기 조각"
    assert sent.call_type == "THEME_DRAFT" and llm.usages[0].call_type == "THEME_DRAFT"
    assert 170 < sent.timeout <= 180  # 미션 초안 기본 타임아웃 대신 테마 값
