from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.judgment.extractor import Extraction
from app.llm.base import LlmError
from app.llm.providers import get_llm
from tests.fakes import FakeLlm

HEADERS = {"X-Internal-Token": "test-token"}
BODY = {
    "answerText": "나는 찬성해. 쉬는 시간이 길면 더 잘 놀 수 있어.",
    "inputType": "ESSAY",
    "grade": 5,
    "rubric": {
        "elements": [
            {
                "elementId": "e1",
                "label": "주장",
                "description": "자기 주장",
                "points": 1,
                "judgeVerified": False,
            }
        ]
    },
    "versions": {"mission": "m-1@1", "rubric": "r-1@1"},
}


def post(llm: FakeLlm, headers: dict[str, str] = HEADERS, body: dict = BODY):
    app = create_app()
    app.dependency_overrides[get_llm] = lambda: llm
    with TestClient(app) as client:
        return client.post("/internal/judgments", json=body, headers=headers)


def test_judgment_response_uses_camel_case() -> None:
    llm = FakeLlm(
        Extraction.model_validate(
            {"elements": [{"elementId": "e1", "status": "FOUND", "quote": "나는 찬성해"}]}
        )
    )
    response = post(llm)
    assert response.status_code == 200
    assert response.json() == {
        "result": "CORRECT",
        "elements": [
            {"elementId": "e1", "quote": "나는 찬성해", "verified": True, "satisfied": True}
        ],
        "heldReason": None,
        "trial": True,
        "versions": {
            "mission": "m-1@1",
            "rubric": "r-1@1",
            "model": "fake-model",
            "prompt": "judge@2",
        },
    }


def test_llm_failure_is_503_problem_with_retryable() -> None:
    response = post(FakeLlm(LlmError("LLM_SERVER_ERROR", retryable=True)))
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert (response.json()["code"], response.json()["retryable"]) == ("AI_UNAVAILABLE", True)


def test_missing_internal_token_is_401() -> None:
    assert post(FakeLlm(), headers={}).status_code == 401


def test_choice_input_is_rejected() -> None:
    response = post(FakeLlm(), body={**BODY, "inputType": "CHOICE"})
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"
