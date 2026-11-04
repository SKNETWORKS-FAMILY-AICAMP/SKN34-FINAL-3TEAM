import asyncio
from typing import Any

import pytest

from app.config import Settings
from app.errors import ApiError
from app.llm.base import LlmError
from app.mission_draft.service import MissionDraftService
from tests.fakes import FakeLlm
from tests.mission_draft.helpers import make_request, narrative_draft


def generate(llm: FakeLlm, request=None, **settings: Any):
    service = MissionDraftService(llm, Settings(internal_token="t", **settings))
    return asyncio.run(service.generate(request or make_request()))


def test_passing_draft_is_returned_with_versions_and_usage_type() -> None:
    llm = FakeLlm(narrative_draft())
    response = generate(llm)
    assert response.checks.passed
    assert response.checks.failures == []
    assert response.draft.title == "쉬는 시간을 늘릴까?"
    assert response.draft.elements[0].standard_code == "6국01-02"
    assert response.versions.model_dump() == {"model": "fake-model", "prompt": "mission-draft@1"}
    assert len(llm.requests) == 1
    assert llm.requests[0].call_type == "MISSION_DRAFT"
    assert [u.call_type for u in llm.usages] == ["MISSION_DRAFT"]


def test_failed_checks_are_still_200_and_not_regenerated() -> None:
    llm = FakeLlm(narrative_draft(question="집중력 향상에 도움이 될까?"))
    response = generate(llm)
    assert not response.checks.passed
    assert [(f.check, f.reason) for f in response.checks.failures] == [("LEAK", "FORBIDDEN_TERM")]
    assert len(llm.requests) == 1  # 반복은 learning이 함


def test_question_limit_setting_reaches_prompt_and_check() -> None:
    llm = FakeLlm(narrative_draft(question="가" * 60))
    response = generate(llm, mission_draft_question_max_chars={3: 50, 4: 50, 5: 50, 6: 50})
    assert "질문 글자 수 상한: 50자" in llm.requests[0].user
    assert [f.reason for f in response.checks.failures] == ["TOO_LONG"]


def test_mission_draft_waits_60_seconds_once_with_63_second_deadline() -> None:
    # #353: 주기 작업이라 이 호출만 LLM 60초 1회(P12 예외). 재시도하지 않음
    llm = FakeLlm(LlmError("LLM_TIMEOUT", retryable=True), narrative_draft(), max_retries=1)
    with pytest.raises(ApiError) as error:
        generate(llm)
    assert error.value.status == 503
    assert len(llm.requests) == 1
    assert 59 < llm.requests[0].timeout <= 60
    settings = Settings(internal_token="t")
    assert (settings.mission_draft_deadline, settings.mission_draft_llm_retries) == (63.0, 0)
    assert (settings.llm_timeout, settings.llm_max_retries) == (15.0, 1)  # 다른 호출은 그대로


def test_invalid_output_is_502() -> None:
    with pytest.raises(ApiError) as error:
        generate(FakeLlm(LlmError("LLM_INVALID_OUTPUT", retryable=True)))
    assert error.value.status == 502
    assert error.value.code == "AI_BAD_RESPONSE"


@pytest.mark.parametrize("code", ["LLM_TIMEOUT", "LLM_SERVER_ERROR", "LLM_AUTH"])
def test_other_llm_failures_are_503(code) -> None:
    with pytest.raises(ApiError) as error:
        generate(FakeLlm(LlmError(code, retryable=code != "LLM_AUTH")))
    assert error.value.status == 503
    assert error.value.code == "AI_UNAVAILABLE"
