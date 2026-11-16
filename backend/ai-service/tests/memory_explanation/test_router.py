"""POST /internal/memory-explanations (#565, api-spec 4.2.6)."""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.bootstrap import create_app
from app.llm.base import LlmError
from app.llm.providers import get_llm
from tests.fakes import FakeLlm
from tests.memory_explanation.test_service import BODY, EVIDENCE, GOOD, with_second

HEADERS = {"X-Internal-Token": "test-token"}
OPENAPI = Path(__file__).resolve().parents[4] / "contracts/openapi/ai-service.yaml"


def post(llm: FakeLlm, body: object = BODY, headers: dict[str, str] = HEADERS):
    app = create_app()
    app.dependency_overrides[get_llm] = lambda: llm
    with TestClient(app) as client:
        return client.post("/internal/memory-explanations", json=body, headers=headers)


def operation() -> tuple[dict, dict]:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    return spec["paths"]["/memory-explanations"]["post"], spec["components"]


def schema(status: str, media: str = "application/json") -> dict:
    op, components = operation()
    return {**op["responses"][status]["content"][media]["schema"], "components": components}


def test_response_is_camel_case_and_matches_openapi() -> None:
    response = post(FakeLlm(GOOD))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"text", "citations", "versions"}
    assert body["citations"] == [1]
    assert body["versions"] == {"model": "fake-model", "prompt": "memory-explanation@1"}
    Draft202012Validator(schema("200")).validate(body)
    op, components = operation()
    assert "x-implementation-status" not in op
    request = {**op["requestBody"]["content"]["application/json"]["schema"]}
    Draft202012Validator({**request, "components": components}).validate(BODY)


@pytest.mark.parametrize(
    "body",
    [
        {"query": "q", "evidence": []},
        {"query": "q", "evidence": [EVIDENCE[0]] * 2},  # 번호 겹침
        {"query": "q", "evidence": [{**EVIDENCE[0], "no": 4}]},
        {"query": "q", "evidence": [*EVIDENCE, {**EVIDENCE[0], "no": 3}, {**EVIDENCE[0], "no": 4}]},
        {"query": "   ", "evidence": EVIDENCE},
        {"query": "가" * 201, "evidence": EVIDENCE},
        {"query": "q", "evidence": [{**EVIDENCE[0], "answerExcerpt": " "}]},
        {"query": "q", "evidence": [{**EVIDENCE[0], "studentName": "x"}]},
        {"query": "q"},
    ],
)
def test_invalid_request_is_400(body: dict) -> None:
    response = post(FakeLlm(), body)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_problems_have_codes_and_retryable() -> None:
    rejected = post(FakeLlm(with_second([3])))
    assert rejected.status_code == 422
    assert rejected.headers["content-type"] == "application/problem+json"
    assert (rejected.json()["code"], rejected.json()["retryable"]) == (
        "AI_EXPLANATION_REJECTED",
        False,
    )
    Draft202012Validator(schema("422", "application/problem+json")).validate(rejected.json())
    one = GOOD.model_copy(update={"sentences": GOOD.sentences[:1]})
    bad = post(FakeLlm(one))
    assert (bad.status_code, bad.json()["code"], bad.json()["retryable"]) == (
        502,
        "AI_BAD_RESPONSE",
        True,
    )
    timeout = LlmError("LLM_TIMEOUT", retryable=True)
    down = post(FakeLlm(timeout, timeout))
    assert (down.status_code, down.json()["code"], down.json()["retryable"]) == (
        503,
        "AI_UNAVAILABLE",
        True,
    )


def test_missing_internal_token_is_401() -> None:
    assert post(FakeLlm(GOOD), headers={}).status_code == 401
