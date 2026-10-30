"""#135: 실제 lifespan에서 공유 클라이언트의 수명·요청별 권한 분리를 검증한다."""

import asyncio
from types import SimpleNamespace
from typing import Annotated
from unittest.mock import Mock

import httpx
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app import bootstrap
from app.clients.base import internal_client
from app.query.router import query_service
from app.query.service import QueryService


def setup(monkeypatch, *, storage_error=False, close_error=False):
    seen, clients = [], []
    engine, storage = SimpleNamespace(dispose=Mock()), SimpleNamespace(close=Mock())
    if close_error:
        storage.close.side_effect = RuntimeError("synthetic close failure")

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    def http(url):
        client = internal_client(url, transport=httpx.MockTransport(handler))
        clients.append(client)
        return client

    configured = Mock(return_value=storage)
    if storage_error:
        configured.side_effect = RuntimeError("synthetic storage startup failure")
    monkeypatch.setattr(bootstrap, "create_db_engine", lambda: engine)
    monkeypatch.setattr(bootstrap, "create_session_factory", lambda _: object())
    monkeypatch.setattr(bootstrap, "internal_client", http)
    monkeypatch.setattr(bootstrap.ObjectStorage, "configured", configured)
    return engine, storage, clients, seen, configured


def test_requests_share_clients_without_reusing_user_scope_or_closing_early(monkeypatch):
    engine, storage, clients, seen, configured = setup(monkeypatch)
    app = bootstrap.create_app()

    @app.get("/internal/lifespan-probe")
    async def probe(service: Annotated[QueryService, Depends(query_service)]):
        await service._learning._client.get("/synthetic")
        assert service._storage() is storage
        return {"client": id(service._learning), "storage": id(service._storage())}

    with TestClient(app) as client:
        results = []
        for user, scope in (("parent-a", "student-a"), ("parent-b", "student-b")):
            response = client.get(
                "/internal/lifespan-probe",
                headers={
                    "X-Internal-Token": "test-token",
                    "X-User-Id": user,
                    "X-User-Role": "PARENT",
                    "X-Student-Scope": scope,
                },
            )
            assert response.status_code == 200
            results.append(response.json())
        # 권한 없는 다음 요청으로 이전 학생 scope가 전파되지 않는다.
        assert (
            client.get(
                "/internal/lifespan-probe", headers={"X-Internal-Token": "test-token"}
            ).status_code
            == 200
        )
        assert results[0] == results[1]
        assert len(clients) == configured.call_count == 1
        storage.close.assert_not_called()
        assert not clients[0].is_closed
    assert [(x.headers.get("X-User-Id"), x.headers.get("X-Student-Scope")) for x in seen] == [
        ("parent-a", "student-a"),
        ("parent-b", "student-b"),
        (None, None),
    ]
    assert all(x.headers["X-Internal-Token"] == "test-token" for x in seen)
    storage.close.assert_called_once()
    engine.dispose.assert_called_once()
    assert clients[0].is_closed


@pytest.mark.parametrize("phase", ["storage-startup", "request", "storage-close"])
def test_partial_startup_and_failure_still_close_owned_resources(monkeypatch, phase):
    engine, storage, clients, _, _ = setup(
        monkeypatch, storage_error=phase == "storage-startup", close_error=phase == "storage-close"
    )

    async def scenario():
        async with bootstrap.lifespan(bootstrap.create_app()):
            if phase == "request":
                raise RuntimeError("synthetic request failure")

    with pytest.raises(RuntimeError, match="synthetic"):
        asyncio.run(scenario())
    assert len(clients) == 1 and clients[0].is_closed
    engine.dispose.assert_called_once()
    assert storage.close.call_count == (0 if phase == "storage-startup" else 1)
