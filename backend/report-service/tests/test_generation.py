import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.database import transaction
from app.generation.consumer import GenerationConsumer
from app.generation.locking import JobLocks
from app.generation.models import GenerationBusy, JobConflict
from app.generation.repository import weekly_report
from app.generation.service import GenerationService
from app.messaging.envelope import EventEnvelope
from app.outbox.repository import OutboxRepository, outbox_event
from app.security import UserContext, bind_user_context, current_user_context, reset_user_context
from tests.report_helpers import EmptyGenerator, FakeCodec, command_for


def make_service(factory, engine, command, generator=None, outbox=None):
    return GenerationService(
        factory, JobLocks(engine), generator or EmptyGenerator(), FakeCodec(command), outbox=outbox
    )


def stored(factory, student_id):
    with factory() as session:
        reports = (
            session.execute(
                select(weekly_report)
                .where(weekly_report.c.student_id == student_id)
                .order_by(weekly_report.c.revision)
            )
            .mappings()
            .all()
        )
        events = (
            session.execute(
                select(outbox_event)
                .where(outbox_event.c.subject == str(student_id))
                .order_by(outbox_event.c.created_at)
            )
            .mappings()
            .all()
        )
    return reports, events


def test_repeated_job_creates_one_report_and_one_of_each_event(
    report_factory, db_engine, report_student_id
):
    command = command_for(report_student_id)
    generator = EmptyGenerator()
    service = make_service(report_factory, db_engine, command, generator)
    asyncio.run(service.generate(command))
    asyncio.run(service.generate(command))
    reports, events = stored(report_factory, report_student_id)
    assert len(reports) == 1
    assert reports[0]["status"] == "COMPLETED" and reports[0]["state"] == "NO_RECORD"
    assert reports[0]["revision"] == 1 and reports[0]["generated_at"] is not None
    assert [e["event_type"] for e in events] == ["report.started", "report.completed"]
    assert generator.calls == 1


def test_failure_is_terminal_and_does_not_store_raw_exception(
    report_factory, db_engine, report_student_id
):
    class FailingGenerator(EmptyGenerator):
        async def generate(self, command, report):
            self.calls += 1
            raise RuntimeError("synthetic secret/student text must not be stored")

    command = command_for(report_student_id)
    generator = FailingGenerator()
    service = make_service(report_factory, db_engine, command, generator)
    asyncio.run(service.generate(command))
    asyncio.run(service.generate(command))
    reports, events = stored(report_factory, report_student_id)
    assert reports[0]["status"] == "FAILED" and reports[0]["state"] is None
    assert reports[0]["failure_reason"] == "GENERATION_FAILED"
    assert [e["event_type"] for e in events] == ["report.started", "report.failed"]
    assert generator.calls == 1


def test_start_and_outbox_roll_back_together(report_factory, db_engine, report_student_id):
    class BrokenOutbox(OutboxRepository):
        def add(self, session, envelope):
            super().add(session, envelope)
            raise RuntimeError("synthetic outbox failure")

    command = command_for(report_student_id)
    service = make_service(report_factory, db_engine, command, outbox=BrokenOutbox())
    with pytest.raises(RuntimeError, match="synthetic outbox"):
        asyncio.run(service.generate(command))
    assert stored(report_factory, report_student_id) == ([], [])
    # Failure also releases the session advisory lock.
    JobLocks(db_engine).acquire(command.job_id).close()


def test_completion_rollback_leaves_running_and_redelivery_reuses_it(
    report_factory, db_engine, report_student_id
):
    class BrokenCompletion(OutboxRepository):
        def add(self, session, envelope):
            super().add(session, envelope)
            if envelope.type == "report.completed":
                raise RuntimeError("synthetic completion persistence failure")

    command = command_for(report_student_id)
    broken = make_service(report_factory, db_engine, command, outbox=BrokenCompletion())
    with pytest.raises(RuntimeError, match="completion persistence"):
        asyncio.run(broken.generate(command))
    reports, events = stored(report_factory, report_student_id)
    original_id = reports[0]["id"]
    assert reports[0]["status"] == "RUNNING" and reports[0]["state"] is None
    assert [e["event_type"] for e in events] == ["report.started"]
    asyncio.run(make_service(report_factory, db_engine, command).generate(command))
    reports, events = stored(report_factory, report_student_id)
    assert len(reports) == 1 and reports[0]["id"] == original_id
    assert [e["event_type"] for e in events] == ["report.started", "report.completed"]


def test_conflicting_job_does_not_change_original_report(
    report_factory, db_engine, report_student_id
):
    command = command_for(report_student_id)
    service = make_service(report_factory, db_engine, command)
    asyncio.run(service.generate(command))
    with pytest.raises(JobConflict):
        asyncio.run(service.generate(replace(command, student_id=uuid4())))
    reports, events = stored(report_factory, report_student_id)
    assert reports[0]["student_id"] == report_student_id and len(events) == 2


def test_concurrent_deliveries_do_not_run_generator_twice(
    report_factory, db_engine, report_student_id
):
    async def scenario():
        entered, finish = asyncio.Event(), asyncio.Event()

        class SlowGenerator(EmptyGenerator):
            async def generate(self, command, report):
                entered.set()
                await finish.wait()
                return await super().generate(command, report)

        command = command_for(report_student_id)
        generator = SlowGenerator()
        service = make_service(report_factory, db_engine, command, generator)
        first = asyncio.create_task(service.generate(command))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            with pytest.raises(GenerationBusy):
                await service.generate(command)
        finally:
            finish.set()
            await first
        await service.generate(command)
        assert generator.calls == 1

    asyncio.run(scenario())
    reports, events = stored(report_factory, report_student_id)
    assert len(reports) == 1 and len(events) == 2


def test_concurrent_regenerations_allocate_distinct_revisions(
    report_factory, db_engine, report_student_id
):
    first = command_for(report_student_id)
    second = replace(first, job_id=uuid4(), trigger="REGENERATE")
    service = make_service(report_factory, db_engine, first)

    async def scenario():
        await asyncio.gather(service.generate(first), service.generate(second))

    asyncio.run(scenario())
    reports, events = stored(report_factory, report_student_id)
    assert [r["revision"] for r in reports] == [1, 2]
    assert {r["job_id"] for r in reports} == {first.job_id, second.job_id}
    assert len(events) == 4


def test_cancellation_leaves_running_and_allows_recovery(
    report_factory, db_engine, report_student_id
):
    command = command_for(report_student_id)

    async def scenario():
        entered = asyncio.Event()

        class StalledGenerator(EmptyGenerator):
            async def generate(self, command, report):
                entered.set()
                await asyncio.Event().wait()

        service = make_service(report_factory, db_engine, command, StalledGenerator())
        task = asyncio.create_task(service.generate(command))
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        reports, events = stored(report_factory, report_student_id)
        assert reports[0]["status"] == "RUNNING" and len(events) == 1
        await make_service(report_factory, db_engine, command).generate(command)

    asyncio.run(scenario())
    reports, events = stored(report_factory, report_student_id)
    assert reports[0]["status"] == "COMPLETED" and len(events) == 2


def test_system_context_is_bound_and_restored(report_factory, db_engine, report_student_id):
    command = command_for(report_student_id)
    generator = EmptyGenerator()
    service = make_service(report_factory, db_engine, command, generator)
    handler = GenerationConsumer(service, FakeCodec(command))
    previous = UserContext("synthetic-parent", "PARENT", frozenset())
    envelope = EventEnvelope(
        type="report.generate",
        source="core-service",
        subject=str(report_student_id),
        dataschema="report.generate.v1",
        traceparent="synthetic-trace",
        data={},
    )

    async def scenario():
        reset = bind_user_context(previous)
        try:
            await handler(envelope)
            assert current_user_context() == previous
        finally:
            reset_user_context(reset)

    asyncio.run(scenario())
    [context] = generator.contexts
    assert context.role == "SYSTEM" and context.user_id is None
    assert context.student_scope == frozenset({str(report_student_id)})
    _, events = stored(report_factory, report_student_id)
    assert all(e["payload"]["traceparent"] == "synthetic-trace" for e in events)


def test_subject_mismatch_is_rejected_before_writing(report_factory, db_engine, report_student_id):
    command = command_for(report_student_id)
    handler = GenerationConsumer(
        make_service(report_factory, db_engine, command), FakeCodec(command)
    )
    envelope = EventEnvelope(
        type="report.generate",
        source="core-service",
        subject=str(uuid4()),
        dataschema="report.generate.v1",
        data={},
    )
    with pytest.raises(ValueError, match="subject"):
        asyncio.run(handler(envelope))
    assert stored(report_factory, report_student_id) == ([], [])


def test_existing_terminal_report_cannot_emit_another_terminal_event(
    report_factory, db_engine, report_student_id
):
    from app.generation.repository import ReportRepository

    command = command_for(report_student_id)
    asyncio.run(make_service(report_factory, db_engine, command).generate(command))
    reports, _ = stored(report_factory, report_student_id)
    with transaction(report_factory) as session:
        assert (
            ReportRepository().finish(session, reports[0]["id"], failure_reason="LATE_FAILURE")
            is None
        )
    reports, events = stored(report_factory, report_student_id)
    assert reports[0]["status"] == "COMPLETED" and len(events) == 2
