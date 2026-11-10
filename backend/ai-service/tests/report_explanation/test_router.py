from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.llm.providers import get_explanation_llm, get_llm
from app.prompt_versions.registry import ActiveVersions
from tests.fakes import FakeLlm
from tests.report_explanation.test_service import BODY, active

HEADERS = {"X-Internal-Token": "test-token"}


def post(
    llm: FakeLlm,
    body: dict = BODY,
    versions: ActiveVersions | None = None,
    headers: dict[str, str] = HEADERS,
):
    app = create_app()
    app.dependency_overrides[get_explanation_llm] = lambda: llm
    app.dependency_overrides[get_llm] = lambda: FakeLlm()  # 설명은 기본 LLM을 쓰지 않음
    with TestClient(app) as client:
        app.state.active_versions = versions or active("explanation/grade-5/narrative")
        return client.post("/internal/report-explanations", json=body, headers=headers)


def test_active_response_uses_camel_case_and_nullable_quote() -> None:
    response = post(FakeLlm("글자를 바르게 씀.", "문단을 나누지 않음."))
    assert response.status_code == 200
    assert response.json() == {
        "active": True,
        "explanation": {
            "text": "잘한 점: 글자를 바르게 씀.\n함께 이야기해 볼 점: 문단을 나누지 않음.",
            "quote": None,
        },
        "versions": {"model": "report-explanation@lora-1", "prompt": "report-explanation@1"},
    }


def test_inactive_response_has_only_active_false() -> None:
    response = post(FakeLlm(), versions=ActiveVersions())
    assert response.status_code == 200
    assert response.json() == {"active": False}


def test_scores_must_match_input_type_and_range() -> None:
    essay_keys = {**BODY, "inputType": "ESSAY"}
    out_of_range = {**BODY, "scores": {**BODY["scores"], "hol": 5}}
    blank = {**BODY, "text": "  "}
    for body in (essay_keys, out_of_range, blank, {**BODY, "grade": 2}):
        assert post(FakeLlm(), body=body).status_code == 400


def test_rejected_and_unavailable_problems() -> None:
    rejected = post(FakeLlm("4점.", "끝."))
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "AI_EXPLANATION_REJECTED"
    assert rejected.json()["retryable"] is False


def test_unconfigured_explanation_server_is_503_without_touching_default_llm() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.active_versions = active("explanation/grade-5/narrative")
        response = client.post("/internal/report-explanations", json=BODY, headers=HEADERS)
    assert response.status_code == 503
    assert response.json()["code"] == "AI_UNAVAILABLE"


def test_missing_internal_token_is_401() -> None:
    assert post(FakeLlm(), headers={}).status_code == 401
