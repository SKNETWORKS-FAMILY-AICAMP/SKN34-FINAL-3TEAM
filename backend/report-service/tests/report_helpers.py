"""Synthetic test doubles; the codec here is NOT the #42 report message contract."""

from datetime import date
from uuid import uuid4

from app.generation.models import GenerateReport, GenerationResult, ReportState
from app.messaging.envelope import EventEnvelope
from app.security import current_user_context


def command_for(student_id):
    return GenerateReport(
        job_id=uuid4(),
        student_id=student_id,
        period_from=date(2026, 10, 19),
        period_to=date(2026, 10, 25),
        trigger="SCHEDULE",
        narrative_enabled=False,
    )


class FakeCodec:
    def __init__(self, command):
        self.command = command

    def decode(self, envelope):
        # Decoding the real payload is deliberately not implemented until #42.
        return self.command

    def encode(self, event, traceparent):
        return EventEnvelope(
            type=event.event_type,
            source="report-service",
            subject=str(event.report.student_id),
            dataschema=f"{event.event_type}.v1",
            traceparent=traceparent,
            data={"testOnlyReportId": str(event.report.id)},
        )


class EmptyGenerator:
    """Only tests use an empty generator; no production no-op can emit a false completion."""

    def __init__(self):
        self.calls = 0
        self.contexts = []

    async def generate(self, command, report):
        self.calls += 1
        self.contexts.append(current_user_context())
        return GenerationResult(ReportState.NO_RECORD, "synthetic empty generator")
