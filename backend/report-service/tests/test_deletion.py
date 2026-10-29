import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select

from app.clients.base import internal_client
from app.clients.core_client import CoreClient
from app.deletion.consumer import DELETION_QUEUE, StudentDeletedConsumer
from app.deletion.service import DeletionService
from app.deletion.state import DeleteStudent, deletion_guard, processed_event
from app.errors import ApiError
from app.generation.locking import JobLocks
from app.generation.models import GenerationBusy
from app.generation.repository import report_file, report_item, report_item_evidence
from app.messaging.connection import AmqpConnection
from app.messaging.consumer import EventConsumer
from app.messaging.envelope import EventEnvelope
from app.query.service import QueryService
from app.security import UserContext, bind_user_context, current_user_context, reset_user_context
from app.worker import serve
from tests.report_helpers import command_for
from tests.test_consumer import FakeChannel, FakeMessage
from tests.test_generation import make_service, stored
from tests.test_report_codec import validate_contract


class Storage:
    def __init__(self):
        self.calls, self.fail = [], False

    def delete_prefix(self, prefix):
        self.calls.append(prefix)
        if self.fail:
            raise RuntimeError("synthetic object deletion failure")


class Core:
    def __init__(self):
        self.calls, self.fail = [], False

    async def report_deletion_completed(self, request):
        self.calls.append(request)
        if self.fail:
            raise httpx.ConnectError("synthetic core outage")


@pytest.fixture
def deletion_setup(report_factory, db_engine, report_student_id):
    events = []
    storage, core = Storage(), Core()

    def command(scope="PROFILE", at=None):
        result = DeleteStudent(uuid4(), report_student_id, uuid4(), scope, at or datetime.now(UTC))
        events.append(result.event_id)
        return result

    try:
        yield (
            command,
            DeletionService(report_factory, JobLocks(db_engine), lambda: storage, core),
            storage,
            core,
        )
    finally:
        with report_factory.begin() as session:
            session.execute(delete(processed_event).where(processed_event.c.event_id.in_(events)))


def guard(factory, student):
    with factory() as session:
        return (
            session.execute(select(deletion_guard).where(deletion_guard.c.student_id == student))
            .mappings()
            .one()
        )


def envelope(command):
    return EventEnvelope(
        type="student.deleted",
        source="core-service",
        id=str(command.event_id),
        time=command.occurred_at,
        subject=str(command.student_id),
        dataschema="student.deleted.v1",
        data={
            "studentId": str(command.student_id),
            "deletionRequestId": str(command.request_id),
            "scope": command.scope,
        },
    )


@pytest.mark.parametrize(
    "fault", ["source", "subject", "missing-student", "extra", "scope", "uuid", "schema"]
)
def test_invalid_shared_deletion_contract_is_rejected_before_side_effects(fault):
    command = DeleteStudent(uuid4(), uuid4(), uuid4(), "RECORDS", datetime.now(UTC))
    body = envelope(command).model_dump(mode="json")
    validate_contract(body)
    if fault == "source":
        body["source"] = "other-service"
    elif fault == "subject":
        body["subject"] = str(uuid4())
    elif fault == "missing-student":
        del body["data"]["studentId"]
    elif fault == "extra":
        body["data"]["nickname"] = "synthetic"
    elif fault == "scope":
        body["data"]["scope"] = "UNLINK"
    elif fault == "uuid":
        body["data"]["deletionRequestId"] = uuid4().hex
    else:
        body["dataschema"] = "student.deleted.v2"

    class Untouched:
        async def delete(self, command):
            pytest.fail("Invalid contract reached deletion side effects")

    message, channel = FakeMessage(json.dumps(body).encode()), FakeChannel()
    asyncio.run(
        EventConsumer(AmqpConnection("amqp://unused"), 3, 1).handle_message(
            channel, DELETION_QUEUE, StudentDeletedConsumer(Untouched()), message
        )
    )
    assert message.rejected and not message.acked
    assert not channel.default_exchange.published
    assert current_user_context() is None


def test_duplicate_deletes_all_owned_rows_once_and_preserves_other_student(
    deletion_setup, report_factory, db_engine, report_student_id, report_students
):
    new_command, service, storage, core = deletion_setup
    other = uuid4()
    report_students.add(other)
    for student in (report_student_id, other):
        request = command_for(student)
        asyncio.run(make_service(report_factory, db_engine, request).generate(request))
    report = stored(report_factory, report_student_id)[0][0]
    item = uuid4()
    with report_factory.begin() as session:
        session.execute(
            report_item.insert().values(
                id=item,
                report_id=report["id"],
                item_type="QUOTE",
                seq=1,
                payload={"text": "synthetic"},
                state="OK",
                verified=True,
            )
        )
        session.execute(
            report_item_evidence.insert().values(
                id=uuid4(), item_id=item, attempt_id=uuid4(), answer_id=uuid4(), answer_version=1
            )
        )
        session.execute(
            report_file.insert().values(
                id=uuid4(),
                report_id=report["id"],
                format="PDF",
                s3_key="synthetic",
                size_bytes=1,
                created_at=datetime.now(UTC),
            )
        )
    command = new_command()
    consumer = StudentDeletedConsumer(service)
    asyncio.run(consumer(envelope(command)))
    asyncio.run(consumer(envelope(command)))
    assert current_user_context() is None
    assert storage.calls == [f"reports/{report_student_id}/"]
    assert core.calls == [command.request_id, command.request_id]
    assert stored(report_factory, report_student_id) == ([], [])
    assert len(stored(report_factory, other)[0]) == 1
    with report_factory() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(report_item).where(report_item.c.id == item)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(report_item_evidence)
                .where(report_item_evidence.c.item_id == item)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(report_file)
                .where(report_file.c.report_id == report["id"])
            )
            == 0
        )
        assert (
            session.scalar(
                select(processed_event.c.event_type).where(
                    processed_event.c.event_id == command.event_id
                )
            )
            == "student.deleted"
        )


def test_s3_failure_routes_to_retry_and_leaves_pending_db_then_recovers(
    deletion_setup, report_factory, db_engine, report_student_id
):
    new_command, service, storage, core = deletion_setup
    request = command_for(report_student_id)
    asyncio.run(make_service(report_factory, db_engine, request).generate(request))
    storage.fail = True
    command = new_command()
    message = FakeMessage(envelope(command).model_dump_json().encode())
    channel = FakeChannel()
    consumer = EventConsumer(AmqpConnection("amqp://unused"), 3, 1)
    asyncio.run(
        consumer.handle_message(channel, DELETION_QUEUE, StudentDeletedConsumer(service), message)
    )
    assert message.acked and not message.rejected
    retry, queue = channel.default_exchange.published[0]
    assert queue == DELETION_QUEUE + ".retry.1" and retry.headers["x-retry-count"] == 1
    assert guard(report_factory, report_student_id)["status"] == "PENDING"
    assert len(stored(report_factory, report_student_id)[0]) == 1 and not core.calls
    storage.fail = False
    asyncio.run(service.delete(command))
    assert guard(report_factory, report_student_id)["status"] == "COMPLETED"
    assert stored(report_factory, report_student_id) == ([], [])


def test_core_failure_retries_callback_only(deletion_setup, report_factory, report_student_id):
    new_command, service, storage, core = deletion_setup
    command = new_command()
    core.fail = True
    with pytest.raises(httpx.ConnectError):
        asyncio.run(service.delete(command))
    assert guard(report_factory, report_student_id)["status"] == "COMPLETED"
    core.fail = False
    asyncio.run(service.delete(command))
    assert len(storage.calls) == 1 and len(core.calls) == 2


def test_generation_lock_blocks_deletion_and_deletion_lock_blocks_generation(
    deletion_setup, db_engine, report_student_id
):
    new_command, service, storage, _ = deletion_setup
    locks = JobLocks(db_engine)
    lease = locks.acquire(uuid4(), report_student_id)
    try:
        with pytest.raises(GenerationBusy):
            asyncio.run(service.delete(new_command()))
        assert not storage.calls
    finally:
        lease.close()
    lease = locks.acquire_student(report_student_id)
    try:
        with pytest.raises(GenerationBusy):
            locks.acquire(uuid4(), report_student_id)
    finally:
        lease.close()
    locks.acquire(uuid4(), report_student_id).close()


@pytest.mark.parametrize("scope", ["PROFILE", "RECORDS"])
def test_both_scopes_block_late_and_new_generation_until_explicit_resume(
    scope, deletion_setup, report_factory, db_engine, report_student_id
):
    new_command, service, _, _ = deletion_setup
    command = new_command(scope)
    asyncio.run(service.delete(command))
    for at in (None, command.occurred_at - timedelta(seconds=1), command.occurred_at):
        request = replace(command_for(report_student_id), requested_at=at)
        asyncio.run(make_service(report_factory, db_engine, request).generate(request))
    assert stored(report_factory, report_student_id) == ([], [])
    request = replace(
        command_for(report_student_id), requested_at=command.occurred_at + timedelta(seconds=1)
    )
    asyncio.run(make_service(report_factory, db_engine, request).generate(request))
    assert stored(report_factory, report_student_id) == ([], [])


def test_old_records_event_is_idempotent_but_profile_always_upgrades(
    deletion_setup, report_factory, db_engine, report_student_id
):
    new_command, service, storage, _ = deletion_setup
    current = new_command("RECORDS")
    asyncio.run(service.delete(current))
    request = replace(
        command_for(report_student_id), requested_at=current.occurred_at + timedelta(seconds=1)
    )
    asyncio.run(make_service(report_factory, db_engine, request).generate(request))
    old = new_command("RECORDS", current.occurred_at - timedelta(seconds=1))
    asyncio.run(service.delete(old))
    assert len(storage.calls) == 1 and stored(report_factory, report_student_id) == ([], [])
    profile = new_command("PROFILE", old.occurred_at)
    asyncio.run(service.delete(profile))
    assert len(storage.calls) == 2 and stored(report_factory, report_student_id) == ([], [])
    assert guard(report_factory, report_student_id)["scope"] == "PROFILE"


@pytest.mark.parametrize("scope", ["PROFILE", "RECORDS"])
def test_newer_event_after_profile_deletion_can_retry_completion(
    scope, deletion_setup, report_factory, report_student_id
):
    new_command, service, storage, core = deletion_setup
    profile = new_command("PROFILE")
    asyncio.run(service.delete(profile))
    newer = new_command(scope, profile.occurred_at + timedelta(seconds=1))
    core.fail = True
    with pytest.raises(httpx.ConnectError):
        asyncio.run(service.delete(newer))
    core.fail = False
    asyncio.run(service.delete(newer))
    assert len(storage.calls) == 1
    assert core.calls == [profile.request_id, newer.request_id, newer.request_id]
    assert guard(report_factory, report_student_id)["scope"] == "PROFILE"


def test_processed_event_redelivered_during_newer_pending_request_resends_completion(
    deletion_setup, report_factory, report_student_id
):
    new_command, service, storage, core = deletion_setup
    first = new_command("RECORDS")
    asyncio.run(service.delete(first))
    newer = new_command("RECORDS", first.occurred_at + timedelta(seconds=1))
    storage.fail = True
    with pytest.raises(RuntimeError):
        asyncio.run(service.delete(newer))
    asyncio.run(service.delete(first))
    assert core.calls == [first.request_id, first.request_id]
    pending = guard(report_factory, report_student_id)
    assert pending["status"] == "PENDING" and pending["deletion_request_id"] == newer.request_id


def test_pending_blocks_query_and_generation(
    deletion_setup, report_factory, db_engine, report_student_id
):
    new_command, service, storage, _ = deletion_setup
    storage.fail = True
    with pytest.raises(RuntimeError):
        asyncio.run(service.delete(new_command()))
    token = bind_user_context(
        UserContext(None, "SYSTEM", frozenset({str(report_student_id)}), None)
    )
    try:
        with pytest.raises(ApiError) as error:
            asyncio.run(
                QueryService(report_factory, None, None, 300).list(report_student_id, None, 0, 20)
            )
        assert error.value.status == 409
    finally:
        reset_user_context(token)
    request = command_for(report_student_id)
    with pytest.raises(GenerationBusy):
        asyncio.run(make_service(report_factory, db_engine, request).generate(request))


def test_completion_client_uses_internal_auth_and_scoped_context():
    request_id, student_id = uuid4(), uuid4()

    def respond(request):
        assert request.url.path == f"/internal/deletion-requests/{request_id}/completions"
        assert request.headers["X-Internal-Token"] == "test-token"
        assert request.headers["X-Student-Scope"] == str(student_id)
        assert request.content == b'{"service":"report"}'
        return httpx.Response(204)

    async def scenario():
        token = bind_user_context(UserContext(None, "SYSTEM", frozenset({str(student_id)}), None))
        try:
            async with internal_client(
                "http://core.test", transport=httpx.MockTransport(respond)
            ) as client:
                await CoreClient(client).report_deletion_completed(request_id)
        finally:
            reset_user_context(token)

    asyncio.run(scenario())


def test_worker_stops_deliveries_then_drains_handler_and_closes():
    async def scenario():
        stop, entered, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()
        order, deliveries = [], []

        async def handler(event):
            entered.set()
            await finish.wait()
            order.append("done")

        class Subscription:
            async def stop(self):
                order.append("stop")
                finish.set()

            async def close(self):
                order.append("close")

        class Consumer:
            async def consume(self, queue, call):
                assert queue == DELETION_QUEUE
                deliveries.append(asyncio.create_task(call(None)))
                return Subscription()

        class Relay:
            async def publish_once(self):
                return False

        task = asyncio.create_task(
            serve(
                SimpleNamespace(is_connected=True),
                Consumer(),
                [(DELETION_QUEUE, handler)],
                Relay(),
                stop,
            )
        )
        await entered.wait()
        stop.set()
        await task
        await asyncio.gather(*deliveries)
        assert order == ["stop", "done", "close"]

    asyncio.run(scenario())
