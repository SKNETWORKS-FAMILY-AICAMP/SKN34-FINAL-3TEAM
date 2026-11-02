import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.messaging.consumer import ActivationEnvelope, ModelVersionConsumer
from app.model_registry import ModelRegistry
from app.model_startup import ModelStartup
from tests.test_model_registry import SCOPE, loaded, version


async def until(predicate):
    for _ in range(500):
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition not reached")


def event(revision=2, **changes):
    data = version(revision).model_dump(mode="json", by_alias=True)
    data["previousVersionId"] = None
    data.update(changes)
    return {
        "id": str(uuid4()),
        "specversion": "1.0",
        "type": "model.version.activated",
        "source": "core-service",
        "time": "2026-10-29T00:00:00Z",
        "dataschema": "model.version.activated.v1",
        "data": data,
    }


def test_buffer_during_snapshot_and_loading_latest_revision_wins():
    async def run():
        requested, release = asyncio.Event(), asyncio.Event()
        entered, finish = threading.Event(), threading.Event()

        class Core:
            async def active_versions(self):
                requested.set()
                await release.wait()
                return [version(1)]

        def loader(item):
            if item.revision == 3:
                entered.set()
                assert finish.wait(5)
            return loaded(item)

        registry = ModelRegistry(loader)
        startup = ModelStartup(Core(), registry, 0.01)
        startup.start()
        try:
            await requested.wait()
            startup.offer(version(3))
            startup.offer(version(2))
            release.set()
            await until(entered.is_set)
            assert not startup.ready
            startup.offer(version(4))
            finish.set()
            await until(lambda: startup.ready)
            assert registry.versions()[0]["revision"] == 4
            startup.offer(version(2))
            await until(lambda: not startup._pending)
            assert registry.versions()[0]["revision"] == 4
        finally:
            finish.set()
            await startup.close()

    asyncio.run(run())


def test_event_failure_keeps_old_model_then_retries_and_rollback_redownloads(caplog):
    async def run():
        calls, fail = [], True

        def loader(item):
            calls.append(item.version)
            if item.revision == 2 and fail:
                raise OSError("SECRET model content")
            return loaded(item)

        core = SimpleNamespace(active_versions=AsyncMock(return_value=[version(1)]))
        registry = ModelRegistry(loader)
        startup = ModelStartup(core, registry, 0.01)
        startup.start()
        try:
            await until(lambda: startup.ready)
            startup.offer(version(2))
            await until(lambda: len(calls) >= 2)
            assert startup.ready
            assert registry.get("m2-klue-narrative", SCOPE).metadata.revision == 1
            fail = False
            await until(lambda: registry.versions()[0]["revision"] == 2)
            startup.offer(version(3, release="1.1"))
            await until(lambda: registry.versions()[0]["revision"] == 3)
            assert calls.count("1.1") == 2
            assert core.active_versions.await_count == 1
        finally:
            await startup.close()

    asyncio.run(run())
    assert "SECRET" not in caplog.text


@pytest.mark.parametrize(
    "kind,name,target",
    [
        ("MODEL", "m2-klue-narrative", True),
        ("MODEL", "m1-math", True),
        ("MODEL", "other", False),
        ("PROMPT", "judge", False),
        ("RUBRIC", "rubric", False),
        ("GENERATION", "mission", False),
    ],
)
def test_event_filter_and_ack(kind, name, target):
    async def run():
        startup = ModelStartup(None, ModelRegistry(loaded), 0.01)
        message = SimpleNamespace(
            body=json.dumps(event(kind=kind, name=name)).encode(), ack=AsyncMock()
        )
        await ModelVersionConsumer.receive(message, startup)
        assert bool(startup._pending) == target
        message.ack.assert_awaited_once()

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda e: e.pop("id"),
        lambda e: e.update(id="bad"),
        lambda e: e.update(specversion="2.0"),
        lambda e: e.pop("time"),
        lambda e: e.update(dataschema="model.version.activated.v2"),
        lambda e: e["data"].pop("previousVersionId"),
        lambda e: e["data"].update(revision=True),
        lambda e: e["data"].update(scopes=[SCOPE, SCOPE]),
        lambda e: e["data"].update(artifactUri=None),
        lambda e: e["data"].update(unexpected="SECRET"),
    ],
)
def test_invalid_events_discarded_without_retry_or_payload_log(mutation, caplog):
    async def run():
        payload = event()
        mutation(payload)
        startup = ModelStartup(None, ModelRegistry(loaded), 0.01)
        message = SimpleNamespace(body=json.dumps(payload).encode(), ack=AsyncMock())
        await ModelVersionConsumer.receive(message, startup)
        assert not startup._pending
        message.ack.assert_awaited_once()

    asyncio.run(run())
    assert "Invalid model activation event ignored" in caplog.text
    assert "SECRET" not in caplog.text


def test_event_contract_schema_fields_and_example():
    root = Path(__file__).resolve().parents[3]
    # production validator must keep the externally defined required fields and names.
    contract = json.loads(
        (root / "contracts/events/model.version.activated.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    schema = ActivationEnvelope.model_json_schema()
    data_schema = schema["$defs"]["ActivationData"]
    assert set(contract["required"]) == set(data_schema["required"])
    assert set(contract["properties"]) == set(data_schema["properties"])
    assert data_schema["additionalProperties"] is False
    assert ActivationEnvelope.model_validate(event()).data.revision == 2


def test_failed_model_does_not_block_another_model_update():
    async def run():
        def loader(item):
            if item.name == "m2-klue-narrative" and item.revision == 2:
                raise OSError("missing artifact")
            return loaded(item)

        registry = ModelRegistry(loader)
        core = SimpleNamespace(active_versions=AsyncMock(return_value=[version(1)]))
        startup = ModelStartup(core, registry, 0.01)
        startup.start()
        try:
            await until(lambda: startup.ready)
            startup.offer(version(2))
            startup.offer(version(2, name="m2-klue-essay"))
            await until(lambda: registry.is_active("m2-klue-essay", SCOPE))
            assert registry.get("m2-klue-narrative", SCOPE).metadata.revision == 1
            assert registry.get("m2-klue-essay", SCOPE).metadata.revision == 2
            assert startup.ready
        finally:
            await startup.close()

    asyncio.run(run())


def test_bind_before_snapshot_and_reconnect_creates_new_queue():
    async def run():
        order, receivers = [], []

        class Queue:
            name = "generated-exclusive"

            async def bind(self, exchange, **kwargs):
                assert kwargs == {"routing_key": "model.version.*", "robust": False}
                order.append("bind")

            async def consume(self, callback, **kwargs):
                receivers.append(callback)
                order.append("consume")

        class Channel:
            async def set_qos(self, **kwargs):
                pass

            async def get_exchange(self, name, **kwargs):
                assert name == "events.topic"
                return object()

            async def declare_queue(self, name, **kwargs):
                assert name == ""
                assert kwargs == {"exclusive": True, "auto_delete": True, "robust": False}
                order.append("declare")
                return Queue()

            async def close(self):
                order.append("close")

        connection = SimpleNamespace(close_callbacks=set(), channel=AsyncMock(side_effect=Channel))
        broker = SimpleNamespace(is_connected=True, connection=connection)

        class Core:
            async def active_versions(self):
                order.append("snapshot")
                return [version(1 if len(receivers) == 1 else 3)]

        registry = ModelRegistry(loaded)
        consumer = ModelVersionConsumer(broker, Core(), registry, 0.005)
        consumer.start()
        try:
            await until(lambda: registry.versions() != [])
            assert order[:4] == ["declare", "bind", "consume", "snapshot"]
            message = SimpleNamespace(body=json.dumps(event()).encode(), ack=AsyncMock())
            await receivers[0](message)
            await until(lambda: registry.versions()[0]["revision"] == 2)
            for callback in list(connection.close_callbacks):
                callback()
            assert not await consumer.is_ready()
            await until(lambda: registry.versions()[0]["revision"] == 3)
            assert len(receivers) == 2
            assert order.count("bind") == order.count("snapshot") == 2
            assert await consumer.is_ready()
        finally:
            await consumer.close()
        assert not connection.close_callbacks

    asyncio.run(run())
