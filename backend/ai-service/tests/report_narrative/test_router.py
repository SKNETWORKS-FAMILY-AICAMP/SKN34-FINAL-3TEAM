from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.llm.base import LlmError
from app.llm.providers import get_llm
from app.report_narrative.prompts import CitedQuote, GeneratedNarrative
from tests.fakes import FakeLlm
from tests.report_narrative.test_service import BODY

HEADERS = {"X-Internal-Token": "test-token"}


def post(llm: FakeLlm, headers: dict[str, str] = HEADERS, body: dict = BODY):
    app = create_app()
    app.dependency_overrides[get_llm] = lambda: llm
    with TestClient(app) as client:
        return client.post("/internal/report-narratives", json=body, headers=headers)


def test_response_uses_camel_case() -> None:
    llm = FakeLlm(
        GeneratedNarrative(
            narrative='아이는 "나는 반대야."라고 썼어요.',
            evening_question="오늘 뭐 했어?",
            cited_quotes=[CitedQuote(candidate=2, quote="나는 반대야.")],
        )
    )
    response = post(llm)
    assert response.status_code == 200
    assert response.json() == {
        "narrative": {
            "text": '아이는 "나는 반대야."라고 썼어요.',
            "source": "LLM",
            "modelExplanation": None,
        },
        "eveningQuestion": "오늘 뭐 했어?",
        "citedQuotes": [
            {"attemptId": "t-9", "answerId": "a-201", "answerVersion": 1, "quote": "나는 반대야."}
        ],
        "versions": {"model": "fake-model", "prompt": "report@1"},
    }


def test_missing_internal_token_is_401() -> None:
    assert post(FakeLlm(), headers={}).status_code == 401


def test_missing_field_is_400() -> None:
    body = {key: value for key, value in BODY.items() if key != "quotes"}
    assert post(FakeLlm(), body=body).status_code == 400


def test_quote_without_answer_version_is_400() -> None:
    quotes = [{key: v for key, v in BODY["quotes"][1].items() if key != "answerVersion"}]
    assert post(FakeLlm(), body={**BODY, "quotes": quotes}).status_code == 400


def test_llm_failure_is_503_problem_with_retryable() -> None:
    response = post(FakeLlm(LlmError("LLM_SERVER_ERROR", retryable=True)))
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert (response.json()["code"], response.json()["retryable"]) == ("AI_UNAVAILABLE", True)
