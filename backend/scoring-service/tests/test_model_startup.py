import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app import bootstrap
from app.clients.base import internal_client
from app.clients.core_client import CoreClient
from app.model_registry import ModelRegistry
from app.model_startup import ModelStartup
from tests.test_model_registry import loaded, version


def test_core_client_uses_existing_internal_auth_and_path(monkeypatch):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            200, json={"items": [version().model_dump(mode="json", by_alias=True)]}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(handle))
    )

    async def run():
        async with internal_client("http://core.test:8080") as http:
            assert len(await CoreClient(http).active_versions()) == 1

    asyncio.run(run())
    assert len(seen) == 1
    assert seen[0].url.path == "/internal/model-versions/active"
    assert seen[0].headers["X-Internal-Token"] == "test-token"


@pytest.mark.parametrize("first", ["core-error", "loading-error", "empty"])
def test_startup_readiness_retry_and_empty_models(first, caplog):
    async def run():
        attempts = 0

        class Core:
            async def active_versions(self):
                nonlocal attempts
                attempts += 1
                if first == "core-error" and attempts == 1:
                    raise httpx.ConnectError("private-host secret")
                return [] if first == "empty" else [version()]

        loads = 0

        def loader(item):
            nonlocal loads
            loads += 1
            if first == "loading-error" and loads == 1:
                raise RuntimeError("private-bucket secret")
            return loaded(item)

        registry = ModelRegistry(loader)
        startup = ModelStartup(Core(), registry, 0.03)
        assert not await startup.is_ready()
        startup.start()
        try:
            for _ in range(100):
                if attempts:
                    break
                await asyncio.sleep(0.001)
            if first != "empty":
                assert not await startup.is_ready()
            for _ in range(200):
                if await startup.is_ready():
                    break
                await asyncio.sleep(0.005)
            assert await startup.is_ready()
            assert attempts == (1 if first == "empty" else 2)
            assert len(registry.versions()) == (0 if first == "empty" else 1)
        finally:
            await startup.close()

    asyncio.run(run())
    assert "private-host" not in caplog.text
    assert "private-bucket" not in caplog.text


def test_shutdown_interrupts_retry_delay():
    async def run():
        class Core:
            async def active_versions(self):
                raise RuntimeError("offline")

        startup = ModelStartup(Core(), ModelRegistry(loaded), 60)
        startup.start()
        await asyncio.sleep(0)
        await asyncio.wait_for(startup.close(), 1)
        assert not startup.ready

    asyncio.run(run())


def test_http_versions_auth_and_health_do_not_query_core(monkeypatch):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            200, json={"items": [version().model_dump(mode="json", by_alias=True)]}
        )

    monkeypatch.setattr(
        bootstrap,
        "internal_client",
        lambda url: httpx.AsyncClient(base_url=url, transport=httpx.MockTransport(handle)),
    )
    monkeypatch.setattr(bootstrap, "ModelLoader", lambda _: loaded)

    class Broker:
        is_connected = True

        def __init__(self, url):
            pass

        def start(self):
            pass

        async def close(self):
            pass

    monkeypatch.setattr(bootstrap, "AmqpConnection", Broker)

    class Consumer:
        def __init__(self, amqp, core, registry, retry_interval):
            self.startup = ModelStartup(core, registry, retry_interval)

        def start(self):
            self.startup.start()

        async def is_ready(self):
            return await self.startup.is_ready()

        async def close(self):
            await self.startup.close()

    monkeypatch.setattr(bootstrap, "ModelVersionConsumer", Consumer)
    with TestClient(bootstrap.create_app()) as client:

        async def wait_ready():
            for _ in range(200):
                if await client.app.state.readiness_checks["models"]():
                    return
                await asyncio.sleep(0.005)
            raise AssertionError("startup not ready")

        client.portal.call(wait_ready)
        assert client.get("/internal/versions").status_code == 401
        response = client.get("/internal/versions", headers={"X-Internal-Token": "test-token"})
        assert response.json() == {
            "items": [
                {
                    "name": "m2-klue-narrative",
                    "version": "1.1",
                    "revision": 1,
                }
            ]
        }
        for _ in range(3):
            assert client.get("/health/ready").json() == {
                "status": "UP",
                "checks": {"rabbitmq": "UP", "models": "UP"},
            }
        assert len(calls) == 1
