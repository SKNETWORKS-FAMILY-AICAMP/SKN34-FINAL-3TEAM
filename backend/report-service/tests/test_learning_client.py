import asyncio
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.clients.base import internal_client
from app.clients.learning_client import LearningClient
from app.generation.metrics import MetricsCalculator
from app.generation.models import ItemType, ReportState
from app.generation.records import RecordContractError
from app.security import UserContext, bind_user_context, reset_user_context
from tests.record_helpers import (
    PERIOD,
    attempt_for,
    page,
    wire_attempt,
    wire_changes,
    wire_thinking,
)


def handler_for(student, attempts, requests, mutate=None):
    def handle(request):
        requests.append(request)
        assert request.method == "GET" and request.url.host == "learning.test"
        assert request.headers["X-Internal-Token"] == "test-token"
        assert request.headers["X-User-Role"] == "SYSTEM"
        assert request.headers["X-Student-Scope"] == str(student)
        assert request.headers["traceparent"] == "synthetic-trace"
        assert request.url.params["from"] == "2026-10-19"
        assert request.url.params["to"] == "2026-10-25"
        name = request.url.path.rsplit("/", 1)[-1]
        if name == "attempts":
            index = int(request.url.params["page"])
            values = [wire_attempt(a) for a in attempts]
            data = page(
                student, values[index * 100 : (index + 1) * 100], index=index, total=len(values)
            )
        elif name == "thinking-types":
            data = wire_thinking(student, attempts)
        elif name == "changes":
            data = wire_changes(student, attempts)
        else:
            raise AssertionError("Unexpected call")
        if mutate:
            data = mutate(name, data)
        return httpx.Response(200, json=data)

    return handle


async def read(student, handler):
    reset = bind_user_context(
        UserContext(None, "SYSTEM", frozenset({str(student)}), "synthetic-trace")
    )
    try:
        async with internal_client(
            "http://learning.test", transport=httpx.MockTransport(handler)
        ) as http:
            return await LearningClient(http).records(student, PERIOD)
    finally:
        reset_user_context(reset)


def test_all_pages_are_loaded_with_existing_internal_headers():
    student = uuid4()
    attempts = [attempt_for(student) for _ in range(101)]
    requests = []
    records = asyncio.run(read(student, handler_for(student, attempts, requests)))
    assert len(records.attempts) == 101
    assert [r.url.params["page"] for r in requests if r.url.path.endswith("attempts")] == ["0", "1"]
    assert len(requests) == 4


def test_tombstone_and_private_fields_are_not_forwarded():
    student = uuid4()
    attempt = attempt_for(student)

    def mutate(name, data):
        if name == "attempts":
            data["items"][0]["draft"] = {"content": {"memo": "PRIVATE-MEMO-TEST"}}
            data["items"][0]["memo"] = "PRIVATE-MEMO-TEST"
            data["items"][0]["answers"][0]["content"] = {"memo": "PRIVATE-MEMO-TEST"}
            data["items"].append({"attemptId": str(uuid4()), "available": False})
            data["totalElements"] = 2
        return data

    records = asyncio.run(read(student, handler_for(student, [attempt], [], mutate)))
    assert len(records.attempts) == 1
    assert "PRIVATE-MEMO-TEST" not in repr(records)


@pytest.mark.parametrize(
    "difficulty,text,created_at,written",
    [
        ("EASY", "", "2026-10-20T10:00:00+09:00", True),
        ("NORMAL", None, "2026-10-20T10:00:00+09:00", True),
        ("HARD", "직접 쓴 돌아보기", "2026-10-20T10:00:00+09:00", True),
        ("NORMAL", "지난 주 기록", "2026-10-18T23:59:59+09:00", False),
        ("NORMAL", "다음 주 기록", "2026-10-26T00:00:00+09:00", False),
    ],
)
def test_reflection_input_becomes_period_scoped_report_item(difficulty, text, created_at, written):
    student = uuid4()

    def mutate(name, data):
        if name == "attempts":
            data["items"][0]["reflection"] = {
                "difficulty": difficulty,
                "text": text,
                "createdAt": created_at,
            }
        return data

    records = asyncio.run(read(student, handler_for(student, [attempt_for(student)], [], mutate)))
    result = MetricsCalculator().calculate(records)
    [reflection] = [item.payload for item in result.items if item.type == ItemType.REFLECTION]
    assert reflection["written"] is written
    assert reflection["difficulty"] == (difficulty if written else None)
    assert reflection["text"] == (text if written else None)


@pytest.mark.parametrize("omit", [False, True])
def test_null_or_absent_reflection_produces_unwritten_report_item(omit):
    student = uuid4()

    def mutate(name, data):
        if name == "attempts" and omit:
            del data["items"][0]["reflection"]
        return data

    records = asyncio.run(read(student, handler_for(student, [attempt_for(student)], [], mutate)))
    result = MetricsCalculator().calculate(records)
    [reflection] = [item for item in result.items if item.type == ItemType.REFLECTION]
    assert reflection.state == ReportState.NO_RECORD
    assert reflection.payload["written"] is False
    assert reflection.payload["difficulty"] is None and reflection.payload["text"] is None


@pytest.mark.parametrize(
    "reflection",
    [
        {"written": False},
        {"difficulty": "보통", "text": None, "createdAt": "2026-10-20T10:00:00+09:00"},
    ],
)
def test_report_output_shape_is_not_accepted_as_learning_reflection_input(reflection):
    student = uuid4()

    def mutate(name, data):
        if name == "attempts":
            data["items"][0]["reflection"] = reflection
        return data

    with pytest.raises(ValidationError):
        asyncio.run(read(student, handler_for(student, [attempt_for(student)], [], mutate)))


def test_empty_no_record_response_needs_no_attempt_tombstones():
    student = uuid4()

    def mutate(name, data):
        data["state"] = "NO_RECORD"
        return data

    records = asyncio.run(read(student, handler_for(student, [], [], mutate)))
    result = MetricsCalculator().calculate(records)
    assert records.attempts == () and records.changes == ()
    assert result.state == ReportState.NO_RECORD
    assert all(item.payload["count"] == 0 for item in result.items if item.type == ItemType.METRIC)


@pytest.mark.parametrize(
    "fault",
    [
        "student",
        "period",
        "failed",
        "processing",
        "missing-page",
        "missing-hints",
        "naive-time",
        "boolean-version",
        "thinking-duplicate",
    ],
)
def test_invalid_or_incomplete_response_fails_instead_of_becoming_no_record(fault):
    student = uuid4()

    def mutate(name, data):
        if name == "attempts":
            if fault == "student":
                data["childId"] = str(uuid4())
            elif fault == "period":
                data["period"]["to"] = "2026-10-26"
            elif fault in ("failed", "processing"):
                data["state"] = fault.upper()
            elif fault == "missing-page":
                data["items"], data["totalElements"] = [], 1
            elif fault == "missing-hints":
                del data["items"][0]["hintUsages"]
            elif fault == "naive-time":
                data["items"][0]["answers"][0]["submittedAt"] = "2026-10-20T10:00:00"
            elif fault == "boolean-version":
                data["items"][0]["answers"][0]["version"] = True
        if name == "thinking-types" and fault == "thinking-duplicate":
            data["items"].append(data["items"][0])
        return data

    with pytest.raises((RecordContractError, ValidationError)):
        asyncio.run(read(student, handler_for(student, [attempt_for(student)], [], mutate)))


@pytest.mark.parametrize("fault", ["duplicate", "total-changed", "wrong-page"])
def test_page_consistency_checks(fault):
    student = uuid4()
    attempts = [attempt_for(student) for _ in range(101)]

    def mutate(name, data):
        if name == "attempts" and data["page"] == 1:
            if fault == "duplicate":
                data["items"][0] = wire_attempt(attempts[0])
            elif fault == "total-changed":
                data["totalElements"] = 102
            else:
                data["page"] = 0
        return data

    with pytest.raises(RecordContractError):
        asyncio.run(read(student, handler_for(student, attempts, [], mutate)))


@pytest.mark.parametrize("status", [403, 404, 500, 503])
def test_http_errors_are_not_retried_or_converted_to_empty_records(status):
    student, calls = uuid4(), []

    def fail(request):
        calls.append(request)
        return httpx.Response(status, json={"detail": "synthetic failure"})

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(read(student, fail))
    assert len(calls) == 1


def test_scope_is_checked_before_any_http_call():
    student, calls = uuid4(), []

    async def scenario():
        async with internal_client(
            "http://learning.test", transport=httpx.MockTransport(lambda r: calls.append(r))
        ) as http:
            with pytest.raises(RecordContractError, match="context"):
                await LearningClient(http).records(student, PERIOD)

    asyncio.run(scenario())
    assert calls == []
