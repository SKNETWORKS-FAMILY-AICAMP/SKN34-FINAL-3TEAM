import asyncio

import httpx
import pytest

from app.analysis_agent import records as records_module
from app.analysis_agent.records import HttpLearningRecords, RecordsUnavailable
from app.security import UserContext
from tests.analysis_agent.records_fixture import ATTEMPTS, SCOPE

USER = UserContext(user_id="p-1", role="PARENT", student_scope=frozenset({"s-1"}))
PERIOD = {"from": "2026-10-20", "to": "2026-10-26"}


def use_transport(monkeypatch, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(
        records_module,
        "internal_client",
        lambda base_url: httpx.AsyncClient(
            base_url=base_url, transport=httpx.MockTransport(recording)
        ),
    )
    return seen


def page(items, page_no, total, **extra):
    return httpx.Response(
        200,
        json={
            "childId": "s-1",
            "state": "OK",
            "period": PERIOD,
            "items": items,
            "page": page_no,
            "size": 100,
            "totalElements": total,
            **extra,
        },
    )


def test_reads_all_pages_with_confirmed_scope(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        number = int(request.url.params["page"])
        return page(ATTEMPTS[number * 3 : number * 3 + 3], number, len(ATTEMPTS))

    seen = use_transport(monkeypatch, handler)
    attempts = asyncio.run(HttpLearningRecords("http://learning", USER).attempts(SCOPE))
    assert len(attempts) == len(ATTEMPTS)
    assert seen[0].url.path == "/internal/records/students/s-1/attempts"
    assert dict(seen[0].url.params) == {**PERIOD, "page": "0", "size": "100"}
    assert seen[0].headers["X-Student-Scope"] == "s-1"
    assert seen[0].headers["X-User-Role"] == "PARENT"


@pytest.mark.parametrize(
    ("response", "code", "retryable"),
    [
        (httpx.Response(503), "RECORDS_UNAVAILABLE", True),
        (httpx.Response(403), "FORBIDDEN", False),
        (page([], 0, 0, childId="s-2"), "RECORDS_INVALID", False),
        (
            page([], 0, 0, period={"from": "2026-10-01", "to": "2026-10-26"}),
            "RECORDS_INVALID",
            False,
        ),
        (page([], 0, 0, state="PROCESSING"), "RECORDS_NOT_READY", True),
        (page([{"attemptId": 1}], 0, 1), "RECORDS_INVALID", False),
    ],
)
def test_failures_are_not_empty_records(monkeypatch, response, code, retryable) -> None:
    use_transport(monkeypatch, lambda request: response)
    with pytest.raises(RecordsUnavailable) as caught:
        asyncio.run(HttpLearningRecords("http://learning", USER).attempts(SCOPE))
    assert (caught.value.code, caught.value.retryable) == (code, retryable)


def test_every_tool_call_rechecks_permission(monkeypatch) -> None:
    seen = use_transport(monkeypatch, lambda request: page([], 0, 0))
    outsider = UserContext(user_id="p-2", role="PARENT", student_scope=frozenset({"s-9"}))
    with pytest.raises(RecordsUnavailable) as caught:
        asyncio.run(HttpLearningRecords("http://learning", outsider).changes(SCOPE))
    assert caught.value.code == "FORBIDDEN"
    assert seen == []  # 권한 밖이면 learning을 호출하지 않음


def test_connection_error_is_retryable(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    use_transport(monkeypatch, handler)
    with pytest.raises(RecordsUnavailable) as caught:
        asyncio.run(HttpLearningRecords("http://learning", USER).thinking_types(SCOPE))
    assert (caught.value.code, caught.value.retryable) == ("RECORDS_UNAVAILABLE", True)
