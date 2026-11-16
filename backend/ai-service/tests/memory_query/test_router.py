"""POST /internal/memory-queries (#681, api-spec 4.2.7)."""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.bootstrap import create_app
from app.llm.base import LlmError
from app.llm.providers import get_llm
from app.security import caller_permits
from tests.fakes import FakeLlm
from tests.memory_query.test_service import BODY, GOOD, make

HEADERS = {"X-Internal-Token": "test-token"}
OPENAPI = Path(__file__).resolve().parents[4] / "contracts/openapi/ai-service.yaml"


def post(llm: FakeLlm, body: object = BODY, headers: dict[str, str] = HEADERS):
    app = create_app()
    app.dependency_overrides[get_llm] = lambda: llm
    with TestClient(app) as client:
        return client.post("/internal/memory-queries", json=body, headers=headers)


def operation() -> tuple[dict, dict]:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    return spec["paths"]["/memory-queries"]["post"], spec["components"]


def schema(status: str, media: str = "application/json") -> dict:
    op, components = operation()
    return {**op["responses"][status]["content"][media]["schema"], "components": components}


def test_response_is_camel_case_and_matches_openapi() -> None:
    response = post(FakeLlm(GOOD))
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "keywords": ["동물", "집"],
        "period": {"from": "2026-11-09", "to": "2026-11-16"},
        "searchText": "동물들이 살 수 있게 만든 것",
        "versions": {"model": "fake-model", "prompt": "memory-query@1"},
    }
    Draft202012Validator(schema("200")).validate(body)
    op, components = operation()
    assert "x-implementation-status" not in op
    request = {**op["requestBody"]["content"]["application/json"]["schema"]}
    Draft202012Validator({**request, "components": components}).validate(BODY)


def test_null_period_matches_openapi() -> None:
    body = post(FakeLlm(make(period=None))).json()
    assert body["period"] is None
    Draft202012Validator(schema("200")).validate(body)


@pytest.mark.parametrize(
    "body",
    [
        {"query": "", "today": "2026-11-18"},
        {"query": "   ", "today": "2026-11-18"},
        {"query": "가" * 201, "today": "2026-11-18"},
        {"query": "고양이", "today": "2026/11/18"},
        {"query": "고양이", "today": 20261118},
        {"query": "고양이", "today": "2026-11-18T09:00:00+09:00"},
        {"query": "고양이"},
        {"query": "고양이", "today": "2026-11-18", "studentName": "x"},
    ],
)
def test_invalid_request_is_400(body: dict) -> None:
    llm = FakeLlm()
    response = post(llm, body)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"
    assert llm.requests == []


def test_problems_have_codes_and_retryable() -> None:
    bad = post(FakeLlm(make(keywords=["가" * 21])))
    assert bad.status_code == 502
    assert bad.headers["content-type"] == "application/problem+json"
    assert (bad.json()["code"], bad.json()["retryable"]) == ("AI_BAD_RESPONSE", True)
    Draft202012Validator(schema("502", "application/problem+json")).validate(bad.json())
    down = post(FakeLlm(LlmError("LLM_TIMEOUT", retryable=True)))
    assert (down.status_code, down.json()["code"], down.json()["retryable"]) == (
        503,
        "AI_UNAVAILABLE",
        True,
    )
    Draft202012Validator(schema("503", "application/problem+json")).validate(down.json())


def test_only_learning_may_call() -> None:
    assert post(FakeLlm(GOOD), headers={}).status_code == 401
    assert caller_permits("learning", "/internal/memory-queries")
    for caller in ("core", "report-worker", "ops"):
        assert not caller_permits(caller, "/internal/memory-queries")
