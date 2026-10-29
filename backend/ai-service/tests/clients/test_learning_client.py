import asyncio

import httpx
import pytest

from app.clients import learning_client as learning_module
from app.clients.learning_client import LearningClient, RecordsUnavailable
from app.security import UserContext
from tests.analysis_agent.records_fixture import ATTEMPTS, CHANGES, PERIOD, SCOPE, summary

TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
USER = UserContext(
    user_id="p-1",
    role="PARENT",
    student_scope=frozenset({"s-1", "s-2"}),
    traceparent=TRACEPARENT,
)


def use_transport(monkeypatch, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(
        learning_module,
        "internal_client",
        lambda base_url: httpx.AsyncClient(
            base_url=base_url, transport=httpx.MockTransport(recording)
        ),
    )
    return seen


def body(**fields) -> httpx.Response:
    return httpx.Response(200, json={"studentId": "s-1", "state": "OK", "period": PERIOD, **fields})


async def run(call):
    client = LearningClient("http://learning", USER)
    try:
        return await call(client)
    finally:
        await client.aclose()


def test_summary_and_attempts_share_one_connection(monkeypatch) -> None:
    clients: list[httpx.AsyncClient] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/summary"):
            return body(inclusionRule="...", metrics=summary())
        return body(items=ATTEMPTS, page=0, size=8, totalElements=10, inclusionRule="...")

    seen = use_transport(monkeypatch, handler)
    factory = learning_module.internal_client
    monkeypatch.setattr(
        learning_module, "internal_client", lambda url: clients.append(factory(url)) or clients[-1]
    )

    async def both(client):
        return await client.summary(SCOPE), await client.attempts(SCOPE, 8)

    metrics, attempts = asyncio.run(run(both))
    assert metrics[0].label == "학습한 활동"
    assert len(attempts) == 3
    assert len(clients) == 1  # 질문 하나에 연결 하나
    assert seen[1].url.path == "/internal/records/students/s-1/attempts"
    assert dict(seen[1].url.params) == {**PERIOD, "page": "0", "size": "8"}  # 첫 페이지만


def test_context_headers_are_forwarded_as_received(monkeypatch) -> None:
    seen = use_transport(monkeypatch, lambda request: body(items=[]))
    asyncio.run(run(lambda client: client.thinking_types(SCOPE)))
    headers = seen[0].headers
    assert headers["X-User-Id"] == "p-1"
    assert headers["X-User-Role"] == "PARENT"
    assert headers["X-Student-Scope"] == "s-1,s-2"  # 받은 허용 범위 그대로
    assert headers["traceparent"] == TRACEPARENT


def test_changes_read_all_pages(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return body(items=CHANGES, page=page, size=100, totalElements=2)

    seen = use_transport(monkeypatch, handler)
    changes = asyncio.run(run(lambda client: client.changes(SCOPE)))
    assert len(changes) == 2
    assert [r.url.params["page"] for r in seen] == ["0", "1"]
    assert changes[0].counts.chars == (7, 33)


def test_attempts_without_size_read_all_pages(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return body(items=ATTEMPTS if page == 0 else [], page=page, size=100, totalElements=4)

    seen = use_transport(monkeypatch, handler)
    attempts = asyncio.run(run(lambda client: client.attempts(SCOPE, None)))
    assert len(attempts) == 3
    assert [r.url.params["page"] for r in seen] == ["0", "1"]  # 빈 페이지에서 멈춤
    assert seen[0].url.params["size"] == "100"
    assert attempts[2].reflection is not None
    assert attempts[2].reflection.created_at == "2026-10-22T19:30:00+09:00"


def test_evidence_passes_deleted_items_through(monkeypatch) -> None:
    items = [
        {
            "answerId": "a-2",
            "attemptId": "t-1",
            "missionTitle": "쉬는 시간 토론",
            "answerVersion": 2,
            "submittedAt": "2026-10-22T19:00:00+09:00",
            "quote": "나는 찬성해.",
            "available": True,
        },
        {
            "answerId": "a-9",
            "attemptId": None,
            "missionTitle": None,
            "answerVersion": None,
            "submittedAt": None,
            "quote": None,
            "available": False,
        },
    ]
    seen = use_transport(monkeypatch, lambda request: httpx.Response(200, json={"items": items}))
    evidence = asyncio.run(run(lambda client: client.evidence(["a-2", "a-9"])))
    assert seen[0].url.path == "/internal/records/evidence"
    assert dict(seen[0].url.params) == {"answerIds": "a-2,a-9"}
    assert [(e.answer_id, e.available, e.quote) for e in evidence] == [
        ("a-2", True, "나는 찬성해."),
        ("a-9", False, None),  # 삭제된 근거는 원문 없이 그대로
    ]


def test_evidence_forbidden(monkeypatch) -> None:
    use_transport(monkeypatch, lambda request: httpx.Response(403))
    with pytest.raises(RecordsUnavailable) as caught:
        asyncio.run(run(lambda client: client.evidence(["a-1"])))
    assert (caught.value.code, caught.value.retryable) == ("FORBIDDEN", False)


@pytest.mark.parametrize(
    ("response", "code", "retryable"),
    [
        (httpx.Response(503), "RECORDS_UNAVAILABLE", True),
        (httpx.Response(403), "FORBIDDEN", False),
        (httpx.Response(200, text="not json"), "RECORDS_INVALID", False),
        (body(metrics=summary(), studentId="s-2"), "RECORDS_INVALID", False),
        (
            body(metrics=summary(), period={**PERIOD, "from": "2026-10-01"}),
            "RECORDS_INVALID",
            False,
        ),
        (body(state="PROCESSING", metrics=[]), "RECORDS_NOT_READY", True),
        (body(metrics=[{"label": "학습한 활동"}]), "RECORDS_INVALID", False),
    ],
)
def test_failures_are_not_empty_records(monkeypatch, response, code, retryable) -> None:
    use_transport(monkeypatch, lambda request: response)
    with pytest.raises(RecordsUnavailable) as caught:
        asyncio.run(run(lambda client: client.summary(SCOPE)))
    assert (caught.value.code, caught.value.retryable) == (code, retryable)


def test_connection_error_is_retryable(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    use_transport(monkeypatch, handler)
    with pytest.raises(RecordsUnavailable) as caught:
        asyncio.run(run(lambda client: client.thinking_types(SCOPE)))
    assert (caught.value.code, caught.value.retryable) == ("RECORDS_UNAVAILABLE", True)
