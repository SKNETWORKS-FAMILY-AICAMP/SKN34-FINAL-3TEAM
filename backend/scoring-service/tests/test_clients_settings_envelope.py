"""#140: 내부 권한 전달·설정·공통 이벤트 봉투 계약의 공백 보강."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from app import config, security
from app.clients.base import internal_client
from app.messaging.envelope import EventEnvelope


@pytest.fixture
def settings_cache():
    config.get_settings.cache_clear()
    try:
        yield
    finally:
        config.get_settings.cache_clear()


def transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(handler))
    )


def test_shared_http_client_uses_each_tasks_scope_trace_and_internal_token(
    monkeypatch, settings_cache
):
    seen = []

    async def handle(request):
        await asyncio.sleep(0)
        seen.append(request)
        return httpx.Response(200)

    transport(monkeypatch, handle)

    async def scenario():
        async with internal_client("http://core.test") as http:

            async def call(user, student, trace):
                token = security.bind_user_context(
                    security.UserContext(user, "SYSTEM", frozenset([student]), trace)
                )
                try:
                    await http.get("/internal/probe/" + student)
                finally:
                    security._current.reset(token)

            await asyncio.gather(call("u-a", "s-a", "trace-a"), call("u-b", "s-b", "trace-b"))
            await http.get("/internal/probe/no-context")
        assert http.is_closed

    asyncio.run(scenario())
    by_path = {r.url.path.rsplit("/", 1)[-1]: r for r in seen}
    for suffix in ("a", "b"):
        request = by_path["s-" + suffix]
        assert request.headers["X-User-Id"] == "u-" + suffix
        assert request.headers["X-User-Role"] == "SYSTEM"
        assert request.headers["X-Student-Scope"] == "s-" + suffix
        assert request.headers["traceparent"] == "trace-" + suffix
    assert "X-Student-Scope" not in by_path["no-context"].headers
    assert "X-User-Id" not in by_path["no-context"].headers
    assert all(r.headers["X-Internal-Token"] == "test-token" for r in seen)


@pytest.mark.parametrize("failure", ["status", "timeout"])
def test_http_errors_do_not_retry_and_timeouts_use_configuration(
    monkeypatch, settings_cache, failure
):
    monkeypatch.setenv("HTTP_CONNECT_TIMEOUT", "0.7")
    monkeypatch.setenv("HTTP_READ_TIMEOUT", "4.5")
    seen = []

    def handle(request):
        seen.append(request)
        assert request.extensions["timeout"]["connect"] == 0.7
        assert request.extensions["timeout"]["read"] == 4.5
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return httpx.Response(503)

    transport(monkeypatch, handle)

    async def scenario():
        async with internal_client("http://core.test") as http:
            with pytest.raises(
                httpx.ReadTimeout if failure == "timeout" else httpx.HTTPStatusError
            ):
                response = await http.get("/internal/probe")
                response.raise_for_status()

    asyncio.run(scenario())
    assert len(seen) == 1


def test_settings_environment_types_and_cached_snapshot(monkeypatch, settings_cache, tmp_path):
    monkeypatch.setenv("CORE_URL", "http://core.synthetic:8080")
    monkeypatch.setenv("S3_BUCKET", "synthetic-models")
    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("MODEL_RETRY_INTERVAL", "0.25")
    first = config.get_settings()
    assert first.core_url == "http://core.synthetic:8080" and first.s3_bucket == "synthetic-models"
    assert first.model_cache_dir == tmp_path / "models" and first.model_retry_interval == 0.25
    monkeypatch.setenv("CORE_URL", "http://changed.synthetic")
    assert config.get_settings() is first
    config.get_settings.cache_clear()
    assert config.get_settings().core_url == "http://changed.synthetic"


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_invalid_model_retry_setting_is_rejected(monkeypatch, settings_cache, value):
    monkeypatch.setenv("MODEL_RETRY_INTERVAL", value)
    with pytest.raises(ValidationError):
        config.get_settings()


def test_internal_token_is_required(monkeypatch, settings_cache):
    monkeypatch.delenv("INTERNAL_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        config.get_settings()


def envelope(**changes):
    return EventEnvelope[dict](
        type="llm.usage.recorded",
        source="scoring-service",
        dataschema="llm.usage.recorded.v1",
        data={"synthetic": True},
        **changes,
    )


def test_envelope_defaults_and_round_trip_match_shared_json_schema():
    first, second = envelope(), envelope()
    assert UUID(first.id) != UUID(second.id)
    assert first.time.utcoffset() is not None
    payload = first.model_dump(mode="json")
    schema = Path(__file__).resolve().parents[3] / "contracts/events/envelope.schema.json"
    Draft202012Validator(
        json.loads(schema.read_text(encoding="utf-8")), format_checker=FormatChecker()
    ).validate(payload)
    restored = EventEnvelope[dict].model_validate(payload)
    assert restored == first and isinstance(restored.time, datetime)


@pytest.mark.parametrize("field", ["type", "source", "dataschema", "data"])
def test_envelope_required_fields_are_not_silently_invented(field):
    payload = envelope().model_dump(mode="json")
    del payload[field]
    with pytest.raises(ValidationError):
        EventEnvelope[dict].model_validate(payload)


@pytest.mark.parametrize("field,value", [("time", "not-a-date"), ("data", "not-an-object")])
def test_envelope_rejects_invalid_typed_values(field, value):
    payload = envelope().model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValidationError):
        EventEnvelope[dict].model_validate(payload)
