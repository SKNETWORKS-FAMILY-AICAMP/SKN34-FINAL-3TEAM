"""#152: 실제 PostgreSQL·운영 codec/서비스, 생성기는 명시적인 합성 대역."""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.deletion.state import deletion_guard
from app.generation.codec import ReportV1Codec
from app.generation.consumer import GenerationConsumer
from app.generation.locking import JobLocks
from app.generation.models import (
    GenerationBusy,
    GenerationResult,
    ReportFile,
    ReportItem,
    ReportState,
)
from app.generation.repository import report_file, report_item
from app.generation.service import GenerationService
from app.messaging.contracts import ReceivedEnvelope
from app.outbox.repository import OutboxRepository
from tests.report_helpers import EmptyGenerator
from tests.test_generation import stored
from tests.test_report_codec import validate_contract, wire


class FailingGenerator(EmptyGenerator):
    async def generate(self, command, report):
        await super().generate(command, report)
        raise RuntimeError("합성 원문·비밀값은 결과에 포함하지 않음")


def handler(factory, engine, generator, outbox=None):
    codec = ReportV1Codec()
    return GenerationConsumer(
        GenerationService(factory, JobLocks(engine), generator, codec, outbox=outbox), codec
    )


async def deliver(target, body, *, fresh_id=False):
    value = deepcopy(body)
    if fresh_id:
        value["id"] = str(uuid4())
    await target(ReceivedEnvelope.model_validate_json(json.dumps(value)))


def retry_request(original, enabled=True):
    body = deepcopy(original)
    body["id"] = str(uuid4())
    body["data"].update(jobId=str(uuid4()), trigger="ADMIN_RETRY", narrativeEnabled=enabled)
    return body


def lifecycle(events, job):
    return [x for x in events if x["payload"]["data"]["jobId"] == job]


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("narrative", [False, True])
def test_new_admin_job_runs_and_terminal_redeliveries_are_noops(
    report_factory, db_engine, report_student_id, failure, narrative
):
    original = wire(report_student_id)
    retry = retry_request(original, narrative)
    seen = []

    class RetryGenerator(EmptyGenerator):
        async def generate(self, command, report):
            seen.append(command.narrative_enabled)
            result = await super().generate(command, report)
            if failure:
                raise RuntimeError("synthetic retry failure")
            return result

    generator = RetryGenerator()

    async def scenario():
        old = handler(report_factory, db_engine, FailingGenerator())
        await deliver(old, original)
        snapshot = dict(stored(report_factory, report_student_id)[0][0])
        current = handler(report_factory, db_engine, generator)
        await deliver(current, retry)
        await deliver(current, retry)
        await deliver(current, retry, fresh_id=True)
        await deliver(current, original, fresh_id=True)
        return snapshot

    snapshot = asyncio.run(scenario())
    reports, events = stored(report_factory, report_student_id)
    assert dict(reports[0]) == snapshot
    assert reports[1]["revision"] == 2 and reports[1]["id"] != reports[0]["id"]
    assert reports[1]["status"] == ("FAILED" if failure else "COMPLETED")
    assert generator.calls == 1
    assert seen == [narrative]
    current_events = lifecycle(events, retry["data"]["jobId"])
    assert [x["event_type"] for x in current_events] == [
        "report.started",
        "report.failed" if failure else "report.completed",
    ]
    assert len(lifecycle(events, original["data"]["jobId"])) == 2
    assert all(x["payload"]["data"]["reportId"] == str(reports[1]["id"]) for x in current_events)
    for event in events:
        validate_contract(event["payload"])
        assert "합성 원문" not in json.dumps(event["payload"], ensure_ascii=False)


def test_concurrent_retry_and_late_original_delivery_do_not_mix_executions(
    report_factory, db_engine, report_student_id
):
    original = wire(report_student_id)
    retry = retry_request(original)

    async def scenario():
        await deliver(handler(report_factory, db_engine, FailingGenerator()), original)
        entered, release = asyncio.Event(), asyncio.Event()

        class Slow(EmptyGenerator):
            async def generate(self, command, report):
                entered.set()
                await release.wait()
                return await super().generate(command, report)

        generator = Slow()
        first = handler(report_factory, db_engine, generator)
        second = handler(report_factory, db_engine, generator)
        task = asyncio.create_task(deliver(first, retry))
        try:
            await asyncio.wait_for(entered.wait(), 10)
            with pytest.raises(GenerationBusy):
                await deliver(second, retry, fresh_id=True)
            await deliver(second, original, fresh_id=True)
            reports, events = stored(report_factory, report_student_id)
            assert [r["status"] for r in reports] == ["FAILED", "RUNNING"]
            assert len(lifecycle(events, retry["data"]["jobId"])) == 1
        finally:
            release.set()
            await task
        await deliver(second, retry)
        assert generator.calls == 1

    asyncio.run(scenario())
    reports, events = stored(report_factory, report_student_id)
    assert [r["status"] for r in reports] == ["FAILED", "COMPLETED"]
    assert len(events) == 4


def test_prior_completed_content_and_file_rows_survive_failed_and_successful_retries(
    report_factory, db_engine, report_student_id
):
    class WithContent(EmptyGenerator):
        async def generate(self, command, report):
            await super().generate(command, report)
            return GenerationResult(
                ReportState.OK,
                items=(
                    ReportItem(
                        type="METRIC",
                        seq=1,
                        payload={"synthetic": "preserve"},
                        state="OK",
                        verified=True,
                    ),
                ),
                files=(ReportFile("MD", f"synthetic/{report.id}/original.md", 9),),
            )

    original = wire(report_student_id)
    failed = retry_request(original)
    success = retry_request(failed, False)

    def content():
        with report_factory() as session:
            return (
                [dict(x) for x in session.execute(select(report_item)).mappings()],
                [dict(x) for x in session.execute(select(report_file)).mappings()],
            )

    async def scenario():
        await deliver(handler(report_factory, db_engine, WithContent()), original)
        before, old = content(), dict(stored(report_factory, report_student_id)[0][0])
        await deliver(handler(report_factory, db_engine, FailingGenerator()), failed)
        await deliver(handler(report_factory, db_engine, EmptyGenerator()), success)
        await deliver(handler(report_factory, db_engine, FailingGenerator()), original)
        assert content() == before
        assert dict(stored(report_factory, report_student_id)[0][0]) == old

    asyncio.run(scenario())
    reports, events = stored(report_factory, report_student_id)
    assert [r["revision"] for r in reports] == [1, 2, 3]
    assert [r["status"] for r in reports] == ["COMPLETED", "FAILED", "COMPLETED"]
    assert len(events) == 6


@pytest.mark.parametrize("stage", ["report.started", "report.completed", "report.failed"])
def test_retry_state_and_outbox_rollback_atomically(
    report_factory, db_engine, report_student_id, stage
):
    original = wire(report_student_id)
    retry = retry_request(original)

    class Broken(OutboxRepository):
        def add(self, session, envelope):
            super().add(session, envelope)
            if envelope.type == stage:
                raise RuntimeError("synthetic persistence fault")

    generator = FailingGenerator() if stage == "report.failed" else EmptyGenerator()

    async def scenario():
        await deliver(handler(report_factory, db_engine, FailingGenerator()), original)
        old = dict(stored(report_factory, report_student_id)[0][0])
        with pytest.raises(RuntimeError, match="persistence fault"):
            await deliver(handler(report_factory, db_engine, generator, Broken()), retry)
        reports, events = stored(report_factory, report_student_id)
        assert dict(reports[0]) == old
        if stage == "report.started":
            assert len(reports) == 1 and len(events) == 2
        else:
            assert reports[1]["status"] == "RUNNING"
            assert [x["event_type"] for x in lifecycle(events, retry["data"]["jobId"])] == [
                "report.started"
            ]
        await deliver(handler(report_factory, db_engine, generator), retry)

    asyncio.run(scenario())
    reports, events = stored(report_factory, report_student_id)
    assert reports[1]["status"] == ("FAILED" if stage == "report.failed" else "COMPLETED")
    assert len(events) == 4


def test_shared_admin_retry_examples_match_v1_contract_and_execution_identities():
    path = Path(__file__).resolve().parents[3] / "contracts/examples/report-admin-retry"
    samples = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(path.glob("*.json"))]
    assert len(samples) == 7
    for sample in samples:
        validate_contract(sample)
        assert "originalJobId" not in sample["data"]
    old, request, started, completed, another, started_again, failed = samples
    assert len({x["data"]["jobId"] for x in (old, request, another)}) == 3
    for command, events in ((request, (started, completed)), (another, (started_again, failed))):
        decoded = ReportV1Codec().decode(ReceivedEnvelope.model_validate(command))
        assert decoded.trigger == "ADMIN_RETRY"
        assert all(x["data"]["jobId"] == str(decoded.job_id) for x in events)
        assert events[0]["data"]["reportId"] == events[1]["data"]["reportId"]


@pytest.mark.parametrize("status", ["PENDING", "COMPLETED"])
def test_admin_retry_keeps_existing_student_deletion_barrier(
    report_factory, db_engine, report_student_id, status
):
    original = wire(report_student_id)
    retry = retry_request(original)
    asyncio.run(deliver(handler(report_factory, db_engine, FailingGenerator()), original))
    before = stored(report_factory, report_student_id)
    with report_factory.begin() as session:
        session.execute(
            deletion_guard.insert().values(
                student_id=report_student_id,
                scope="RECORDS",
                cutoff_at=datetime.now(UTC),
                deletion_request_id=uuid4(),
                status=status,
                updated_at=datetime.now(UTC),
            )
        )
    generator = EmptyGenerator()
    action = deliver(handler(report_factory, db_engine, generator), retry)
    if status == "PENDING":
        with pytest.raises(GenerationBusy):
            asyncio.run(action)
    else:
        asyncio.run(action)
    assert generator.calls == 0
    assert stored(report_factory, report_student_id) == before
