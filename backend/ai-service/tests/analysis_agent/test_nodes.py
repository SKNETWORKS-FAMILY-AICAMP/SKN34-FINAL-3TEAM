"""분석 대화 노드 단위 테스트 (그래프 없이 노드 하나씩, 가짜 LLM·가짜 learning)."""

import asyncio
import time

import pytest
from langgraph.runtime import Runtime

from app.analysis_agent import templates
from app.analysis_agent.calculators import THOUGHT_LIMIT, compute
from app.analysis_agent.models import AnalysisRequest, StreamError, Verification
from app.analysis_agent.nodes import respond, retrieve, understand
from app.analysis_agent.nodes.events import delta, status
from app.analysis_agent.prompts import Classification
from app.analysis_agent.state import AgentContext
from app.clients.learning_client import RecordsUnavailable
from app.llm.base import LlmError
from app.versions import ActiveVersions
from tests.analysis_agent.records_fixture import PERIOD, SCOPE, STUDENT, FakeRecords, records
from tests.fakes import FakeLlm

REQUEST = AnalysisRequest.model_validate(
    {
        "conversationId": "c-1",
        "question": "질문을 받고 뭐가 달라졌어?",
        "scope": {"studentId": STUDENT, **PERIOD},
    }
)


def run(node, state, llm: FakeLlm | None = None, tools: FakeRecords | None = None):
    """노드 하나를 실행해 (바뀐 상태 조각, 보낸 스트림 조각)을 돌려줌."""
    written: list[dict] = []
    context = AgentContext(
        llm=llm or FakeLlm(),
        tools=tools or FakeRecords(),
        deadline=time.monotonic() + 60,
        prompt=ActiveVersions().prompt("analysis"),
    )  # type: ignore[arg-type]
    update = asyncio.run(node(state, Runtime(context=context, stream_writer=written.append)))
    return update, written


def state(intent: str, empty: bool = False, **extra) -> dict:
    return {
        "request": REQUEST,
        "prompt_version": "analysis@2",
        "intent": intent,
        "computation": compute(intent, records(empty), SCOPE),
        **extra,
    }


def test_events_shape() -> None:
    assert status("조회 중") == {
        "event": "status",
        "data": {"state": "RUNNING", "message": "조회 중"},
    }
    assert delta("조각") == {"event": "delta", "data": {"text": "조각"}}


# --- understand.classify ---------------------------------------------------


def test_classify_without_scope_issue() -> None:
    llm = FakeLlm(Classification(intent="CHANGES", scope_issue="NONE"))
    update, written = run(understand.classify, {"request": REQUEST}, llm)
    assert update == {"intent": "CHANGES", "model": "fake-model"}
    assert written == [status("질문을 확인하는 중")]
    assert STUDENT not in llm.requests[0].user  # 학생 ID를 LLM에 보내지 않음


@pytest.mark.parametrize("issue", ["OTHER_CHILD", "DIFFERENT_PERIOD", "UNCLEAR"])
def test_classify_scope_issue_asks_clarification(issue) -> None:
    llm = FakeLlm(Classification(intent="COUNT", scope_issue=issue))
    update, _ = run(understand.classify, {"request": REQUEST}, llm)
    clarification = update["clarification"]
    assert clarification.reason == issue
    assert clarification.message == understand.CLARIFY_MESSAGES[issue]
    # 범위를 임의로 바꾸지 않고 골라 둔 범위를 그대로 돌려줌
    assert clarification.current.model_dump(by_alias=True, mode="json") == {
        "childId": STUDENT,
        **PERIOD,
    }


def test_classify_llm_failure_counts_without_classification() -> None:
    llm = FakeLlm(LlmError("LLM_SERVER_ERROR", retryable=True))
    update, _ = run(understand.classify, {"request": REQUEST}, llm)
    assert update == {"intent": "COUNT", "fallback_reason": "AI_UNAVAILABLE"}


# --- retrieve.retrieve·compute ---------------------------------------------


@pytest.mark.parametrize(
    "intent,fields,calls",
    [
        ("COUNT", {"summary"}, {"summary"}),
        ("MATH_CHECK", {"summary"}, {"summary"}),
        ("OTHER", {"summary"}, {"summary"}),
        ("THINKING_TYPES", {"summary", "thinking_types"}, {"summary", "thinking_types"}),
        ("CHILD_THOUGHTS", {"summary", "attempts"}, {"summary", "attempts"}),
        (
            "CHANGES",
            {"summary", "changes", "activities"},
            {"summary", "changes", "thinking_activities"},
        ),
        ("REFLECTIONS", {"summary", "attempts"}, {"summary", "attempts"}),
    ],
)
def test_retrieve_calls_tools_for_intent(intent, fields, calls) -> None:
    tools = FakeRecords()
    update, written = run(retrieve.retrieve, {"request": REQUEST, "intent": intent}, tools=tools)
    assert update["records"].model_fields_set == fields
    assert {name for name, _ in tools.calls} == calls
    assert all(scope == SCOPE for _, scope in tools.calls)
    assert written == [status("기록을 조회하는 중")]


@pytest.mark.parametrize("intent,size", [("CHILD_THOUGHTS", THOUGHT_LIMIT), ("REFLECTIONS", None)])
def test_retrieve_attempts_page_size(intent, size) -> None:
    tools = FakeRecords()
    run(retrieve.retrieve, {"request": REQUEST, "intent": intent}, tools=tools)
    assert tools.attempts_size == size


@pytest.mark.parametrize(
    "code,retryable,message",
    [
        ("FORBIDDEN", False, "이 자녀의 기록을 조회할 권한이 없어요."),
        ("RECORDS_NOT_READY", True, "기록을 집계하는 중이에요. 잠시 뒤 다시 물어봐 주세요."),
        ("RECORDS_UNAVAILABLE", True, retrieve.DEFAULT_ERROR),
    ],
)
def test_retrieve_failure_is_error_not_empty_records(code, retryable, message) -> None:
    tools = FakeRecords(fail=RecordsUnavailable(code, retryable=retryable))
    update, _ = run(retrieve.retrieve, {"request": REQUEST, "intent": "CHANGES"}, tools=tools)
    assert update == {"error": StreamError(code=code, message=message, retryable=retryable)}


def test_retrieve_unexpected_error_is_raised() -> None:
    tools = FakeRecords(fail=RuntimeError("boom"))  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        run(retrieve.retrieve, {"request": REQUEST, "intent": "COUNT"}, tools=tools)


def test_compute_marks_insufficient_records() -> None:
    update, written = run(
        retrieve.compute, {"request": REQUEST, "intent": "COUNT", "records": records(empty=True)}
    )
    assert update["computation"].insufficient == "NO_RECORD"
    assert update["computation"].record_count == 0
    assert written == [status("수치를 계산하는 중")]


# --- respond.answer·check ----------------------------------------------------


def test_answer_streams_draft_as_deltas() -> None:
    llm = FakeLlm("3개 시도 중 1개에서 답을 다시 썼어요.")
    update, written = run(respond.answer, state("CHANGES"), llm)
    assert update == {"draft": "3개 시도 중 1개에서 답을 다시 썼어요.", "model": "fake-model"}
    assert written[0] == status("답변을 쓰는 중")
    assert "".join(e["data"]["text"] for e in written[1:]) == update["draft"]
    assert {e["event"] for e in written[1:]} == {"delta"}


@pytest.mark.parametrize(
    "step,sent",
    [
        (LlmError("LLM_TIMEOUT", retryable=True), []),
        (["3개 시도", LlmError("LLM_CONNECTION", retryable=True)], ["3개 시도"]),
    ],
)
def test_answer_llm_failure_falls_back(step, sent) -> None:
    update, written = run(respond.answer, state("CHANGES"), FakeLlm(step))
    assert update == {"fallback_reason": "AI_UNAVAILABLE"}
    assert [e["data"]["text"] for e in written if e["event"] == "delta"] == sent


def test_check_confirms_verified_draft() -> None:
    draft = "  3개 시도 중 1개에서 “왜냐하면 쉬는 시간이 길면”이라는 까닭을 더했어요.\n"
    update, written = run(respond.check, state("CHANGES", draft=draft, model="fake-model"))
    result = update["result"]
    assert result.source == "LLM"
    assert result.answer == draft.strip()
    assert result.fallback is None
    assert [e.answer_id for e in result.evidence] == ["a-2"]
    assert result.versions.model == "fake-model"
    assert result.versions.prompt == "analysis@2"
    assert written == [status("숫자와 인용을 기록과 맞춰 보는 중")]


def test_check_failure_keeps_verification_without_result() -> None:
    update, _ = run(respond.check, state("CHANGES", draft="7개 시도에서 답을 바꿨어요."))
    assert set(update) == {"verification", "fallback_reason"}
    assert update["fallback_reason"] == "VERIFICATION_FAILED"
    assert update["verification"].numbers_matched is False


# --- respond.fallback·insufficient·unsupported ------------------------------


@pytest.mark.parametrize(
    "reason,draft_verification",
    [
        (
            "VERIFICATION_FAILED",
            Verification(numbers_matched=False, quotes_matched=True, content_allowed=True),
        ),
        ("AI_UNAVAILABLE", None),
    ],
)
def test_fallback_is_verified_template(reason, draft_verification) -> None:
    extra = {"fallback_reason": reason}
    if draft_verification:
        extra["verification"] = draft_verification
    update, _ = run(respond.fallback, state("CHANGES", **extra))
    result = update["result"]
    assert result.source == "TEMPLATE"
    assert result.fallback.reason == reason
    assert result.fallback.draft_verification == draft_verification
    assert result.notice is None
    assert all(result.verification.model_dump().values())
    assert result.versions.model is None  # LLM 답변을 쓰지 않음
    assert result.answer == templates.fallback_answer(
        reason, compute("CHANGES", records(), SCOPE), SCOPE
    )


def test_insufficient_is_notice_not_fallback() -> None:
    update, _ = run(respond.insufficient, state("COUNT", empty=True))
    result = update["result"]
    assert result.source == "TEMPLATE"
    assert result.notice.reason == "NO_RECORD"
    assert result.fallback is None
    assert result.record_count == 0
    assert "분석할 기록이 없어요" in result.answer


@pytest.mark.parametrize("intent,notice", [("MATH_CHECK", "MATH_CHECK"), ("OTHER", "UNSUPPORTED")])
def test_unsupported_notice(intent, notice) -> None:
    update, _ = run(respond.unsupported, state(intent))
    result = update["result"]
    assert result.notice.reason == notice
    assert result.fallback is None
    assert result.record_count == 3


@pytest.mark.parametrize(
    "node,template,current",
    [
        (respond.fallback, "fallback_answer", state("CHANGES", fallback_reason="AI_UNAVAILABLE")),
        (respond.insufficient, "insufficient_answer", state("COUNT", empty=True)),
        (respond.unsupported, "unsupported_answer", state("MATH_CHECK")),
    ],
)
def test_unverified_template_is_error(monkeypatch, node, template, current) -> None:
    monkeypatch.setattr(templates, template, lambda *args: "99999개 활동이에요.")
    update, _ = run(node, current)
    assert update == {
        "error": StreamError(
            code="FINAL_RESPONSE_VERIFICATION_FAILED",
            message="최종 안내를 기록과 대조하지 못했어요.",
            retryable=True,
        )
    }
