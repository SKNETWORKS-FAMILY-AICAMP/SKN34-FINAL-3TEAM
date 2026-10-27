"""Integration boundaries. The production message codec awaits #42's shared schemas."""

from typing import Any, Protocol

from app.generation.models import GenerateReport, GenerationResult, ReportEvent, WeeklyReport
from app.messaging.envelope import EventEnvelope


class ReportGenerator(Protocol):
    async def generate(self, command: GenerateReport, report: WeeklyReport) -> GenerationResult:
        """R2-R4 supply calculation, narrative and rendering; no production dummy result."""
        ...


class ReportEventCodec(Protocol):
    def decode(self, envelope: EventEnvelope[dict[str, Any]]) -> GenerateReport: ...

    def encode(
        self, event: ReportEvent, traceparent: str | None
    ) -> EventEnvelope[dict[str, Any]]: ...
