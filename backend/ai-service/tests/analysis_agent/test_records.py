import asyncio

import httpx
import pytest

from app.analysis_agent import records as records_module
from app.analysis_agent.records import HttpLearningRecords, RecordsUnavailable
from app.security import UserContext
from tests.analysis_agent.records_fixture import ATTEMPTS, CHANGES, PERIOD, SCOPE, summary

USER = UserContext(user_id="p-1", role="PARENT", student_scope=frozenset({"s-1"}))


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


def body(**fields) -> httpx.Response:
    return httpx.Response(200, json={"studentId": "s-1", "state": "OK", "period": PERIOD, **fields})


async def run(call):
    records = HttpLearningRecords("http://learning", USER)
    try:
        return await call(records)
    finally:
        await records.aclose()


def test_summary_and_recent_attempts_share_one_connection(monkeypatch) -> None:
    clients: list[httpx.AsyncClient] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/summary"):
            return body(inclusionRule="...", metrics=summary())
        return body(items=ATTEMPTS, page=0, size=8, totalElements=10, inclusionRule="...")

    seen = use_transport(monkeypatch, handler)
    factory = records_module.internal_client
    monkeypatch.setattr(
        records_module, "internal_client", lambda url: clients.append(factory(url)) or clients[-1]
    )

    async def both(records):
        return await records.summary(SCOPE), await records.recent_attempts(SCOPE, 8)

    metrics, attempts = asyncio.run(run(both))
    assert metrics[0].label == "학습한 활동"
    assert len(attempts) == 3
    assert len(clients) == 1  # 질문 하나에 연결 하나
    assert seen[1].url.path == "/internal/records/students/s-1/attempts"
    assert dict(seen[1].url.params) == {**PERIOD, "page": "0", "size": "8"}  # 첫 페이지만
    assert seen[0].headers["X-Student-Scope"] == "s-1"
    assert seen[0].headers["X-User-Role"] == "PARENT"


def test_changes_read_all_pages(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return body(items=CHANGES, page=page, size=100, totalElements=2)

    seen = use_transport(monkeypatch, handler)
    changes = asyncio.run(run(lambda records: records.changes(SCOPE)))
    assert len(changes) == 2
    assert [r.url.params["page"] for r in seen] == ["0", "1"]
    assert changes[0].counts.chars == (7, 33)


@pytest.mark.parametrize(
    ("response", "code", "retryable"),
    [
        (httpx.Response(503), "RECORDS_UNAVAILABLE", True),
        (httpx.Response(403), "FORBIDDEN", False),
        (body(metrics=summary(), studentId="s-2"), "RECORDS_INVALID", False),
        (
            body(metrics=summary(), period={**PERIOD, "from": "2026-10-01"}),
            "RECORDS_INVALID",
            False,
        ),
        (body(state="PROCESSING", metrics=[]), "RECORDS_NOT_READY", True),
        (body(metrics=[{"label": "학습한 활동"}]), "RECORDS_INVALID", False),
        (body(metrics=summary()[1:]), "RECORDS_INVALID", False),  # 집계 대상 수 지표 없음
    ],
)
def test_failures_are_not_empty_records(monkeypatch, response, code, retryable) -> None:
    use_transport(monkeypatch, lambda request: response)
    with pytest.raises(RecordsUnavailable) as caught:
        asyncio.run(run(lambda records: records.summary(SCOPE)))
    assert (caught.value.code, caught.value.retryable) == (code, retryable)


def test_every_tool_call_rechecks_permission(monkeypatch) -> None:
    seen = use_transport(monkeypatch, lambda request: body(items=[]))
    outsider = UserContext(user_id="p-2", role="PARENT", student_scope=frozenset({"s-9"}))

    async def call():
        records = HttpLearningRecords("http://learning", outsider)
        await records.thinking_activities(SCOPE)

    with pytest.raises(RecordsUnavailable) as caught:
        asyncio.run(call())
    assert caught.value.code == "FORBIDDEN"
    assert seen == []  # 권한 밖이면 learning을 호출하지 않음


def test_connection_error_is_retryable(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    use_transport(monkeypatch, handler)
    with pytest.raises(RecordsUnavailable) as caught:
        asyncio.run(run(lambda records: records.thinking_types(SCOPE)))
    assert (caught.value.code, caught.value.retryable) == ("RECORDS_UNAVAILABLE", True)
