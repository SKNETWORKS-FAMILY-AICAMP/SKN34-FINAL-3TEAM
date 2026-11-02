"""기동 snapshot·이벤트 순서·재연결·Pod별 수신 계약."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.clients.base import internal_client
from app.clients.core_client import CoreClient
from app.messaging.consumer import ActivationEnvelope, ModelVersionConsumer
from app.versions import PROMPT_SCOPES, ActiveVersions
from tests.test_active_versions import installed, version


def event(name: str = "judgment", revision: int = 2, release: str = "judge@next", **changes):
    data = version(name, release, revision).model_dump(mode="json", by_alias=True)
    data["previousVersionId"] = None
    data.update(changes)
    return {
        "id": str(uuid4()),
        "specversion": "1.0",
        "type": "model.version.activated",
        "source": "core-service",
        "time": "2026-10-30T00:00:00Z",
        "dataschema": "model.version.activated.v1",
        "data": data,
    }


def message(payload):
    return SimpleNamespace(body=json.dumps(payload).encode(), ack=AsyncMock())


async def until(predicate):
    for _ in range(500):
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition not reached")


def test_core_snapshot_uses_internal_token_and_validates_contract(monkeypatch):
    async def run():
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.url.path, request.headers.get("X-Internal-Token")))
            return httpx.Response(
                200,
                json={
                    "items": [version("judgment", "judge@2").model_dump(mode="json", by_alias=True)]
                },
            )

        monkeypatch.setattr(
            "app.clients.base.get_settings",
            lambda: SimpleNamespace(
                internal_token="test-token", http_read_timeout=30.0, http_connect_timeout=2.0
            ),
        )
        async with internal_client(
            "http://core",
        ) as client:
            client._transport = httpx.MockTransport(handler)
            items = await CoreClient(client).active_versions()
        assert seen == [("/internal/model-versions/active", "test-token")]
        assert items[0].name == "judgment"

    asyncio.run(run())


def test_buffer_retry_reconnect_and_two_pod_queues():
    async def run():
        class Queue:
            def __init__(self, order):
                self.name = f"exclusive-{uuid4()}"
                self._order = order
                self.receiver = None

            async def bind(self, _exchange, **kwargs):
                assert kwargs == {"routing_key": "model.version.*", "robust": False}
                self._order.append("bind")

            async def consume(self, callback, **kwargs):
                assert kwargs == {"robust": False}
                self._order.append("consume")
                self.receiver = callback

        class Channel:
            def __init__(self, order, queues):
                self._order = order
                self._queues = queues

            async def set_qos(self, **kwargs):
                assert kwargs == {"prefetch_count": 100}

            async def get_exchange(self, name, **kwargs):
                assert (name, kwargs) == ("events.topic", {"ensure": True})
                return object()

            async def declare_queue(self, name, **kwargs):
                assert (name, kwargs) == (
                    "",
                    {"exclusive": True, "auto_delete": True, "robust": False},
                )
                self._order.append("declare")
                queue = Queue(self._order)
                self._queues.append(queue)
                return queue

            async def close(self):
                pass

        class Core:
            def __init__(self, order, fail=False):
                self.order = order
                self.fail = fail
                self.calls = 0
                self.release = asyncio.Event()

            async def active_versions(self):
                self.order.append("snapshot")
                self.calls += 1
                if self.fail and self.calls == 1:
                    raise OSError("core unavailable")
                if self.fail and self.calls == 2:
                    await self.release.wait()
                if self.calls >= (3 if self.fail else 2):
                    return [version("judgment", "judge@next", 4)]
                return [version("judgment", "judge@2", 1)]

        consumers = []
        for fail in (True, False):
            order, queues = [], []
            connection = SimpleNamespace(close_callbacks=set())
            connection.channel = AsyncMock(
                side_effect=lambda order=order, queues=queues: Channel(order, queues)
            )
            broker = SimpleNamespace(is_connected=True, connection=connection)
            core = Core(order, fail)
            registry = installed("judgment", "judge@next")
            consumer = ModelVersionConsumer(broker, core, registry, 0.005)
            consumers.append((consumer, connection, core, registry, order, queues))
            consumer.start()
        try:
            await until(lambda: all(items[5] for items in consumers))
            for _consumer, _, _, _, order, _ in consumers:
                assert order[:4] == ["declare", "bind", "consume", "snapshot"]
            await until(lambda: consumers[0][2].calls >= 2)
            assert not await consumers[0][0].is_ready()
            for _, _, _, _, _, queues in consumers:
                msg = message(event(revision=3))
                await queues[0].receiver(msg)
                msg.ack.assert_awaited_once()
                stale = message(event(revision=2))
                await queues[0].receiver(stale)
                stale.ack.assert_awaited_once()
            consumers[0][2].release.set()
            await until(lambda: all(items[0]._initialized for items in consumers))
            assert all(items[3].prompt("judgment").version == "judge@next" for items in consumers)
            assert all(items[3]._active["judgment"].revision == 3 for items in consumers)
            assert all([await consumer.is_ready() for consumer, *_ in consumers])

            # 재연결 동안 이벤트가 유실돼도 새 큐 뒤 snapshot을 다시 읽는다.
            for _, connection, _, _, _, _ in consumers:
                for callback in list(connection.close_callbacks):
                    callback()
            await until(lambda: all(len(items[5]) == 2 for items in consumers))
            await until(lambda: all(items[0]._initialized for items in consumers))
            assert all(items[2].calls >= 2 for items in consumers)
            assert all(items[5][0].name != items[5][1].name for items in consumers)
            assert all(items[3].prompt("judgment").version == "judge@next" for items in consumers)
        finally:
            for consumer, connection, *_ in consumers:
                await consumer.close()
                assert not connection.close_callbacks

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e.pop("id"),
        lambda e: e.update(specversion="2.0"),
        lambda e: e["data"].pop("previousVersionId"),
        lambda e: e["data"].update(scopes=[PROMPT_SCOPES["judgment"]] * 2),
        lambda e: e["data"].update(revision=True),
        lambda e: e["data"].update(artifactUri="SECRET", unexpected="SECRET"),
    ],
)
def test_invalid_event_ack_without_payload_log(mutate, caplog):
    async def run():
        consumer = ModelVersionConsumer(None, None, ActiveVersions())
        payload = event()
        mutate(payload)
        incoming = message(payload)
        await consumer.receive(incoming)
        incoming.ack.assert_awaited_once()
        assert not consumer._pending

    asyncio.run(run())
    assert "Invalid prompt activation event ignored" in caplog.text
    assert "SECRET" not in caplog.text


def test_event_fields_match_existing_schema():
    root = Path(__file__).resolve().parents[4]
    contract = json.loads(
        (root / "contracts/events/model.version.activated.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    schema = ActivationEnvelope.model_json_schema()
    assert set(schema["$defs"]["ActivationData"]["required"]) == set(contract["required"])
    assert set(schema["$defs"]["ActivationData"]["properties"]) == set(contract["properties"])
    assert ActivationEnvelope.model_validate(event()).data.revision == 2
