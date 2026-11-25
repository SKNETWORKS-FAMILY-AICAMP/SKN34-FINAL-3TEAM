"""OTLP trace·지표 내보내기와 W3C traceparent 처리 (아키텍처 4.6·4.7, #1029).

- trace는 OTEL_TRACES_EXPORTER=otlp(app-service chart tracing.enabled), 지표는
  OTEL_METRICS_EXPORTER=otlp일 때만 SDK를 설치한다. 아니면 no-op이고 받은 traceparent를
  그대로 넘긴다(report-service app/tracing.py와 같은 규칙).
- provider는 전역에 등록하지 않는다. Langfuse(bootstrap)가 전역 TracerProvider를 쓰므로
  섞이면 Langfuse generation span이 Collector로, 앱 span이 Langfuse로 나간다.
  앱 계측은 tracer()·meter()로만 가져온다(#1030 품질 카운터도 meter()를 쓴다).
- span·지표 속성에 프롬프트·응답 원문, 학생 ID, 업무 ID를 넣지 않는다(NFR-SEC-05).
"""

import os
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

SCOPE = "app.ai"
TRACEPARENT = "traceparent"
_PROPAGATOR = TraceContextTextMapPropagator()
_NOOP_TRACER = trace.NoOpTracerProvider()
_NOOP_METER = metrics.NoOpMeterProvider()

_tracer_provider: Any = None
_meter_provider: Any = None


def configure() -> None:
    """OTEL_* 환경 값으로 exporter를 설치한다. endpoint·service name도 OTEL_* 값을 따른다."""
    if _tracer_provider is not None or _meter_provider is not None:
        return
    traces = os.environ.get("OTEL_TRACES_EXPORTER") == "otlp"
    metric = os.environ.get("OTEL_METRICS_EXPORTER") == "otlp"
    if not (traces or metric):
        return
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create()
    tracer_provider = meter_provider = None
    if traces:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    if metric:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        meter_provider = MeterProvider(
            resource=resource, metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())]
        )
    install(tracer_provider, meter_provider)


def install(tracer_provider: Any = None, meter_provider: Any = None) -> None:
    """앱 계측이 쓸 provider 지정. None이면 no-op. 시험은 메모리 exporter provider를 넣는다."""
    global _tracer_provider, _meter_provider
    _tracer_provider, _meter_provider = tracer_provider, meter_provider
    _instruments.clear()


def shutdown() -> None:
    """남은 span·지표를 보내고 provider를 내린다. no-op이면 할 일이 없다."""
    for provider in (_tracer_provider, _meter_provider):
        if provider is not None:
            provider.shutdown()
    install()


def tracer() -> trace.Tracer:
    return (_tracer_provider or _NOOP_TRACER).get_tracer(SCOPE)


def meter() -> metrics.Meter:
    return (_meter_provider or _NOOP_METER).get_meter(SCOPE)


_instruments: dict[str, Any] = {}


def instrument(name: str, factory: Any) -> Any:
    """현재 meter provider에서 이름당 한 번만 만든 계기. factory(meter)로 만든다."""
    if name not in _instruments:
        _instruments[name] = factory(meter())
    return _instruments[name]


def parent_context(traceparent: str | None) -> Context | None:
    """traceparent를 부모로 하는 context. 형식이 틀리면 새 trace로 시작한다."""
    return _PROPAGATOR.extract({TRACEPARENT: traceparent}) if traceparent else None


def current_traceparent() -> str | None:
    """현재 span의 traceparent. no-op이면 부모로 받은 값 그대로, span이 없으면 None."""
    carrier: dict[str, str] = {}
    _PROPAGATOR.inject(carrier)
    return carrier.get(TRACEPARENT)
