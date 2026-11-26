"""OTLP trace/metric export and W3C traceparent helpers for event handling (아키텍처 4.6·4.7).

Export starts only with OTEL_TRACES_EXPORTER=otlp (app-service chart tracing.enabled). Otherwise the
OpenTelemetry API stays a no-op and the received traceparent is passed along unchanged.
Metrics share that switch (#1031): the chart sets no OTEL_METRICS_EXPORTER for non-Java services.
"""

import os

from opentelemetry import metrics, trace
from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

TRACEPARENT = "traceparent"
_PROPAGATOR = TraceContextTextMapPropagator()

tracer = trace.get_tracer("app.report")
meter = metrics.get_meter("app.report")

# #1031: one decision per weekly report explanation stage. Only the state label, never IDs or text.
EXPLANATION_STATES = ("INCLUDED", "NOT_INCLUDED", "NO_TARGET")
explanation_states = meter.create_counter(
    "report.explanation.state",
    unit="{report}",
    description="Weekly report explanation stage results by state",
)


def record_explanation_state(state: str) -> None:
    explanation_states.add(1, {"state": state})


def configure() -> None:
    """Install the SDK exporter; endpoint and service name come from OTEL_* environment values."""
    if os.environ.get("OTEL_TRACES_EXPORTER") != "otlp":
        return
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create()
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))
    start_explanation_series()


def start_explanation_series() -> None:
    """Export every state from 0 so the first decision after a restart counts in increase()."""
    for state in EXPLANATION_STATES:
        explanation_states.add(0, {"state": state})


def shutdown() -> None:
    """Flush queued spans and metrics; a no-op provider has nothing to flush."""
    for provider in (trace.get_tracer_provider(), metrics.get_meter_provider()):
        if hasattr(provider, "shutdown"):
            provider.shutdown()


def parent_context(traceparent: str | None) -> Context | None:
    """Context whose parent is the stored traceparent; malformed values start a new trace."""
    return _PROPAGATOR.extract({TRACEPARENT: traceparent}) if traceparent else None


def current_traceparent() -> str | None:
    carrier: dict[str, str] = {}
    _PROPAGATOR.inject(carrier)
    return carrier.get(TRACEPARENT)
