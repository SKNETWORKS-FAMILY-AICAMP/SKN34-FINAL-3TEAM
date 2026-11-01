"""#139: serve 대역 없이 실제 run → serve의 구독·relay·종료 조립을 검증한다."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest

from app import worker
from app.generation.pipeline import NamedGenerator


@pytest.mark.parametrize("pipeline_failure", [False, True])
def test_default_run_wires_configured_clients_queues_relay_and_releases_resources(
    monkeypatch, pipeline_failure
):
    events, clients, handlers, captured = [], {}, [], {}
    factory = object()

    class Broker:
        is_connected = True

        def __init__(self, url):
            captured["broker_url"] = url

        def start(self):
            events.append("broker-start")

        async def close(self):
            events.append("broker-close")

    class Publisher:
        def __init__(self, amqp):
            captured["publisher_broker"] = amqp

        async def close(self):
            events.append("publisher-close")

    class Relay:
        def __init__(self, sessions, publisher):
            assert sessions is factory and isinstance(publisher, Publisher)

        async def publish_once(self):
            events.append("relay")
            return False

    class Consumer:
        def __init__(self, amqp, retries, prefetch):
            assert isinstance(amqp, Broker)
            assert (retries, prefetch) == (3, 1)

        async def consume(self, queue, handler):
            handlers.append(queue)
            events.append("subscribe:" + queue)
            await asyncio.sleep(0)  # 실제 serve의 relay 태스크를 실행한다.
            if len(handlers) == 2:
                # run이 등록한 실제 종료 신호 callback을 사용한다.
                captured["stop"]()

            async def stop():
                events.append("stop:" + queue)

            async def close():
                events.append("close:" + queue)

            return SimpleNamespace(stop=stop, close=close)

    @asynccontextmanager
    async def http(url):
        async with httpx.AsyncClient(base_url=url) as client:
            clients[url] = client
            try:
                yield client
            finally:
                events.append("http-close:" + url)

    def pipeline(provider, learning, ai, storage):
        assert provider._client is clients["http://core.test"]
        assert learning._client is clients["http://learning.test"]
        assert ai._client is clients["http://ai.test"]
        assert storage is captured["storage"]
        if pipeline_failure:
            raise RuntimeError("synthetic pipeline startup failure")
        return original_pipeline(provider, learning, ai, storage)

    engine = SimpleNamespace(dispose=lambda: events.append("engine-dispose"))
    captured["storage"] = SimpleNamespace(close=lambda: events.append("storage-close"))
    original_pipeline = worker.build_pipeline
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(
            rabbitmq_url="amqp://synthetic",
            core_url="http://core.test",
            learning_url="http://learning.test",
            ai_url="http://ai.test",
            consumer_max_retries=3,
            consumer_prefetch=1,
        ),
    )
    monkeypatch.setattr(worker, "AmqpConnection", Broker)
    monkeypatch.setattr(worker, "EventPublisher", Publisher)
    monkeypatch.setattr(worker, "EventConsumer", Consumer)
    monkeypatch.setattr(worker, "OutboxRelay", Relay)
    monkeypatch.setattr(worker, "internal_client", http)
    monkeypatch.setattr(worker, "create_db_engine", lambda: engine)
    monkeypatch.setattr(worker, "create_session_factory", lambda _: factory)
    monkeypatch.setattr(worker.ObjectStorage, "configured", lambda: captured["storage"])
    monkeypatch.setattr(worker, "build_pipeline", pipeline)
    real_service = worker.GenerationService

    def service(sessions, locks, generator, codec):
        assert sessions is factory and isinstance(generator, NamedGenerator)
        return real_service(sessions, locks, generator, codec)

    monkeypatch.setattr(worker, "GenerationService", service)

    async def scenario():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(
            loop, "add_signal_handler", lambda sig, callback: captured.update(stop=callback)
        )
        await worker.run()

    if pipeline_failure:
        with pytest.raises(RuntimeError, match="synthetic pipeline"):
            asyncio.run(scenario())
        assert handlers == []
    else:
        asyncio.run(scenario())
        assert handlers == [worker.DELETION_QUEUE, worker.GENERATE_QUEUE]
        assert "relay" in events
        stop_positions = [events.index("stop:" + q) for q in handlers]
        close_positions = [events.index("close:" + q) for q in handlers]
        assert max(stop_positions) < min(close_positions)
        assert max(close_positions) < events.index("http-close:http://ai.test")
    assert len(clients) == 3 and all(x.is_closed for x in clients.values())
    assert events[-4:] == ["publisher-close", "broker-close", "storage-close", "engine-dispose"]


def test_run_rejects_ambiguous_generator_before_opening_any_resource(monkeypatch):
    def unexpected():
        raise AssertionError("must not create a DB")

    monkeypatch.setattr(worker, "create_db_engine", unexpected)
    with pytest.raises(ValueError, match="either"):
        asyncio.run(worker.run(object(), display_names=object()))
