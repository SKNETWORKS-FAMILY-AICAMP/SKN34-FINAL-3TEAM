import asyncio
from typing import Any

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.errors import ApiError
from app.judgment.extractor import Extraction
from app.judgment.models import JudgmentRequest, RubricElement
from app.judgment.service import JudgmentService
from app.llm.base import LlmError
from tests.fakes import FakeLlm

ANSWER = "나는 찬성해. 왜냐하면 쉬는 시간이 길면 더 잘 놀 수 있기 때문이야."


def make_request(**overrides: Any) -> JudgmentRequest:
    body: dict[str, Any] = {
        "answerText": ANSWER,
        "inputType": "NARRATIVE",
        "grade": 5,
        "rubric": {
            "elements": [
                {
                    "elementId": "e1",
                    "label": "주장",
                    "description": "자기 주장",
                    "points": 1,
                    "judgeVerified": False,
                },
                {
                    "elementId": "e2",
                    "label": "까닭",
                    "description": "까닭",
                    "points": 2,
                    "judgeVerified": False,
                },
            ]
        },
        "versions": {"mission": "m-12@3", "rubric": "r-12@2"},
    }
    body.update(overrides)
    return JudgmentRequest.model_validate(body)


def extraction(*items: tuple[str, str, str | None]) -> Extraction:
    return Extraction.model_validate(
        {"elements": [{"elementId": e, "status": s, "quote": q} for e, s, q in items]}
    )


def judge(llm: FakeLlm, request: JudgmentRequest | None = None, **settings: Any):
    service = JudgmentService(llm, Settings(internal_token="t", **settings))
    return asyncio.run(service.judge(request or make_request()))


def test_all_elements_verified_is_correct() -> None:
    llm = FakeLlm(
        extraction(
            ("e1", "FOUND", "나는 찬성해"),
            ("e2", "FOUND", "쉬는 시간이 길면 더 잘 놀 수 있기 때문이야"),
        )
    )
    response = judge(llm)
    assert response.result == "CORRECT"
    assert [(e.element_id, e.verified, e.satisfied) for e in response.elements] == [
        ("e1", True, True),
        ("e2", True, True),
    ]
    assert response.trial is True
    assert response.versions.model_dump() == {
        "mission": "m-12@3",
        "rubric": "r-12@2",
        "model": "fake-model",
        "prompt": "judge@2",
    }


def test_missing_required_element_is_partial() -> None:
    llm = FakeLlm(extraction(("e1", "FOUND", "나는 찬성해"), ("e2", "NOT_FOUND", None)))
    response = judge(llm)
    assert response.result == "PARTIAL"
    assert response.elements[1].model_dump() == {
        "element_id": "e2",
        "quote": None,
        "verified": False,
        "satisfied": False,
    }


def test_no_points_is_rethink() -> None:
    llm = FakeLlm(extraction(("e1", "NOT_FOUND", None), ("e2", "NOT_FOUND", None)))
    assert judge(llm).result == "RETHINK"


def with_good_thought() -> JudgmentRequest:
    request = make_request()
    request.rubric.elements.append(
        RubricElement(
            element_id="e3",
            label="다른 관점",
            description="반대 입장 고려",
            points=1,
            judge_verified=False,
            good_thought=True,
        )
    )
    return request


@pytest.mark.parametrize(
    ("items", "result"),
    [
        # 필수 요소(e1·e2)만 충족, 들어가면 좋은 생각(e3) 없음 → CORRECT
        (
            (
                ("e1", "FOUND", "나는 찬성해"),
                ("e2", "FOUND", "더 잘 놀 수 있기 때문이야"),
                ("e3", "NOT_FOUND", None),
            ),
            "CORRECT",
        ),
        # 좋은 생각만 충족 → PARTIAL
        (
            (("e1", "NOT_FOUND", None), ("e2", "NOT_FOUND", None), ("e3", "FOUND", "나는 찬성해")),
            "PARTIAL",
        ),
    ],
)
def test_good_thought_is_not_required(items: tuple, result: str) -> None:
    assert judge(FakeLlm(extraction(*items)), with_good_thought()).result == result


def test_nullable_rubric_fields_are_accepted() -> None:
    request = make_request(
        rubric={
            "elements": [
                {
                    "elementId": "e1",
                    "label": "주장",
                    "description": None,
                    "points": 1,
                    "commonErrors": None,
                    "judgeVerified": False,
                }
            ]
        }
    )
    llm = FakeLlm(extraction(("e1", "FOUND", "나는 찬성해")))
    assert judge(llm, request).result == "CORRECT"
    assert "설명:" not in llm.requests[0].user


@pytest.mark.parametrize(
    ("items", "reason"),
    [
        # LLM이 판단 못 함
        ((("e1", "UNCLEAR", None), ("e2", "FOUND", "나는 찬성해")), "INSUFFICIENT_EVIDENCE"),
        # 요소 누락
        ((("e1", "FOUND", "나는 찬성해"),), "INSUFFICIENT_EVIDENCE"),
        # 원문에 없는 구절 (지어냄)
        ((("e1", "FOUND", "나는 찬성해"), ("e2", "FOUND", "시간이 절약되니까")), "QUOTE_MISMATCH"),
        # FOUND인데 구절 없음
        ((("e1", "FOUND", "나는 찬성해"), ("e2", "FOUND", None)), "QUOTE_MISMATCH"),
    ],
)
def test_held_after_llm_has_no_elements(items: tuple, reason: str) -> None:
    response = judge(FakeLlm(extraction(*items)))
    assert (response.result, response.held_reason, response.elements) == ("HELD", reason, [])
    assert response.versions.prompt == "judge@2"


@pytest.mark.parametrize(
    ("overrides", "settings", "reason"),
    [
        ({"answerText": " 몰 라 요 "}, {}, "TOO_SHORT"),
        ({}, {"judge_require_verified": True}, "UNVERIFIED_SCOPE"),
    ],
)
def test_held_before_llm_does_not_call_llm(
    overrides: dict[str, Any], settings: dict[str, Any], reason: str
) -> None:
    llm = FakeLlm()
    response = judge(llm, make_request(**overrides), **settings)
    assert (response.result, response.held_reason) == ("HELD", reason)
    assert llm.requests == []
    assert response.versions.model is None


def test_verified_rubric_is_judged_when_verification_required() -> None:
    request = make_request()
    for element in request.rubric.elements:
        element.judge_verified = True
    llm = FakeLlm(extraction(("e1", "NOT_FOUND", None), ("e2", "NOT_FOUND", None)))
    assert judge(llm, request, judge_require_verified=True).result == "RETHINK"


def test_llm_failure_is_503_not_held() -> None:
    llm = FakeLlm(LlmError("LLM_TIMEOUT", retryable=True))
    with pytest.raises(ApiError) as exc:
        judge(llm)
    assert (exc.value.status, exc.value.code, exc.value.extra) == (
        503,
        "AI_UNAVAILABLE",
        {"retryable": True},
    )


def test_prompt_has_no_student_identifiers() -> None:
    llm = FakeLlm(extraction(("e1", "NOT_FOUND", None), ("e2", "NOT_FOUND", None)))
    judge(llm)
    prompt = llm.requests[0].user
    assert ANSWER in prompt and "m-12@3" not in prompt


@pytest.mark.parametrize("grade", [2, 7])
def test_grade_outside_supported_range_is_rejected(grade: int) -> None:
    with pytest.raises(ValidationError):
        make_request(grade=grade)  # 지원 학년 초3~6 (P03), 초1~2 보류 규칙은 문서에서 삭제됨


def test_lowest_supported_grade_is_judged() -> None:
    llm = FakeLlm(extraction(("e1", "FOUND", "나는 찬성해"), ("e2", "NOT_FOUND", None)))
    assert judge(llm, make_request(grade=3)).result == "PARTIAL"


def test_solution_steps_are_judged() -> None:
    # sequence-diagram: 서술·논술·풀이 단계는 ai 판정 (M1 점검은 범위 밖)
    llm = FakeLlm(extraction(("e1", "FOUND", "나는 찬성해"), ("e2", "NOT_FOUND", None)))
    assert judge(llm, make_request(inputType="SOLUTION_STEPS")).result == "PARTIAL"


def test_trial_is_false_only_when_all_elements_verified() -> None:
    items = (("e1", "NOT_FOUND", None), ("e2", "NOT_FOUND", None))
    assert judge(FakeLlm(extraction(*items))).trial is True
    request = make_request()
    for element in request.rubric.elements:
        element.judge_verified = True
    assert judge(FakeLlm(extraction(*items)), request).trial is False


def test_zero_point_element_only_is_rethink() -> None:
    # 배점 기준: 충족 요소가 있어도 충족 배점이 0이면 RETHINK
    request = make_request()
    request.rubric.elements[0].points = 0
    llm = FakeLlm(extraction(("e1", "FOUND", "나는 찬성해"), ("e2", "NOT_FOUND", None)))
    assert judge(llm, request).result == "RETHINK"


def test_duplicate_and_unknown_element_ids_from_llm() -> None:
    # 같은 요소가 두 번 오면 첫 번째만, 기준표에 없는 요소는 무시
    llm = FakeLlm(
        extraction(
            ("e1", "FOUND", "나는 찬성해"),
            ("e1", "FOUND", "지어낸 구절"),
            ("e2", "NOT_FOUND", None),
            ("e9", "FOUND", "지어낸 구절"),
        )
    )
    response = judge(llm)
    assert response.result == "PARTIAL"
    assert [e.element_id for e in response.elements] == ["e1", "e2"]


def test_held_before_llm_has_no_elements() -> None:
    response = judge(FakeLlm(), make_request(answerText="몰라요"))
    assert (response.result, response.elements, response.trial) == ("HELD", [], True)
