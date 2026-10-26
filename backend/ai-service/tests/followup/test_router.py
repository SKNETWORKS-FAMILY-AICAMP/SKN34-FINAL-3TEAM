from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.followup.prompts import GeneratedQuestion
from app.llm.factory import get_llm
from tests.fakes import FakeLlm

HEADERS = {"X-Internal-Token": "test-token"}
BODY = {
    "timeline": [{"kind": "ANSWER", "text": "나는 찬성해."}],
    "judgment": {"result": "RETHINK", "heldReason": None, "elements": []},
    "rubric": {"elements": [{"elementId": "e1", "label": "주장"}]},
    "mission": {"title": "쉬는 시간", "question": "늘릴까?", "thinkingType": "EVALUATE"},
}


def post(llm: FakeLlm, headers: dict[str, str] = HEADERS, body: dict = BODY):
    app = create_app()
    app.dependency_overrides[get_llm] = lambda: llm
    with TestClient(app) as client:
        return client.post("/internal/followups", json=body, headers=headers)


def test_followup_response_uses_camel_case() -> None:
    response = post(FakeLlm(GeneratedQuestion(question="문제를 다시 읽어 볼까?")))
    assert response.status_code == 200
    assert response.json() == {
        "type": "LOOK_AGAIN",
        "question": "문제를 다시 읽어 볼까?",
        "source": "LLM",
        "leakCheck": {"passed": True},
        "versions": {"model": "fake-model", "prompt": "followup@1"},
    }


def test_missing_internal_token_is_401() -> None:
    assert post(FakeLlm(), headers={}).status_code == 401


def test_empty_timeline_is_rejected() -> None:
    response = post(FakeLlm(), body={**BODY, "timeline": []})
    assert response.status_code == 400
