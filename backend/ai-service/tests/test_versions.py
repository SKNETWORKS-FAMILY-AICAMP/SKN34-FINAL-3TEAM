from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.bootstrap import create_app
from app.prompt_versions.models import PROMPT_SCOPES

OPENAPI = Path(__file__).resolve().parents[3] / "contracts/openapi/ai-service.yaml"


def _versions_schema() -> dict:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    response = spec["paths"]["/versions"]["get"]["responses"]["200"]
    return response["content"]["application/json"]["schema"]


def test_versions_returns_active_prompt_versions() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/internal/versions", headers={"X-Internal-Token": "test-token"})
    assert response.status_code == 200
    assert response.json() == {
        "prompts": {
            "judgment": "judge@2",
            "followup": "followup@4",
            "analysis": "analysis@4",
            "reportNarrative": "report@1",
            "reportTemplate": "analysis-template@1",
            "missionDraft": "mission-draft@1",
            "reportExplanation": "report-explanation@1",
        }
    }


def test_versions_response_matches_openapi_contract() -> None:
    # 실제 응답이 contracts/openapi/ai-service.yaml의 /versions 스키마를 통과해야 한다 (#502)
    schema = _versions_schema()
    with TestClient(create_app()) as client:
        body = client.get("/internal/versions", headers={"X-Internal-Token": "test-token"}).json()
    Draft202012Validator(schema).validate(body)
    prompts = schema["properties"]["prompts"]
    assert set(prompts["required"]) == set(prompts["properties"]) == set(PROMPT_SCOPES)


def test_versions_requires_internal_token() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/internal/versions").status_code == 401
