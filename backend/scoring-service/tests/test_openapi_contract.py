"""실제 내부 라우터·응답 스키마와 팀 OpenAPI 계약의 불일치를 탐지한다."""

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.bootstrap import create_app

SPEC = Path(__file__).resolve().parents[3] / "contracts/openapi/scoring-service.yaml"


def test_documented_operations_and_response_models_match_runtime():
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    runtime = create_app().openapi()
    actual = {
        (method, path.removeprefix("/internal"))
        for path, methods in runtime["paths"].items()
        if path.startswith("/internal/")
        for method in methods
    }
    documented = {(method, path) for path, methods in spec["paths"].items() for method in methods}
    assert actual == documented == {("get", "/versions"), ("post", "/m2/scores")}
    for name in (
        "ModelVersionSummary",
        "VersionsResponse",
        "M2Request",
        "M2Active",
        "M2Inactive",
        "Scores",
        "RawScores",
        "ModelIdentity",
    ):
        assert spec["components"]["schemas"][name] == runtime["components"]["schemas"][name]
    assert (
        spec["paths"]["/versions"]["get"]["responses"]["200"]["content"]
        == (runtime["paths"]["/internal/versions"]["get"]["responses"]["200"]["content"])
    )


def test_authentication_failure_matches_documented_problem():
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    # 인증 실패는 lifespan/모델 로딩을 시작하지 않아도 확인할 수 있다.
    client = TestClient(create_app())
    response = client.get("/internal/versions")
    assert response.status_code == 401
    assert spec["security"] == [{"InternalToken": []}]
    assert spec["components"]["securitySchemes"]["InternalToken"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-Internal-Token",
    }
    problem = spec["paths"]["/versions"]["get"]["responses"]["401"]["content"]
    assert response.headers["content-type"] in problem
    assert problem["application/problem+json"]["schema"] == {"$ref": "#/components/schemas/Problem"}
    assert set(spec["components"]["schemas"]["Problem"]["required"]) <= response.json().keys()
    assert response.json()["code"] == "UNAUTHENTICATED"
