"""OTLP trace export and W3C traceparent helpers for event handling (아키텍처 4.6).

Export starts only with OTEL_TRACES_EXPORTER=otlp (app-service chart tracing.enabled). Otherwise the
OpenTelemetry API stays a no-op and the received traceparent is passed along unchanged.
"""

import os

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

TRACEPARENT = "traceparent"
_PROPAGATOR = TraceContextTextMapPropagator()

tracer = trace.get_tracer("app.report")


def configure() -> None:
    """Install the SDK exporter; endpoint and service name come from OTEL_* environment values."""
    if os.environ.get("OTEL_TRACES_EXPORTER") != "otlp":
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create())
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)


def shutdown() -> None:
    """Flush queued spans; a no-op provider has nothing to flush."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()


def parent_context(traceparent: str | None) -> Context | None:
    """Context whose parent is the stored traceparent; malformed values start a new trace."""
    return _PROPAGATOR.extract({TRACEPARENT: traceparent}) if traceparent else None


def current_traceparent() -> str | None:
    carrier: dict[str, str] = {}
    _PROPAGATOR.inject(carrier)
    return carrier.get(TRACEPARENT)
