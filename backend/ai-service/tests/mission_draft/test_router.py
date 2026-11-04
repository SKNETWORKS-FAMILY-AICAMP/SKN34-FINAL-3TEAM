from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.llm.base import LlmError
from app.llm.providers import get_llm
from tests.fakes import FakeLlm
from tests.mission_draft.helpers import EVALUATE_CODES, narrative_draft

HEADERS = {"X-Internal-Token": "test-token"}
BODY = {
    "standards": [{"code": "6국01-02", "statement": "의견을 제시하고 함께 조정하며 토의한다."}],
    "thinkingType": "EVALUATE",
    "elementCodes": EVALUATE_CODES,
    "gradeMin": 5,
    "gradeMax": 5,
    "inputType": "NARRATIVE",
    "previousFailures": [],
}


def post(llm: FakeLlm, headers: dict[str, str] = HEADERS, body: dict = BODY):
    app = create_app()
    app.dependency_overrides[get_llm] = lambda: llm
    with TestClient(app) as client:
        return client.post("/internal/mission-drafts", json=body, headers=headers)


def test_response_uses_camel_case_contract_fields() -> None:
    response = post(FakeLlm(narrative_draft()))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"draft", "checks", "versions"}
    assert body["checks"] == {"passed": True, "failures": []}
    assert body["versions"] == {"model": "fake-model", "prompt": "mission-draft@1"}
    assert {"sceneNote", "answerKey", "exampleAnswer", "forbiddenTerms"} <= set(body["draft"])
    assert body["draft"]["elements"][0] == {
        "code": "EVALUATE_CLAIM",
        "label": "EVALUATE_CLAIM",
        "description": "EVALUATE_CLAIM 설명",
        "goodThought": False,
        "standardCode": "6국01-02",
    }


def test_missing_internal_token_is_401() -> None:
    assert post(FakeLlm(), headers={}).status_code == 401


def test_bad_request_is_400() -> None:
    assert post(FakeLlm(), body={**BODY, "standards": []}).status_code == 400
    assert post(FakeLlm(), body={**BODY, "inputType": "ESSAY", "gradeMin": 4}).status_code == 400


def test_invalid_output_is_502_and_llm_failure_is_503_with_retryable() -> None:
    bad = post(FakeLlm(LlmError("LLM_INVALID_OUTPUT", retryable=True)))
    assert bad.status_code == 502
    assert bad.headers["content-type"] == "application/problem+json"
    assert bad.json()["retryable"] is True
    down = post(FakeLlm(LlmError("LLM_SERVER_ERROR", retryable=True)))
    assert down.status_code == 503
    assert down.json()["code"] == "AI_UNAVAILABLE"
