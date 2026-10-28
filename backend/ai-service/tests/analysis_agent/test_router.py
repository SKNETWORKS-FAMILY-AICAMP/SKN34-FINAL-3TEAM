"""분석 대화 그래프 경로별 SSE 결과 (가짜 LLM·가짜 learning)."""

import json

from fastapi.testclient import TestClient

from app.analysis_agent.prompts import AnswerDraft, Citation, Classification
from app.analysis_agent.records import RecordsUnavailable
from app.analysis_agent.router import get_learning_records
from app.bootstrap import create_app
from app.llm.base import LlmError
from app.llm.providers import get_llm
from tests.analysis_agent.records_fixture import FakeRecords
from tests.fakes import FakeLlm

HEADERS = {
    "X-Internal-Token": "test-token",
    "X-User-Id": "p-1",
    "X-User-Role": "PARENT",
    "X-Student-Scope": "s-1",
}
BODY = {
    "conversationId": "c-1",
    "question": "질문을 받고 뭐가 달라졌어?",
    "scope": {"studentId": "s-1", "from": "2026-10-20", "to": "2026-10-26"},
    "history": [],
}


def classified(intent: str, issue: str = "NONE") -> Classification:
    return Classification(intent=intent, scope_issue=issue)


def post(llm: FakeLlm, records: FakeRecords | None = None, body: dict = BODY, headers=HEADERS):
    app = create_app()
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_learning_records] = lambda: records or FakeRecords()
    with TestClient(app) as client:
        return client.post("/internal/analysis/stream", json=body, headers=headers)


def events(response) -> list[tuple[str, dict]]:
    parsed = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        parsed.append((lines["event"], json.loads(lines["data"])))
    return parsed


def test_verified_llm_answer() -> None:
    draft = AnswerDraft(
        answer=(
            "3개 시도 중 1개에서 되묻기 뒤에 답을 다시 썼어요. "
            "“왜냐하면 쉬는 시간이 길면”이라는 까닭을 더했어요."
        ),
        citations=[Citation(source_id="S2", quote="왜냐하면 쉬는 시간이 길면")],
    )
    llm = FakeLlm(classified("CHANGES"), draft)
    records = FakeRecords()
    response = post(llm, records)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    names = [name for name, _ in events(response)]
    assert names[-2:] == ["result", "done"]
    assert "status" in names
    assert records.closed  # 질문이 끝나면 learning 연결을 닫음
    result = events(response)[-2][1]
    assert result["source"] == "LLM"
    assert result["fallback"] is None
    assert result["recordCount"] == 3
    assert result["scope"] == {"childId": "s-1", "from": "2026-10-20", "to": "2026-10-26"}
    assert result["verification"] == {
        "numbersMatched": True,
        "quotesMatched": True,
        "contentAllowed": True,
    }
    assert result["evidence"][0]["answerId"] == "a-2"
    assert result["versions"] == {"model": "fake-model", "prompt": "analysis@1"}
    assert [r.call_type for r in llm.requests] == ["ANALYSIS", "ANALYSIS"]


def test_scope_conflict_ends_with_clarification_without_records() -> None:
    records = FakeRecords()
    response = post(FakeLlm(classified("COUNT", "DIFFERENT_PERIOD")), records)
    last_name, last = events(response)[-1]
    assert last_name == "clarification"
    assert last["reason"] == "DIFFERENT_PERIOD"
    assert last["current"]["childId"] == "s-1"
    assert records.calls == []  # 범위를 임의로 정해 조회하지 않음


def test_verification_failure_falls_back_to_template() -> None:
    draft = AnswerDraft(answer="7개 시도에서 답을 바꿨어요.", citations=[])
    response = post(FakeLlm(classified("CHANGES"), draft))
    result = events(response)[-2][1]
    assert result["source"] == "TEMPLATE"
    assert result["fallback"] == {"reason": "VERIFICATION_FAILED"}
    assert result["verification"]["numbersMatched"] is False
    assert "7개" not in result["answer"]  # LLM 문장은 버림
    assert "글자 수가 늘어난 시도: 1개 중 1개" in result["answer"]
    assert "학습한 활동: 3개" in result["answer"]


def test_llm_unavailable_falls_back_to_template() -> None:
    llm = FakeLlm(LlmError("LLM_SERVER_ERROR", retryable=True))
    result = events(post(llm))[-2][1]
    assert result["source"] == "TEMPLATE"
    assert result["fallback"] == {"reason": "AI_UNAVAILABLE"}
    assert result["verification"] is None
    assert result["metrics"][0]["count"] == 3


def test_answer_llm_failure_falls_back_to_template() -> None:
    llm = FakeLlm(classified("CHILD_THOUGHTS"), LlmError("LLM_TIMEOUT", retryable=True))
    result = events(post(llm))[-2][1]
    assert result["fallback"] == {"reason": "AI_UNAVAILABLE"}
    assert len(result["evidence"]) == 3


def test_no_records_is_guidance_not_failure() -> None:
    llm = FakeLlm(classified("CHANGES"))
    result = events(post(llm, FakeRecords(empty=True)))[-2][1]
    assert result["source"] == "TEMPLATE"
    assert result["fallback"] is None
    assert result["recordCount"] == 0
    assert "분석할 기록이 없어요" in result["answer"]
    assert len(llm.requests) == 1  # 답변 LLM 호출 없음


def test_unsupported_intent_guides_available_questions() -> None:
    result = events(post(FakeLlm(classified("MATH_CHECK"))))[-2][1]
    assert "수학 풀이 점검은 아직" in result["answer"]
    assert result["recordCount"] == 3


def test_record_failure_is_error_not_empty_answer() -> None:
    records = FakeRecords(fail=RecordsUnavailable("RECORDS_UNAVAILABLE", retryable=True))
    parsed = events(post(FakeLlm(classified("COUNT")), records))
    assert [name for name, _ in parsed][-1] == "error"
    assert parsed[-1][1] == {
        "code": "RECORDS_UNAVAILABLE",
        "message": "기록을 불러오지 못했어요. 잠시 뒤 다시 물어봐 주세요.",
        "retryable": True,
    }
    assert "result" not in [name for name, _ in parsed]


def test_tools_use_confirmed_scope_only() -> None:
    records = FakeRecords()
    post(
        FakeLlm(
            classified("THINKING_TYPES"), AnswerDraft(answer="3개 시도를 했어요.", citations=[])
        ),
        records,
    )
    assert {name for name, _ in records.calls} == {"summary", "thinking_types"}
    assert all(scope.student_id == "s-1" for _, scope in records.calls)


def test_other_child_is_forbidden_before_streaming() -> None:
    headers = {**HEADERS, "X-Student-Scope": "s-2"}
    response = post(FakeLlm(), headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_invalid_period_is_validation_error() -> None:
    body = {**BODY, "scope": {"studentId": "s-1", "from": "2026-10-27", "to": "2026-10-20"}}
    assert post(FakeLlm(), body=body).status_code == 400
