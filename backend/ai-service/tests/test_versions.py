from fastapi.testclient import TestClient

from app.bootstrap import create_app


def test_versions_returns_active_prompt_versions() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/internal/versions", headers={"X-Internal-Token": "test-token"})
    assert response.status_code == 200
    assert response.json() == {
        "prompts": {
            "judgment": "judge@2",
            "followup": "followup@4",
            "analysis": "analysis@1",
            "reportNarrative": "report@1",
        }
    }


def test_versions_requires_internal_token() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/internal/versions").status_code == 401
