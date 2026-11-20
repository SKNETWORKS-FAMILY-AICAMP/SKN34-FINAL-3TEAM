from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.llm.providers import get_explanation_llm, get_llm
from app.prompt_versions.registry import ActiveVersions
from tests.fakes import FakeLlm
from tests.report_explanation.test_service import BODY, active, detail

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
    llm = FakeLlm(
        detail(
            analysis="글자를 바르게 썼습니다.",
            improvement_points=None,
            next_steps="앞으로 문단을 나눠 보게 해 주세요.",
        )
    )
    response = post(llm)
    assert response.status_code == 200
    assert response.json() == {
        "active": True,
        "explanation": {
            "text": (
                "상세 분석\n글자를 바르게 썼습니다.\n\n"
                "개선 방안\n앞으로 문단을 나눠 보게 해 주세요."
            ),
            "quote": None,
        },
        "versions": {"model": "report-explanation@lora-1", "prompt": "report-explanation@4"},
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
    bad = detail(analysis="4점짜리 글입니다.")
    rejected = post(FakeLlm(bad, bad))  # 한 번 다시 만들어도 검사에 걸리면 422
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
