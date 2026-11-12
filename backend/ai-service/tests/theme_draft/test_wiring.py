"""테마 경로 연결: 테마 모델 설정이 틀리면 이 경로만 503, 맞으면 그래프 실행기로 응답."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.config import get_settings
from tests.theme_draft.helpers import request_body
from tests.theme_draft.test_graph import gen_llm, review_llm

HEADERS = {"X-Internal-Token": "test-token"}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def post_theme(app_setup=None) -> tuple[int, dict]:  # noqa: ANN001
    app = create_app()
    with TestClient(app) as client:
        if app_setup:
            app_setup(app)
        response = client.post("/internal/theme-drafts", json=request_body(), headers=HEADERS)
        return response.status_code, response.json()


def test_same_generation_and_review_model_is_503_only_on_theme_route(
    env: pytest.MonkeyPatch,
) -> None:
    env.setenv("OPENAI_API_KEY", "sk-test-not-used")
    env.setenv("THEME_REVIEW_MODEL", "gpt-6-luna")
    status, body = post_theme()
    assert status == 503 and body["code"] == "AI_UNAVAILABLE" and body["retryable"] is False
    assert "THEME_REVIEW_MODEL" in body["detail"]
    with TestClient(create_app()) as client:  # 다른 경로는 그대로(기동도 막지 않음)
        assert client.get("/internal/versions", headers=HEADERS).status_code == 200


def test_missing_openai_key_is_503(env: pytest.MonkeyPatch) -> None:
    env.delenv("OPENAI_API_KEY", raising=False)
    status, body = post_theme()
    assert status == 503 and body["retryable"] is False and "키" in body["detail"]


def test_configured_route_runs_graph_with_theme_llms(env: pytest.MonkeyPatch) -> None:
    env.setenv("OPENAI_API_KEY", "sk-test-not-used")  # 클라이언트 생성만, 호출은 가짜로 교체
    gen, review = gen_llm(), review_llm()

    def swap(app) -> None:  # noqa: ANN001
        app.state.theme_llm, app.state.theme_review_llm = gen, review

    status, body = post_theme(swap)
    assert status == 200 and body["failure"] is None
    assert body["versions"] == {"model": "gen-model", "prompt": "theme-draft@1"}
    assert len(body["missions"]) == 5 and len(body["dialogues"]) == 5
    assert gen.count("GeneratedTheme") == 1 and review.count("GeneratedStoryReview") == 1


def test_default_theme_models_differ() -> None:
    settings = get_settings()
    assert (settings.theme_generation_model, settings.theme_review_model) == (
        "gpt-6-luna",
        "gpt-6.1-terra",
    )
