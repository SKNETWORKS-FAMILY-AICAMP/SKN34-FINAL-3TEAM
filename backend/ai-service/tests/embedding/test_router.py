"""POST /internal/embeddings (#467, api-spec 4.2.4 계약 C6)."""

import asyncio
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.bootstrap import create_app
from app.config import get_settings
from app.embedding.service import EmbeddingService
from app.knowledge.contracts import (
    EMBEDDING_MAX_CHARS,
    EMBEDDING_MAX_TEXTS,
    Embedder,
    EmbeddingResponse,
)
from app.knowledge.fake import fake_vector
from app.llm.base import LlmError
from app.llm.embeddings import (
    EmbeddingClient,
    FakeEmbeddingClient,
    ProviderEmbeddings,
    get_embedder,
)

HEADERS = {"X-Internal-Token": "test-token"}
OPENAPI = Path(__file__).resolve().parents[4] / "contracts/openapi/ai-service.yaml"


class ScriptedClient(EmbeddingClient):
    def __init__(self, *steps: ProviderEmbeddings | LlmError, dimensions: int = 3) -> None:
        super().__init__(
            model="m",
            dimensions=dimensions,
            max_retries=0,
            backoff_seconds=0,
            timeout=1,
            recorder=None,
        )
        self.steps = list(steps)

    async def _request(self, texts: list[str], timeout: float) -> ProviderEmbeddings:
        step = self.steps.pop(0)
        if isinstance(step, LlmError):
            raise step
        return step


def post(client: EmbeddingClient, body: object, headers: dict[str, str] = HEADERS):
    app = create_app()
    app.dependency_overrides[get_embedder] = lambda: client
    with TestClient(app) as http:
        return http.post("/internal/embeddings", json=body, headers=headers)


def test_returns_model_dimensions_and_vectors_in_order() -> None:
    response = post(FakeEmbeddingClient(8), {"texts": ["첫째 글", "둘째 글"]})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"model", "dimensions", "vectors"}
    assert (body["model"], body["dimensions"]) == ("fake-bigram-v1", 8)
    assert body["vectors"] == [fake_vector("첫째 글", 8), fake_vector("둘째 글", 8)]


def test_missing_internal_token_is_401() -> None:
    assert post(FakeEmbeddingClient(8), {"texts": ["a"]}, headers={}).status_code == 401


def test_limits_are_400() -> None:
    client = FakeEmbeddingClient(8)
    too_many = {"texts": ["a"] * (EMBEDDING_MAX_TEXTS + 1)}
    too_long = {"texts": ["가" * (EMBEDDING_MAX_CHARS + 1)]}
    for body in (
        {"texts": []},
        too_many,
        too_long,
        {"texts": [""]},
        {"texts": [" \n"]},
        {},
        {"texts": ["a"], "x": 1},
    ):
        response = post(client, body)
        assert response.status_code == 400, body
        assert response.json()["code"] == "VALIDATION_FAILED"
    assert post(client, {"texts": ["a"] * EMBEDDING_MAX_TEXTS}).status_code == 200
    assert post(client, {"texts": ["가" * EMBEDDING_MAX_CHARS]}).status_code == 200


def test_bad_provider_response_is_502_and_failure_is_503() -> None:
    bad = post(ScriptedClient(ProviderEmbeddings("m", [[0.1, 0.2]], 3)), {"texts": ["a"]})
    assert bad.status_code == 502
    assert bad.headers["content-type"] == "application/problem+json"
    assert (bad.json()["code"], bad.json()["retryable"]) == ("AI_BAD_RESPONSE", True)
    down = post(ScriptedClient(LlmError("LLM_TIMEOUT", retryable=True)), {"texts": ["a"]})
    assert down.status_code == 503
    assert (down.json()["code"], down.json()["retryable"]) == ("AI_UNAVAILABLE", True)
    auth = post(ScriptedClient(LlmError("LLM_AUTH_FAILED", retryable=False)), {"texts": ["a"]})
    assert (auth.status_code, auth.json()["retryable"]) == (503, False)


def test_unconfigured_default_app_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as http:
        response = http.post("/internal/embeddings", json={"texts": ["a"]}, headers=HEADERS)
    get_settings.cache_clear()
    assert (response.status_code, response.json()["retryable"]) == (503, False)


def test_service_satisfies_embedder_protocol() -> None:
    service: Embedder = EmbeddingService(FakeEmbeddingClient(8))
    result = asyncio.run(service.embed(["질의"]))
    assert isinstance(result, EmbeddingResponse)
    assert result.vectors == [fake_vector("질의", 8)]


def test_response_matches_openapi_contract() -> None:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    operation = spec["paths"]["/embeddings"]["post"]
    schema = {
        **operation["responses"]["200"]["content"]["application/json"]["schema"],
        "components": spec["components"],
    }
    body = post(FakeEmbeddingClient(8), {"texts": ["a", "b"]}).json()
    Draft202012Validator(schema).validate(body)
    assert "x-implementation-status" not in operation
