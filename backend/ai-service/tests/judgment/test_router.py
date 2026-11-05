import httpx
import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.clients.scoring_client import ScoringClient
from app.config import get_settings
from app.judgment.extractor import Extraction
from app.judgment.router import get_scoring
from app.llm.base import LlmError
from app.llm.providers import get_llm
from tests.fakes import FakeLlm

HEADERS = {"X-Internal-Token": "test-token"}
BODY = {
    "answerText": "나는 찬성해. 쉬는 시간이 길면 더 잘 놀 수 있어.",
    "inputType": "ESSAY",
    "grade": 5,
    "rubric": {
        "elements": [
            {
                "elementId": "e1",
                "label": "주장",
                "description": "자기 주장",
                "points": 1,
                "judgeVerified": False,
            }
        ]
    },
    "versions": {"mission": "m-1@1", "rubric": "r-1@1"},
}


def post(llm: FakeLlm, headers: dict[str, str] = HEADERS, body: dict = BODY):
    app = create_app()
    app.dependency_overrides[get_llm] = lambda: llm
    with TestClient(app) as client:
        return client.post("/internal/judgments", json=body, headers=headers)


def test_judgment_response_uses_camel_case() -> None:
    llm = FakeLlm(
        Extraction.model_validate(
            {"elements": [{"elementId": "e1", "status": "FOUND", "quote": "나는 찬성해"}]}
        )
    )
    response = post(llm)
    assert response.status_code == 200
    assert response.json() == {
        "result": "CORRECT",
        "elements": [
            {"elementId": "e1", "quote": "나는 찬성해", "verified": True, "satisfied": True}
        ],
        "heldReason": None,
        "trial": True,
        "versions": {
            "mission": "m-1@1",
            "rubric": "r-1@1",
            "model": "fake-model",
            "prompt": "judge@2",
        },
        "modelScores": None,
    }


def test_llm_failure_is_503_problem_with_retryable() -> None:
    response = post(FakeLlm(LlmError("LLM_SERVER_ERROR", retryable=True)))
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert (response.json()["code"], response.json()["retryable"]) == ("AI_UNAVAILABLE", True)


def test_missing_internal_token_is_401() -> None:
    assert post(FakeLlm(), headers={}).status_code == 401


def test_choice_input_is_rejected() -> None:
    response = post(FakeLlm(), body={**BODY, "inputType": "CHOICE"})
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


def found_e1() -> FakeLlm:
    return FakeLlm(
        Extraction.model_validate(
            {"elements": [{"elementId": "e1", "status": "FOUND", "quote": "나는 찬성해"}]}
        )
    )


def post_with_scoring(handler, monkeypatch, enabled: bool = True):
    """실제 ScoringClient에 scoring 응답 대역을 꽂아 판정 HTTP 응답 확인 (#305)."""
    monkeypatch.setenv("M2_CROSS_CHECK_ENABLED", str(enabled).lower())
    calls: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    scoring = ScoringClient(
        httpx.AsyncClient(base_url="http://scoring", transport=httpx.MockTransport(record))
    )
    app = create_app()
    app.dependency_overrides[get_llm] = found_e1
    app.dependency_overrides[get_scoring] = lambda: scoring
    with TestClient(app) as client:
        body = {**BODY, "question": "쉬는 시간을 늘릴까요?", "essayType": "주장"}
        return client.post("/internal/judgments", json=body, headers=HEADERS), calls


def timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("scoring 응답 없음", request=request)


@pytest.fixture(autouse=True)
def fresh_settings():
    # get_settings는 lru_cache라 테스트마다 환경 변수를 다시 읽게 비움
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("handler", "skipped"),
    [
        (
            lambda _: httpx.Response(503, json={"code": "SCORING_UNAVAILABLE"}),
            "SCORING_UNAVAILABLE",
        ),
        (lambda _: httpx.Response(500), "SCORING_UNAVAILABLE"),
        (timeout, "SCORING_UNAVAILABLE"),
        (lambda _: httpx.Response(400, json={"code": "VALIDATION_FAILED"}), "SCORING_REJECTED"),
    ],
)
def test_scoring_failure_is_200_with_cross_check_skipped(handler, skipped, monkeypatch) -> None:
    # ai가 200을 돌려주므로 learning ai 서킷(5xx·전송 오류만 실패)에 집계되지 않음
    response, calls = post_with_scoring(handler, monkeypatch)
    assert len(calls) == 1
    assert response.status_code == 200
    body = response.json()
    assert (body["result"], body["heldReason"]) == ("CORRECT", None)
    assert body["versions"]["model"] == "fake-model"
    assert body["modelScores"] == {"m2": None, "m1": None, "skipped": skipped}


def test_cross_check_disabled_does_not_call_scoring(monkeypatch) -> None:
    response, calls = post_with_scoring(lambda _: httpx.Response(500), monkeypatch, enabled=False)
    assert calls == []
    assert response.status_code == 200
    assert response.json()["modelScores"] is None
