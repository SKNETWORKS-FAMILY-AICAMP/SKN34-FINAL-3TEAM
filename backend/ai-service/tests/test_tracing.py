"""ai-service trace·HTTP 지표 (#1029): no-op 기본값, traceparent 부모·전파, 원문 없는 속성."""

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langfuse import Langfuse
from opentelemetry import trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from app import tracing
from app.bootstrap import create_app
from app.http_telemetry import DURATION, HttpTelemetryMiddleware
from app.llm import base as llm_base
from app.llm.base import LlmError, LlmUnavailable, LlmUsage, UnconfiguredLlm
from app.messaging.consumer import ModelVersionConsumer
from app.messaging.publisher import UsagePublisher
from app.prompt_versions.registry import ActiveVersions
from app.prompt_versions.service import PromptSync
from app.security import UserContext
from tests.llm.test_base import Answer, ScriptedLlm
from tests.messaging.test_model_version_consumer import event, message

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
PARENT_ID = "00f067aa0ba902b7"
TRACEPARENT = f"00-{TRACE_ID}-{PARENT_ID}-01"
PRIVATE = "private-student-answer"
STUDENT = "private-student-id"


class Telemetry:
    def __init__(self) -> None:
        self.spans = InMemorySpanExporter()
        self.reader = InMemoryMetricReader()
        self.tracer_provider = TracerProvider()
        self.tracer_provider.add_span_processor(SimpleSpanProcessor(self.spans))
        self.meter_provider = MeterProvider(metric_readers=[self.reader])

    def finished(self, kind: SpanKind | None = None):
        spans = self.spans.get_finished_spans()
        return [span for span in spans if kind is None or span.kind == kind]

    def points(self, name: str):
        data = self.reader.get_metrics_data()
        return [
            point
            for resource in (data.resource_metrics if data else [])
            for scope in resource.scope_metrics
            for metric in scope.metrics
            if metric.name == name
            for point in metric.data.data_points
        ]


@pytest.fixture
def telemetry():
    state = Telemetry()
    tracing.install(state.tracer_provider, state.meter_provider)
    try:
        yield state
    finally:
        tracing.install()


def dumped(spans) -> str:
    return json.dumps([dict(span.attributes) for span in spans] + [s.name for s in spans])


# ---- provider 설치


def test_configure_without_exporter_values_stays_noop(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)
    tracing.configure()
    assert (tracing._tracer_provider, tracing._meter_provider) == (None, None)
    # no-op에서는 받은 traceparent를 그대로 넘김 (report-service와 같은 규칙)
    with tracing.tracer().start_as_current_span("x", context=tracing.parent_context(TRACEPARENT)):
        assert tracing.current_traceparent() == TRACEPARENT
    assert tracing.current_traceparent() is None


@pytest.mark.parametrize(
    ("traces", "metrics", "expected"),
    [
        ("otlp", "none", (True, False)),
        ("none", "otlp", (False, True)),
        ("otlp", "otlp", (True, True)),
    ],
)
def test_configure_installs_only_requested_exporters_without_global(
    monkeypatch, traces, metrics, expected
) -> None:
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", traces)
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", metrics)
    global_provider = trace.get_tracer_provider()
    try:
        tracing.configure()
        installed = (tracing._tracer_provider, tracing._meter_provider)
        assert tuple(provider is not None for provider in installed) == expected
        # 전역 provider(Langfuse가 쓰는 자리)는 건드리지 않음
        assert trace.get_tracer_provider() is global_provider
    finally:
        tracing.install()  # 시험에서는 Collector로 보내지 않고 버림


# ---- HTTP 서버 span·지표


def items_app() -> TestClient:
    app = FastAPI()

    @app.get("/internal/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        assert tracing.current_traceparent() is not None
        return {"ok": "yes"}

    @app.get("/internal/boom/{item_id}")
    async def boom(item_id: str) -> None:
        raise RuntimeError(PRIVATE)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "UP"}

    app.add_middleware(HttpTelemetryMiddleware)
    return TestClient(app, raise_server_exceptions=False)


def test_http_server_span_uses_traceparent_and_route_template(telemetry) -> None:
    with items_app() as client:
        assert (
            client.get(
                f"/internal/items/{STUDENT}?q={PRIVATE}", headers={"traceparent": TRACEPARENT}
            ).status_code
            == 200
        )
    [span] = telemetry.finished(SpanKind.SERVER)
    assert span.name == "GET /internal/items/{item_id}"
    assert f"{span.context.trace_id:032x}" == TRACE_ID
    assert f"{span.parent.span_id:016x}" == PARENT_ID
    assert span.attributes["http.route"] == "/internal/items/{item_id}"
    assert span.attributes["http.response.status_code"] == 200
    assert STUDENT not in dumped([span]) and PRIVATE not in dumped([span])
    [point] = telemetry.points(DURATION)
    assert point.count == 1
    assert dict(point.attributes) == {
        "http.request.method": "GET",
        "http.response.status_code": 200,
        "http.route": "/internal/items/{item_id}",
    }


def test_http_server_error_marks_span_without_exception_text(telemetry) -> None:
    with items_app() as client:
        assert client.get("/internal/boom/x").status_code == 500
        assert client.get("/nowhere").status_code == 404
        assert client.get("/health/live").status_code == 200
    boom, missing = telemetry.finished(SpanKind.SERVER)
    assert boom.status.status_code == StatusCode.ERROR
    assert boom.attributes["error.type"] == "RuntimeError"
    assert not boom.events  # 예외 메시지를 span event로 남기지 않음
    assert PRIVATE not in dumped([boom])
    # 맞는 경로가 없으면 경로 값 대신 메서드만
    assert missing.name == "GET" and "http.route" not in missing.attributes
    statuses = sorted(p.attributes["http.response.status_code"] for p in telemetry.points(DURATION))
    assert statuses == [404, 500]  # /health는 재지 않음


def test_app_registers_http_telemetry_outermost() -> None:
    assert create_app().user_middleware[0].cls is HttpTelemetryMiddleware


# ---- 이벤트 소비·결과 이벤트 전파


def test_consumer_span_parent_is_envelope_traceparent(telemetry) -> None:
    async def run():
        consumer = ModelVersionConsumer(None, PromptSync(None, ActiveVersions()))
        await consumer.receive(message({**event(), "traceparent": TRACEPARENT}))
        broken = event()
        broken.pop("id")
        await consumer.receive(message(broken))

    asyncio.run(run())
    ok, invalid = telemetry.finished(SpanKind.CONSUMER)
    assert ok.name == "model.version.activated process"
    assert f"{ok.parent.span_id:016x}" == PARENT_ID
    assert ok.status.status_code == StatusCode.UNSET
    assert invalid.parent is None
    assert invalid.attributes["error.type"] == "INVALID_EVENT"


def test_usage_event_and_downstream_headers_follow_current_span(telemetry) -> None:
    published = []

    class Capture:
        async def publish(self, envelope, routing_key):
            published.append(envelope)
            return True

    context = UserContext(STUDENT, "STUDENT", frozenset({STUDENT}), TRACEPARENT)
    with tracing.tracer().start_as_current_span("s", context=tracing.parent_context(TRACEPARENT)):
        current = tracing.current_traceparent()
        headers = context.to_headers()
        asyncio.run(
            UsagePublisher(Capture(), service="ai", source="ai-service").publish(
                "JUDGMENT", "m", input_tokens=1, output_tokens=1, latency_ms=1, success=True
            )
        )
    assert current != TRACEPARENT and TRACE_ID in current
    assert headers["traceparent"] == current
    assert published[0].traceparent == current
    # span 밖이면 받은 값 그대로
    assert context.to_headers()["traceparent"] == TRACEPARENT


# ---- LlmClient span


def test_llm_attempt_spans_have_metadata_only(telemetry, monkeypatch) -> None:
    monkeypatch.setattr(llm_base, "current_user_context", lambda: None)
    seen: list[tuple[LlmUsage, str | None]] = []
    llm = ScriptedLlm([LlmError("LLM_TIMEOUT", retryable=True), Answer(value=PRIVATE)])
    llm._recorder = lambda usage: seen.append((usage, tracing.current_traceparent()))

    async def run():
        with tracing.tracer().start_as_current_span(
            "server", context=tracing.parent_context(TRACEPARENT)
        ):
            return await llm.generate(
                system="private-system-prompt",
                user=PRIVATE,
                output=Answer,
                call_type="JUDGMENT",
                prompt_version="judge@1",
            )

    assert asyncio.run(run()).data.value == PRIVATE
    failed, succeeded = telemetry.finished(SpanKind.CLIENT)
    server = telemetry.finished(SpanKind.INTERNAL)[0]
    assert failed.name == succeeded.name == "llm JUDGMENT"
    assert all(span.parent.span_id == server.context.span_id for span in (failed, succeeded))
    assert (failed.attributes["llm.attempt"], succeeded.attributes["llm.attempt"]) == (1, 2)
    assert failed.status.status_code == StatusCode.ERROR
    assert failed.attributes["error.type"] == "LLM_TIMEOUT"
    assert succeeded.status.status_code == StatusCode.UNSET
    assert succeeded.attributes["llm.prompt_version"] == "judge@1"
    assert succeeded.attributes["gen_ai.response.model"] == "fake-model"
    assert succeeded.attributes["gen_ai.usage.input_tokens"] == 10
    text = dumped([failed, succeeded])
    assert PRIVATE not in text and "private-system-prompt" not in text
    # 사용량 이벤트 traceparent는 그 시도 span
    assert [tp.split("-")[2] for _, tp in seen] == [
        f"{failed.context.span_id:016x}",
        f"{succeeded.context.span_id:016x}",
    ]


@pytest.mark.parametrize("streaming", [False, True])
def test_final_llm_failure_keeps_error_code(telemetry, streaming) -> None:
    llm = UnconfiguredLlm("gpt", lambda usage: None)

    async def run():
        if streaming:
            async for _ in llm.stream(
                system="s", user="u", call_type="ANALYSIS", prompt_version="a@1"
            ):
                pass
        else:
            await llm.generate(
                system="s", user="u", output=Answer, call_type="FOLLOWUP", prompt_version="f@1"
            )

    with pytest.raises(LlmUnavailable):
        asyncio.run(run())
    [span] = telemetry.finished(SpanKind.CLIENT)
    assert span.attributes["error.type"] == "LLM_NOT_CONFIGURED"
    assert span.status.status_code == StatusCode.ERROR


def test_unexpected_llm_failure_ends_span_with_error(telemetry) -> None:
    llm = ScriptedLlm([])  # 단계가 없어 IndexError

    with pytest.raises(IndexError):
        asyncio.run(
            llm.generate(
                system="s", user="u", output=Answer, call_type="FOLLOWUP", prompt_version="f@1"
            )
        )
    [span] = telemetry.finished(SpanKind.CLIENT)
    assert span.attributes["error.type"] == "IndexError"


# ---- Langfuse 공존


def test_langfuse_and_app_spans_stay_on_separate_exporters(telemetry, monkeypatch) -> None:
    monkeypatch.setattr(
        llm_base,
        "current_user_context",
        lambda: UserContext(STUDENT, "STUDENT", frozenset({STUDENT}), TRACEPARENT),
    )
    langfuse_spans = InMemorySpanExporter()
    client = Langfuse(
        public_key="pk-issue1029-test",
        secret_key="sk-issue1029-test",
        span_exporter=langfuse_spans,
        should_export_span=lambda span: span.instrumentation_scope.name == "langfuse-sdk",
    )
    try:
        llm = ScriptedLlm([Answer(value="ok")])
        llm.langfuse = client
        asyncio.run(
            llm.generate(
                system="s",
                user=PRIVATE,
                output=Answer,
                call_type="JUDGMENT",
                prompt_version="judge@1",
            )
        )
        client.flush()
        [generation] = langfuse_spans.get_finished_spans()
        [app_span] = telemetry.finished()
        assert generation.instrumentation_scope.name == "langfuse-sdk"
        assert f"{generation.parent.span_id:016x}" == PARENT_ID  # Langfuse 부모는 이전과 같음
        assert app_span.instrumentation_scope.name == tracing.SCOPE
    finally:
        client.shutdown()
