"""분석 대화 그래프 경로별 SSE 결과 (가짜 LLM·가짜 learning)."""

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.analysis_agent.models import AnalysisRequest
from app.analysis_agent.prompts import Classification
from app.analysis_agent.router import _events, get_record_tools
from app.analysis_agent.state import AgentContext
from app.bootstrap import create_app
from app.clients.learning_client import RecordsUnavailable
from app.llm.base import LlmError
from app.llm.providers import get_llm
from app.versions import ActiveVersions
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
    app.dependency_overrides[get_record_tools] = lambda: records or FakeRecords()
    with TestClient(app) as client:
        return client.post("/internal/analysis/stream", json=body, headers=headers)


def events(response) -> list[tuple[str, dict]]:
    parsed = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        parsed.append((lines["event"], json.loads(lines["data"])))
    return parsed


def test_verified_llm_answer() -> None:
    draft = (
        "3개 시도 중 1개에서 되묻기 뒤에 답을 다시 썼어요. "
        "“왜냐하면 쉬는 시간이 길면”이라는 까닭을 더했어요."
    )
    llm = FakeLlm(classified("CHANGES"), draft)
    records = FakeRecords()
    response = post(llm, records)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    parsed = events(response)
    names = [name for name, _ in parsed]
    # status → delta → result → done (API 3.3)
    first_delta = names.index("delta")
    assert set(names[:first_delta]) == {"status"}
    assert names[-2:] == ["result", "done"]
    assert set(names[first_delta:-2]) <= {"delta", "status"}
    assert records.closed  # 질문이 끝나면 learning 연결을 닫음
    result = parsed[-2][1]
    deltas = "".join(data["text"] for name, data in parsed if name == "delta")
    assert deltas.strip() == result["answer"]
    assert result["source"] == "LLM"
    assert result["fallback"] is None
    assert result["recordCount"] == 3
    assert result["scope"] == {"childId": "s-1", "from": "2026-10-20", "to": "2026-10-26"}
    assert result["verification"] == {
        "numbersMatched": True,
        "quotesMatched": True,
        "contentAllowed": True,
    }
    assert [(e["kind"], e["answerId"]) for e in result["evidence"]] == [("ANSWER", "a-2")]
    assert result["versions"] == {"model": "fake-model", "prompt": "analysis@2"}
    assert [r.call_type for r in llm.requests] == ["ANALYSIS", "ANALYSIS"]
    assert len(llm.usages) == 2  # 노드별 LLM 호출마다 사용량 1건


def test_llm_requests_have_no_student_id() -> None:
    # 학생 이름·ID를 LLM에 보내지 않음 (API 4.2, NFR-SEC-03)
    body = {**BODY, "scope": {**BODY["scope"], "studentId": "s-unique-7"}}
    headers = {**HEADERS, "X-Student-Scope": "s-unique-7"}
    llm = FakeLlm(classified("CHILD_THOUGHTS"), "3개 시도를 했어요.")
    post(llm, FakeRecords(), body=body, headers=headers)
    assert len(llm.requests) == 2
    assert all("s-unique-7" not in r.system + r.user for r in llm.requests)
    assert all(i not in r.user for r in llm.requests for i in ("t-1", "a-2"))  # 시도·답변 ID도


def test_reflection_evidence_is_identified_by_attempt() -> None:
    draft = "1개 활동에 돌아보기를 썼고, “근거 찾기가 어려웠어”라고 했어요."
    records = FakeRecords()
    result = events(post(FakeLlm(classified("REFLECTIONS"), draft), records))[-2][1]
    assert result["source"] == "LLM"
    assert result["evidence"] == [
        {
            "kind": "REFLECTION",
            "attemptId": "t-1",
            "missionTitle": "쉬는 시간 토론",
            "answerId": None,
            "answerVersion": None,
            "submittedAt": "2026-10-22T19:30:00+09:00",  # 돌아보기 작성 시각
            "quote": "근거 찾기가 어려웠어",
            "available": True,
        }
    ]
    assert {name for name, _ in records.calls} == {"summary", "attempts"}
    assert records.attempts_size is None  # 돌아보기 수를 세므로 모든 페이지


def test_scope_conflict_ends_with_clarification_without_records() -> None:
    records = FakeRecords()
    response = post(FakeLlm(classified("COUNT", "DIFFERENT_PERIOD")), records)
    last_name, last = events(response)[-1]
    assert last_name == "clarification"
    assert last["reason"] == "DIFFERENT_PERIOD"
    assert last["current"]["childId"] == "s-1"
    assert records.calls == []  # 범위를 임의로 정해 조회하지 않음


def test_verification_failure_falls_back_to_template() -> None:
    parsed = events(post(FakeLlm(classified("CHANGES"), "7개 시도에서 답을 바꿨어요.")))
    assert "delta" in [name for name, _ in parsed]  # 임시 텍스트는 이미 보냈지만 확정하지 않음
    result = parsed[-2][1]
    assert result["source"] == "TEMPLATE"
    assert result["fallback"]["reason"] == "VERIFICATION_FAILED"
    assert result["fallback"]["draftVerification"]["numbersMatched"] is False
    assert all(result["verification"].values())
    assert "7개" not in result["answer"]  # LLM 문장은 버림
    assert "글자 수가 늘어난 시도: 1개 중 1개" in result["answer"]
    assert "학습한 활동: 3개" in result["answer"]


def test_llm_unavailable_falls_back_to_template() -> None:
    llm = FakeLlm(LlmError("LLM_SERVER_ERROR", retryable=True))
    result = events(post(llm))[-2][1]
    assert result["source"] == "TEMPLATE"
    assert result["fallback"] == {"reason": "AI_UNAVAILABLE", "draftVerification": None}
    assert all(result["verification"].values())
    assert result["metrics"][0]["count"] == 3


def test_answer_llm_failure_falls_back_to_template() -> None:
    llm = FakeLlm(classified("CHILD_THOUGHTS"), LlmError("LLM_TIMEOUT", retryable=True))
    result = events(post(llm))[-2][1]
    assert result["fallback"] == {"reason": "AI_UNAVAILABLE", "draftVerification": None}
    assert len(result["evidence"]) == 3
    assert {e["kind"] for e in result["evidence"]} == {"ANSWER"}


def test_stream_failure_before_first_token_is_retried() -> None:
    llm = FakeLlm(
        classified("THINKING_TYPES"),
        LlmError("LLM_SERVER_ERROR", retryable=True),
        "3개 시도를 했어요.",
        max_retries=1,
    )
    result = events(post(llm))[-2][1]
    assert result["source"] == "LLM"
    assert len(llm.requests) == 3


def test_stream_failure_after_first_token_is_not_retried() -> None:
    llm = FakeLlm(
        classified("THINKING_TYPES"),
        ["3개 시도", LlmError("LLM_CONNECTION", retryable=True)],
        "3개 시도를 했어요.",
        max_retries=1,
    )
    parsed = events(post(llm))
    result = parsed[-2][1]
    assert [data["text"] for name, data in parsed if name == "delta"] == ["3개 시도"]
    assert result["source"] == "TEMPLATE"
    assert result["fallback"] == {"reason": "AI_UNAVAILABLE", "draftVerification": None}
    assert len(llm.requests) == 2  # 보낸 조각이 있으면 다시 요청하지 않음


def test_cancelled_stream_stops_graph_and_llm() -> None:
    # core가 연결을 끊으면 Starlette가 응답 생성기를 취소함 (ASGI 2.3 disconnect 감지)
    llm = FakeLlm(classified("CHANGES"), ["답을 다시 썼어요. "] * 20, delay=0.01)
    records = FakeRecords()
    context = AgentContext(
        llm=llm,
        tools=records,
        deadline=time.monotonic() + 60,
        prompt=ActiveVersions().prompt("analysis"),
    )  # type: ignore[arg-type]
    seen: list[str] = []

    async def scenario() -> None:
        first_delta = asyncio.Event()

        async def consume() -> None:
            async for event in _events(AnalysisRequest.model_validate(BODY), context):
                seen.append(event.split("\n", 1)[0])
                if event.startswith("event: delta"):
                    first_delta.set()

        task = asyncio.create_task(consume())
        await first_delta.wait()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0.1)  # 취소가 안 됐다면 이 사이에 조각·호출이 더 생김

    asyncio.run(scenario())
    assert seen[-1] == "event: delta"
    assert seen.count("event: delta") < 20  # 남은 조각을 받지 않음
    assert len(llm.requests) == 2  # 이후 LLM 호출 없음
    assert len(llm.usages) == 1  # 답변 스트림은 끝나지 않음 (classify만 완료)
    assert records.closed


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
        FakeLlm(classified("THINKING_TYPES"), "3개 시도를 했어요."),
        records,
    )
    assert {name for name, _ in records.calls} == {"summary", "thinking_types"}
    assert all(scope.student_id == "s-1" for _, scope in records.calls)


def test_missing_internal_token_is_unauthorized() -> None:
    headers = {k: v for k, v in HEADERS.items() if k != "X-Internal-Token"}
    llm = FakeLlm()
    response = post(llm, headers=headers)
    assert response.status_code == 401
    assert llm.requests == []


def test_other_child_is_forbidden_before_streaming() -> None:
    headers = {**HEADERS, "X-Student-Scope": "s-2"}
    response = post(FakeLlm(), headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_invalid_period_is_validation_error() -> None:
    body = {**BODY, "scope": {"studentId": "s-1", "from": "2026-10-27", "to": "2026-10-20"}}
    assert post(FakeLlm(), body=body).status_code == 400


@pytest.mark.parametrize(
    "intent,reason",
    [
        ("CHANGES", "NO_CHANGES"),
        ("REFLECTIONS", "NO_REFLECTIONS"),
        ("OTHER", "UNSUPPORTED"),
        ("MATH_CHECK", "MATH_CHECK"),
    ],
)
def test_notices_have_verified_final_text_and_no_failure(intent, reason):
    records = FakeRecords()
    if intent == "CHANGES":
        records._records.changes = []
    elif intent == "REFLECTIONS":
        for attempt in records._records.attempts:
            attempt.reflection = None
    result = events(post(FakeLlm(classified(intent)), records))[-2][1]
    assert result["source"] == "TEMPLATE"
    assert result["notice"] == {"reason": reason}
    assert result["fallback"] is None
    assert all(result["verification"].values())


def test_no_record_notice_is_verified():
    result = events(post(FakeLlm(classified("COUNT")), FakeRecords(empty=True)))[-2][1]
    assert result["notice"] == {"reason": "NO_RECORD"}
    assert all(result["verification"].values())


def test_llm_failure_is_preserved_even_when_records_are_empty():
    result = events(
        post(FakeLlm(LlmError("LLM_SERVER_ERROR", retryable=True)), FakeRecords(empty=True))
    )[-2][1]
    assert result["fallback"] == {"reason": "AI_UNAVAILABLE", "draftVerification": None}
    assert result["notice"] is None
    assert result["recordCount"] == 0
    assert all(result["verification"].values())


@pytest.mark.parametrize(
    "draft,field",
    [
        ("99999개 활동이에요.", "numbersMatched"),
        ("“원문에 없는 인용”이라고 썼어요.", "quotesMatched"),
        ("사고력이 좋아졌어요.", "contentAllowed"),
    ],
)
def test_failed_draft_attestation_is_preserved_separately(draft, field):
    result = events(post(FakeLlm(classified("CHANGES"), draft)))[-2][1]
    assert result["fallback"]["draftVerification"][field] is False
    assert all(result["verification"].values())
    assert result["answer"] != draft


def test_invalid_final_template_is_error_without_result_or_done(monkeypatch):
    from app.analysis_agent import templates

    monkeypatch.setattr(templates, "fallback_answer", lambda *args: "99999개 활동이에요.")
    parsed = events(post(FakeLlm(classified("CHANGES"), "99998개 활동이에요.")))
    assert parsed[-1][0] == "error"
    assert parsed[-1][1]["code"] == "FINAL_RESPONSE_VERIFICATION_FAILED"
    assert parsed[-1][1]["retryable"] is True
    assert not any(name in {"result", "done"} for name, _ in parsed)
