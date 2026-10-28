import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from app.generation.codec import ReportV1Codec
from app.generation.consumer import GenerationConsumer
from app.generation.locking import JobLocks
from app.generation.models import ReportEvent, ReportStatus, WeeklyReport
from app.generation.service import GenerationService
from app.generation.unconfigured import UnconfiguredGenerator
from app.messaging.contracts import InvalidEvent, ReceivedEnvelope
from app.messaging.envelope import EventEnvelope
from tests.report_helpers import EmptyGenerator, command_for
from tests.test_consumer import FakeMessage, run
from tests.test_generation import stored


def wire(student_id):
    command = command_for(student_id)
    return EventEnvelope(
        type="report.generate",
        source="core-service",
        subject=str(student_id),
        dataschema="report.generate.v1",
        data={
            "jobId": str(command.job_id),
            "studentId": str(student_id),
            "periodFrom": command.period_from.isoformat(),
            "periodTo": command.period_to.isoformat(),
            "trigger": command.trigger,
            "narrativeEnabled": command.narrative_enabled,
        },
    ).model_dump(mode="json")


def validate_contract(body):
    root = Path(__file__).resolve().parents[3] / "contracts/events"
    for file, value in [
        ("envelope.schema.json", body),
        (body["dataschema"] + ".schema.json", body["data"]),
    ]:
        schema = json.loads((root / file).read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


@pytest.mark.parametrize("status", list(ReportStatus))
def test_real_shared_input_and_output_contracts(status):
    body = wire(uuid4())
    validate_contract(body)
    envelope = ReceivedEnvelope.model_validate_json(json.dumps(body))
    codec = ReportV1Codec()
    command = codec.decode(envelope)
    assert command.requested_at == envelope.time
    report = WeeklyReport(
        uuid4(),
        command.job_id,
        command.student_id,
        command.period_from,
        command.period_to,
        1,
        status,
        None,
    )
    event_type = {
        "RUNNING": "report.started",
        "COMPLETED": "report.completed",
        "FAILED": "report.failed",
    }[status]
    result = codec.encode(
        ReportEvent(event_type, report, "GENERATION_FAILED" if status == "FAILED" else None),
        "trace",
    )
    validate_contract(result.model_dump(mode="json"))
    assert result.data["reportId"] != result.data["jobId"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("narrativeEnabled", "false"),
        ("narrativeEnabled", 1),
        ("jobId", "wrong"),
        ("periodFrom", "2026-10-20"),
        ("periodTo", "2026-10-26"),
        ("trigger", "RETRY"),
        ("studentId", str(uuid4())),
        ("nickname", "private"),
    ],
)
def test_payload_contract_errors_go_directly_to_dlq(field, value):
    body = wire(uuid4())
    body["data"][field] = value
    message = FakeMessage(json.dumps(body).encode())

    async def handler(envelope):
        ReportV1Codec().decode(envelope)

    channel = run(message, handler)
    assert message.rejected and not message.acked
    assert not channel.default_exchange.published


@pytest.mark.parametrize("field", ["id", "time", "specversion", "dataschema", "source"])
def test_missing_wire_fields_are_not_filled_from_defaults(field):
    body = wire(uuid4())
    del body[field]
    message = FakeMessage(json.dumps(body).encode())

    async def forbidden(_):
        pytest.fail("Invalid envelope reached handler")

    channel = run(message, forbidden)
    assert message.rejected and not channel.default_exchange.published


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "other-service"),
        ("dataschema", "report.generate.v2"),
        ("subject", str(uuid4())),
    ],
)
def test_producer_and_student_identity_must_match(field, value):
    body = wire(uuid4())
    body[field] = value
    with pytest.raises(InvalidEvent):
        ReportV1Codec().decode(ReceivedEnvelope.model_validate_json(json.dumps(body)))


def test_malformed_time_and_unknown_envelope_fields_are_rejected():
    for field, value in [("time", "2026-10-28T01:00:00"), ("extra", "private"), ("id", "bad")]:
        body = wire(uuid4())
        body[field] = value
        message = FakeMessage(json.dumps(body).encode())
        channel = run(message, lambda _: pytest.fail("invalid input"))
        assert message.rejected and not channel.default_exchange.published


@pytest.mark.parametrize("configured", [True, False])
def test_shared_codec_pipeline_is_idempotent_and_unconfigured_is_not_success(
    report_factory, db_engine, report_student_id, configured
):
    body = wire(report_student_id)
    codec = ReportV1Codec()
    generator = EmptyGenerator() if configured else UnconfiguredGenerator()
    handler = GenerationConsumer(
        GenerationService(report_factory, JobLocks(db_engine), generator, codec), codec
    )

    async def scenario():
        for _ in range(2):
            await handler(ReceivedEnvelope.model_validate_json(json.dumps(body)))

    asyncio.run(scenario())
    reports, events = stored(report_factory, report_student_id)
    assert len(reports) == 1 and len(events) == 2
    assert reports[0]["status"] == ("COMPLETED" if configured else "FAILED")
    if not configured:
        assert reports[0]["failure_reason"] == "GENERATOR_NOT_CONFIGURED"
    for event in events:
        validate_contract(event["payload"])


def test_failure_event_rejects_exception_text():
    command = command_for(uuid4())
    report = WeeklyReport(
        uuid4(),
        command.job_id,
        command.student_id,
        command.period_from,
        command.period_to,
        1,
        ReportStatus.FAILED,
        None,
    )
    with pytest.raises(ValueError):
        ReportV1Codec().encode(ReportEvent("report.failed", report, "private student text"), None)
    with pytest.raises(ValueError):
        ReportV1Codec().encode(ReportEvent("report.completed", report), None)
