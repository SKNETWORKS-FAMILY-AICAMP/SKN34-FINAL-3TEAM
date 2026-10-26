import asyncio
from typing import Any

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.errors import ApiError
from app.followup.models import FollowupRequest
from app.followup.prompts import GeneratedQuestion
from app.followup.service import FollowupService
from app.llm.base import LlmError
from tests.fakes import FakeLlm

EXAMPLE = "쉬는 시간이 길면 친구와 더 친해지고 수업 집중도 잘 돼요."


def make_request(result: str = "PARTIAL", **overrides: Any) -> FollowupRequest:
    body: dict[str, Any] = {
        "timeline": [{"kind": "ANSWER", "text": "나는 쉬는 시간을 늘리는 것에 찬성해."}],
        "judgment": {
            "result": result,
            "heldReason": "TOO_SHORT" if result == "HELD" else None,
            "elements": [] if result == "HELD" else [{"elementId": "e1", "satisfied": True}],
        },
        "rubric": {
            "elements": [
                {"elementId": "e1", "label": "주장", "description": "자기 입장"},
                {"elementId": "e2", "label": "근거", "description": "입장의 까닭"},
            ],
            "answerKey": None,
            "forbiddenTerms": ["집중력 향상"],
            "exampleAnswer": EXAMPLE,
        },
        "mission": {
            "title": "쉬는 시간",
            "question": "쉬는 시간을 늘릴까?",
            "thinkingType": "EVALUATE",
        },
        "grade": 5,
    }
    body.update(overrides)
    return FollowupRequest.model_validate(body)


def question(text: str) -> GeneratedQuestion:
    return GeneratedQuestion(question=text)


def create(llm: FakeLlm, request: FollowupRequest | None = None, **settings: Any):
    service = FollowupService(llm, Settings(internal_token="t", **settings))
    return asyncio.run(service.create(request or make_request()))


@pytest.mark.parametrize(
    ("result", "followup_type"),
    [
        ("CORRECT", "ONE_STEP_MORE"),
        ("PARTIAL", "TELL_MORE"),
        ("RETHINK", "LOOK_AGAIN"),
        ("HELD", "TELL_MORE"),
    ],
)
def test_type_follows_judgment_result(result: str, followup_type: str) -> None:
    response = create(FakeLlm(question("왜 그렇게 생각했어?")), make_request(result))
    assert response.type == followup_type
    assert (response.source, response.leak_check.passed) == ("LLM", True)
    assert response.versions.model_dump() == {"model": "fake-model", "prompt": "followup@3"}


def test_leaked_question_is_regenerated_as_llm_retry() -> None:
    llm = FakeLlm(question("집중력 향상 때문일까?"), question("왜 그렇게 생각했는지 더 말해 볼까?"))
    response = create(llm)
    assert (response.question, response.source) == (
        "왜 그렇게 생각했는지 더 말해 볼까?",
        "LLM_RETRY",
    )
    # 재생성 요청에 앞서 거절된 질문을 알려 줌
    assert "집중력 향상 때문일까?" in llm.requests[1].user


def no_question(response) -> tuple:
    return (response.question, response.source, response.leak_check.passed)


def test_repeated_leak_returns_no_question_for_bank() -> None:
    # P16: 재생성 1회까지 유출이면 질문 없이 passed=false → learning이 질문 은행 사용
    llm = FakeLlm(*[question("쉬는 시간이 길면 친구와 더 친해지고 그럴까?")] * 2)
    response = create(llm)
    assert no_question(response) == (None, "LLM_RETRY", False)
    assert response.type == "TELL_MORE"
    assert len(llm.requests) == 2  # 최초 1회 + 재생성 1회


def test_regeneration_failure_falls_back_to_bank_not_503() -> None:
    llm = FakeLlm(question("집중력 향상 때문일까?"), LlmError("LLM_TIMEOUT", retryable=True))
    assert no_question(create(llm)) == (None, "LLM_RETRY", False)


def test_no_regeneration_after_deadline() -> None:
    # 첫 생성에 마감 시간을 다 써 버리면 재생성 요청 없이 질문 은행으로
    llm = FakeLlm(question("집중력 향상 때문일까?"), question("다시 만든 질문"), delay=0.2)
    response = create(llm, followup_deadline=0.1)
    assert no_question(response) == (None, "LLM_RETRY", False)
    assert len(llm.requests) == 1


def test_llm_timeout_is_cut_to_remaining_deadline() -> None:
    llm = FakeLlm(question("왜 그렇게 생각했어?"))
    create(llm, followup_deadline=5)
    assert 4 < llm.requests[0].timeout <= 5  # LLM 1회 15초보다 남은 시간이 짧으면 남은 시간


def test_empty_question_is_regenerated() -> None:
    llm = FakeLlm(question("  "), question("어떤 점이 좋을까?"))
    assert create(llm).source == "LLM_RETRY"


def test_llm_failure_is_503() -> None:
    with pytest.raises(ApiError) as exc:
        create(FakeLlm(LlmError("LLM_REFUSED", retryable=False)))
    assert (exc.value.status, exc.value.extra) == (503, {"retryable": False})


def test_example_answer_is_not_sent_but_banned_terms_are() -> None:
    llm = FakeLlm(question("왜 그렇게 생각했어?"))
    create(llm)
    prompt = llm.requests[0].user
    assert EXAMPLE not in prompt
    assert "집중력 향상" in prompt
    assert llm.requests[0].call_type == "FOLLOWUP"


@pytest.mark.parametrize(
    ("grade", "style"),
    [(3, "짧은 한 문장"), (4, "짧은 한 문장"), (5, "한 문장 위주"), (6, "한 문장 위주")],
)
def test_prompt_follows_grade(grade: int, style: str) -> None:
    llm = FakeLlm(question("왜 그렇게 생각했어?"))
    create(llm, make_request(grade=grade))
    prompt = llm.requests[0].user
    assert f"학년: 초{grade}" in prompt
    assert style in prompt


@pytest.mark.parametrize("grade", [2, 7])
def test_grade_outside_supported_range_is_rejected(grade: int) -> None:
    with pytest.raises(ValidationError):
        make_request(grade=grade)  # 지원 학년 초3~6 (P03)


def test_thinking_direction_only_for_one_step_more() -> None:
    llm = FakeLlm(question("반대하는 친구는 뭐라고 할까?"), question("왜 그렇게 생각했어?"))
    create(llm, make_request("CORRECT"))
    create(llm, make_request("PARTIAL"))
    assert "넓혀 갈 방향: 다른 입장이나 예외" in llm.requests[0].user
    assert "넓혀 갈 방향" not in llm.requests[1].user
