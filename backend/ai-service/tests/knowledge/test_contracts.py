"""#464 지식 RAG 계약.

pydantic 모델(contracts.py)이 OpenAPI와 같고, 가짜 구현이 인터페이스대로 답한다.
"""

import asyncio
import typing
from pathlib import Path

import httpx
import pytest
import yaml
from pydantic import BaseModel

from app.knowledge import contracts as c
from app.knowledge import fake

ROOT = Path(__file__).resolve().parents[4]
LEARNING = yaml.safe_load(
    (ROOT / "contracts/openapi/learning-service.yaml").read_text(encoding="utf-8")
)
AI = yaml.safe_load((ROOT / "contracts/openapi/ai-service.yaml").read_text(encoding="utf-8"))

# OpenAPI 스키마 이름 → pydantic 모델
PAIRS = {
    "KnowledgeRef": c.KnowledgeRef,
    "KnowledgeContentItem": c.ContentItem,
    "KnowledgeStandard": c.StandardView,
    "KnowledgeDomain": c.DomainView,
    "KnowledgeContent": c.ContentView,
    "KnowledgeFit": c.FitView,
    "KnowledgeStandardBundle": c.StandardBundle,
    "KnowledgeSubjectGuide": c.SubjectGuideView,
    "KnowledgeThinkingTypeGuide": c.ThinkingTypeGuide,
    "KnowledgeBundle": c.KnowledgeBundle,
    "KnowledgeThinkingTypeResponse": c.ThinkingTypeResponse,
    "KnowledgeSearchFilters": c.SearchFilters,
    "KnowledgeSearchRequest": c.SearchRequest,
    "KnowledgeSearchHit": c.SearchHit,
    "KnowledgeSearchResponse": c.SearchResponse,
    "KnowledgeThemeCandidatesRequest": c.ThemeCandidatesRequest,
    "KnowledgeThemeCandidate": c.ThemeCandidate,
    "KnowledgeThemeTypeCandidates": c.ThemeTypeCandidates,
    "KnowledgeThemeCandidatesResponse": c.ThemeCandidatesResponse,
    "KnowledgeLearnedConcept": c.LearnedConcept,
    "KnowledgeLearnedRequest": c.LearnedRequest,
    "KnowledgeLearnedItem": c.LearnedItem,
    "KnowledgeLearnedResponse": c.LearnedResponse,
}
HEADERS = {"X-Internal-Token": "t", "X-User-Role": "SYSTEM"}


def aliases(model: type[BaseModel]) -> tuple[set[str], set[str]]:
    fields = model.model_fields
    names = {field.alias or name for name, field in fields.items()}
    required = {field.alias or name for name, field in fields.items() if field.is_required()}
    return names, required


@pytest.mark.parametrize("name", sorted(PAIRS))
def test_models_match_learning_openapi(name: str) -> None:
    schema = LEARNING["components"]["schemas"][name]
    names, required = aliases(PAIRS[name])
    assert set(schema["properties"]) == names
    # 응답 모델은 모든 칸이 필수(null 허용), 요청 모델은 기본값이 있는 칸만 선택
    assert set(schema.get("required", [])) == required


def test_embedding_models_match_ai_openapi() -> None:
    for name, model in (
        ("EmbeddingRequest", c.EmbeddingRequest),
        ("EmbeddingResponse", c.EmbeddingResponse),
    ):
        names, required = aliases(model)
        schema = AI["components"]["schemas"][name]
        assert set(schema["properties"]) == names
        assert set(schema["required"]) == required
    texts = AI["components"]["schemas"]["EmbeddingRequest"]["properties"]["texts"]
    assert texts["maxItems"] == c.EMBEDDING_MAX_TEXTS == fake.MAX_TEXTS
    assert texts["items"]["maxLength"] == c.EMBEDDING_MAX_CHARS == fake.MAX_CHARS
    assert c.EMBEDDING_DIMENSIONS == fake.DIMENSIONS == 1536


def test_literals_match_openapi_enums() -> None:
    schemas = LEARNING["components"]["schemas"]
    assert list(typing.get_args(c.FallbackReason)) == schemas["KnowledgeFallbackReason"]["enum"]
    assert (
        list(typing.get_args(c.KnowledgeKind))
        == schemas["KnowledgeKind"]["enum"]
        == list(fake.KINDS)
    )
    assert (
        list(typing.get_args(c.Subject))
        == schemas["KnowledgeSubject"]["enum"]
        == list(fake.SUBJECTS)
    )
    assert set(typing.get_args(c.FallbackReason)) < set(typing.get_args(c.RetrievalFallback))
    request = schemas["KnowledgeSearchRequest"]["properties"]
    assert request["k"]["maximum"] == c.SEARCH_MAX_K == fake.MAX_K
    assert (
        request["minSimilarity"]["default"]
        == c.DEFAULT_MIN_SIMILARITY
        == fake.DEFAULT_MIN_SIMILARITY
    )
    learned = schemas["KnowledgeLearnedRequest"]["properties"]["concepts"]
    assert learned["maxItems"] == c.LEARNED_MAX_CONCEPTS == fake.MAX_CONCEPTS


def test_fake_answers_through_protocols() -> None:
    api_fake = fake.FakeKnowledgeApi()
    api: c.KnowledgeApi = api_fake.as_knowledge_api()
    embedder: c.Embedder = api_fake.embedder.as_embedder()

    async def run() -> None:
        embedded = await embedder.embed(["자연수의 곱셈과 나눗셈"])
        assert isinstance(embedded, c.EmbeddingResponse)
        bundle = await api.standards(["4수01-06"], 3, "SOLVE")
        assert isinstance(bundle, c.KnowledgeBundle)
        assert bundle.items[0].standard.code == "4수01-06"
        refs = c.sources_of(bundle)
        assert refs[0] == c.KnowledgeRef(
            kind="STANDARD", id="4수01-06", dataset_version=api_fake.version
        )
        assert len({(r.kind, r.id) for r in refs}) == len(refs)
        assert refs[-1].kind == "THINKING_TYPE"
        search = await api.search(
            c.SearchRequest(
                vector=embedded.vectors[0], embedding_model=embedded.model, min_similarity=0.2
            )
        )
        assert search.items and search.reason is None
        theme = await api.theme_candidates(
            c.ThemeCandidatesRequest(
                vector=embedded.vectors[0], embedding_model=embedded.model, grade=3, semester="3-1"
            )
        )
        assert [t.thinking_type for t in theme.types] == list(fake.THINKING_TYPES)
        learned = await api.learned(
            c.LearnedRequest(
                concepts=[
                    c.LearnedConcept(text="자연수의 곱셈과 나눗셈", vector=embedded.vectors[0])
                ],
                embedding_model=embedded.model,
                grade=3,
                semester="3-1",
                min_similarity=0.5,
            )
        )
        assert learned.items[0].verdict == "LEARNED"
        guide = await api.thinking_type("REFLECT")
        assert guide.guide is not None and guide.guide.type == "REFLECT"

    asyncio.run(run())


def test_mission_draft_knowledge_is_standards_response() -> None:
    """C7: knowledge 칸은 C5 standards 응답 그대로라 같은 모델로 읽힌다."""
    body = fake.FakeKnowledgeApi().standards_sync(["4국02-04"], 3, "EVALUATE")
    bundle = c.KnowledgeBundle.model_validate(body)
    assert bundle.model_dump(by_alias=True) == body
    knowledge = AI["components"]["schemas"]["MissionDraftRequest"]["properties"]["knowledge"]
    assert {"$ref": "#/components/schemas/KnowledgeBundle"} in knowledge["anyOf"]


def test_mock_transport_and_server_speak_http() -> None:
    async def run() -> None:
        transport = fake.mock_transport()
        async with httpx.AsyncClient(transport=transport, base_url="http://fake") as client:
            embedded = await client.post(
                "/internal/embeddings", json={"texts": ["나눗셈"]}, headers=HEADERS
            )
            assert embedded.status_code == 200
            vector = c.EmbeddingResponse.model_validate(embedded.json()).vectors[0]
            response = await client.post(
                "/internal/knowledge/search",
                json={"vector": vector, "embeddingModel": "fake-bigram-v1", "minSimilarity": 0.1},
                headers=HEADERS,
            )
            assert response.status_code == 200
            c.SearchResponse.model_validate(response.json())
            standards = await client.get(
                "/internal/knowledge/standards", params={"codes": "4과02-01"}, headers=HEADERS
            )
            assert c.KnowledgeBundle.model_validate(standards.json()).items[0].covers
            denied = await client.get("/internal/knowledge/thinking-types/SOLVE")
            assert denied.status_code == 401
            assert denied.headers["content-type"] == "application/problem+json"

    asyncio.run(run())
    server = fake.serve()
    try:
        port = server.server_address[1]
        with httpx.Client(base_url=f"http://127.0.0.1:{port}") as client:
            response = client.get("/internal/knowledge/thinking-types/ANALYZE", headers=HEADERS)
            assert response.status_code == 200
            assert c.ThinkingTypeResponse.model_validate(response.json()).guide is not None
            bad = client.post("/internal/embeddings", json={"texts": []}, headers=HEADERS)
            assert bad.status_code == 400 and bad.json()["code"] == "VALIDATION_FAILED"
    finally:
        server.shutdown()


def test_retrieval_result_carries_fallback() -> None:
    empty: c.RetrievalResult[c.KnowledgeBundle] = c.RetrievalResult(
        value=None, fallback="KNOWLEDGE_TIMEOUT"
    )
    assert empty.value is None and empty.fallback == "KNOWLEDGE_TIMEOUT"
