import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.bootstrap import create_app
from app.database import transaction
from app.deletion.state import DeleteStudent, DeletionRepository, deletion_guard
from app.errors import ApiError
from app.generation.locking import JobLocks
from app.generation.models import GenerationResult, JobConflict, ReportState
from app.generation.reconciliation import ReconciliationService
from app.generation.repository import ReportRepository, report_job_guard, weekly_report
from app.outbox.repository import outbox_event
from app.security import UserContext, bind_user_context, reset_user_context
from tests.report_helpers import EmptyGenerator, command_for
from tests.test_generation import make_service, stored
from tests.test_outbox_broker import rabbit_url  # noqa: F401


def recover(factory, engine, command):
    token = bind_user_context(UserContext(None, "SYSTEM", frozenset({str(command.student_id)})))
    try:
        return ReconciliationService(factory, JobLocks(engine)).reconcile(
            command.job_id, command.student_id, command.period_from, command.period_to
        )
    finally:
        reset_user_context(token)


@pytest.mark.parametrize("status", ["RUNNING", "COMPLETED", "FAILED"])
def test_lost_terminal_event_and_orphan_are_recovered_idempotently(
    report_factory, db_engine, report_student_id, status
):
    command = command_for(report_student_id)
    repo = ReportRepository()
    with transaction(report_factory) as session:
        report, _ = repo.get_or_create(session, command)
        if status == "COMPLETED":
            repo.finish(session, report.id, result=GenerationResult(ReportState.NO_RECORD))
        elif status == "FAILED":
            repo.finish(session, report.id, failure_reason="GENERATION_FAILED")
    first = recover(report_factory, db_engine, command)
    assert first.status == ("COMPLETED" if status == "COMPLETED" else "FAILED")
    assert first.report_id == report.id
    assert first == recover(report_factory, db_engine, command)
    generator = EmptyGenerator()
    asyncio.run(make_service(report_factory, db_engine, command, generator).generate(command))
    assert generator.calls == 0
    with report_factory() as session:
        assert session.scalar(
            select(func.count())
            .select_from(outbox_event)
            .where(outbox_event.c.subject == str(report_student_id))
        ) == (1 if status == "RUNNING" else 0)


def test_no_row_response_loss_blocks_delayed_delivery_and_rejects_identity_changes(
    report_factory, db_engine, report_student_id
):
    command = command_for(report_student_id)
    first = recover(report_factory, db_engine, command)
    assert first.failure_reason == "REPORT_NOT_CREATED" and first.report_id is None
    assert first == recover(report_factory, db_engine, command)
    generator = EmptyGenerator()
    asyncio.run(make_service(report_factory, db_engine, command, generator).generate(command))
    assert generator.calls == 0 and stored(report_factory, report_student_id) == ([], [])
    for changed in (
        replace(command, student_id=uuid4()),
        replace(
            command,
            period_from=command.period_from + timedelta(days=7),
            period_to=command.period_to + timedelta(days=7),
        ),
    ):
        with pytest.raises(ApiError) as error:
            recover(report_factory, db_engine, changed)
        assert error.value.code == "REPORT_JOB_IDENTITY_MISMATCH"
        with pytest.raises(JobConflict):
            asyncio.run(make_service(report_factory, db_engine, changed).generate(changed))


def test_live_generation_is_busy_and_can_complete(report_factory, db_engine, report_student_id):
    entered, release = Event(), Event()

    class Waiting(EmptyGenerator):
        async def generate(self, command, report):
            entered.set()
            assert await asyncio.to_thread(release.wait, 10)
            return await super().generate(command, report)

    command = command_for(report_student_id)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(
            asyncio.run,
            make_service(report_factory, db_engine, command, Waiting()).generate(command),
        )
        try:
            assert entered.wait(10)
            result = recover(report_factory, db_engine, command)
            assert result.status == "BUSY" and result.report_id is None
            assert stored(report_factory, report_student_id)[0][0]["status"] == "RUNNING"
        finally:
            release.set()
        future.result(10)
    assert recover(report_factory, db_engine, command).status == "COMPLETED"


def test_deletion_guard_replaces_job_guard_without_resurrecting_data(
    report_factory, db_engine, report_student_id
):
    command = command_for(report_student_id)
    recover(report_factory, db_engine, command)
    deletion = DeleteStudent(uuid4(), report_student_id, uuid4(), "RECORDS", datetime.now(UTC))
    locks = JobLocks(db_engine)
    lease = locks.acquire_student(report_student_id)
    try:
        assert recover(report_factory, db_engine, command).status == "BUSY"
        with transaction(report_factory) as session:
            DeletionRepository().begin(session, deletion)
    finally:
        lease.close()
    assert recover(report_factory, db_engine, command).status == "BUSY"
    with transaction(report_factory) as session:
        DeletionRepository().finish(session, deletion)
    result = recover(report_factory, db_engine, command)
    assert result.failure_reason == "STUDENT_DELETED"
    with report_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(report_job_guard)
                .where(report_job_guard.c.student_id == report_student_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(deletion_guard.c.status).where(
                    deletion_guard.c.student_id == report_student_id
                )
            )
            == "COMPLETED"
        )
    asyncio.run(make_service(report_factory, db_engine, command).generate(command))
    assert stored(report_factory, report_student_id) == ([], [])


def test_http_auth_identity_and_response_contract(report_factory, db_engine, report_student_id):
    app = create_app()
    app.state.session_factory, app.state.engine = report_factory, db_engine
    client = TestClient(app)
    command = command_for(report_student_id)
    url = f"/internal/report-jobs/{command.job_id}/reconcile"
    body = dict(
        studentId=str(report_student_id),
        periodFrom=str(command.period_from),
        periodTo=str(command.period_to),
    )
    headers = {
        "X-Internal-Token": "test-token",
        "X-User-Role": "SYSTEM",
        "X-Student-Scope": str(report_student_id),
    }
    assert client.post(url, json=body).status_code == 401
    for changed in (
        {"X-User-Role": "PARENT"},
        {"X-Student-Scope": f"{report_student_id},{uuid4()}"},
        {"X-Student-Scope": str(uuid4())},
    ):
        assert client.post(url, json=body, headers=headers | changed).status_code == 403
    response = client.post(url, json=body, headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == body | dict(
        jobId=str(command.job_id),
        status="FAILED",
        reportId=None,
        failureReason="REPORT_NOT_CREATED",
    )
    assert client.post(url, json=body, headers=headers).json() == response.json()
    changed = body | dict(
        periodFrom=str(command.period_from + timedelta(days=7)),
        periodTo=str(command.period_to + timedelta(days=7)),
    )
    assert (
        client.post(url, json=changed, headers=headers).json()["code"]
        == "REPORT_JOB_IDENTITY_MISMATCH"
    )
    assert (
        client.post(url, json=body | dict(periodTo=body["periodFrom"]), headers=headers).status_code
        == 400
    )


def test_database_error_is_not_a_terminal_response_and_lock_is_released(
    report_factory, db_engine, report_student_id
):
    command = command_for(report_student_id)

    def broken():
        raise RuntimeError("synthetic DB outage")

    class Factory:
        begin = staticmethod(broken)

    with pytest.raises(RuntimeError, match="synthetic DB"):
        recover(Factory(), db_engine, command)
    lease = JobLocks(db_engine).acquire(command.job_id, command.student_id)
    lease.close()
    with report_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(weekly_report)
                .where(weekly_report.c.job_id == command.job_id)
            )
            == 0
        )


@pytest.mark.parametrize("failure", ["invalid", "before_row", "busy"])
def test_dlq_then_recovery_blocks_redelivery(
    request, report_factory, db_engine, report_student_id, failure
):
    import json

    import aio_pika

    from app.generation.codec import ReportV1Codec
    from app.generation.consumer import GenerationConsumer
    from app.generation.service import GenerationService
    from app.messaging.connection import AmqpConnection
    from app.messaging.consumer import EventConsumer
    from app.messaging.envelope import EventEnvelope
    from tests.test_report_codec import wire

    broker_url = request.getfixturevalue("rabbit_url")
    body = wire(report_student_id)
    codec = ReportV1Codec()
    command = codec.decode(EventEnvelope.model_validate(body))
    generator = EmptyGenerator()
    locks = JobLocks(db_engine)
    service = GenerationService(report_factory, locks, generator, codec)
    handler = GenerationConsumer(service, codec)
    original_start = service._start
    lease = None
    if failure == "invalid":
        del body["data"]["narrativeEnabled"]
    elif failure == "before_row":

        def broken(_):
            raise RuntimeError("synthetic failure before report row")

        service._start = broken
    else:
        lease = locks.acquire(command.job_id, report_student_id)

    async def scenario():
        connection = await aio_pika.connect_robust(broker_url)
        try:
            channel = await connection.channel(publisher_confirms=True)
            name = "recovery-" + str(command.job_id)
            dead = await channel.declare_exchange(name + "-dlx", "direct", auto_delete=True)
            dlq = await channel.declare_queue(name + "-dlq", exclusive=True)
            await dlq.bind(dead, name)
            queue = await channel.declare_queue(
                name,
                exclusive=True,
                arguments={"x-dead-letter-exchange": dead.name, "x-dead-letter-routing-key": name},
            )
            consumer = EventConsumer(AmqpConnection(broker_url), 3, 1)
            await channel.default_exchange.publish(
                aio_pika.Message(
                    json.dumps(body).encode(),
                    headers={"x-retry-count": 3},
                    content_type="application/json",
                ),
                routing_key=name,
            )
            message = await queue.get(timeout=5)
            await consumer.handle_message(channel, name, handler, message)
            for _ in range(100):
                rejected = await dlq.get(fail=False)
                if rejected is not None:
                    break
                await asyncio.sleep(0.05)
            assert rejected is not None
            await rejected.ack()
            if lease is not None:
                lease.close()
            service._start = original_start
            response = await asyncio.to_thread(recover, report_factory, db_engine, command)
            assert response.failure_reason == "REPORT_NOT_CREATED"
            body["data"]["narrativeEnabled"] = False
            await channel.default_exchange.publish(
                aio_pika.Message(json.dumps(body).encode(), content_type="application/json"),
                routing_key=name,
            )
            delayed = await queue.get(timeout=5)
            await consumer.handle_message(channel, name, handler, delayed)
            assert delayed.processed and generator.calls == 0
            assert stored(report_factory, report_student_id) == ([], [])
        finally:
            await connection.close()

    asyncio.run(scenario())
