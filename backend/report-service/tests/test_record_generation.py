import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.clients.base import internal_client
from app.clients.learning_client import LearningClient
from app.generation.consumer import GenerationConsumer
from app.generation.locking import JobLocks
from app.generation.record_generator import RecordGenerator
from app.generation.repository import (
    ReportRepository,
    report_item,
    report_item_evidence,
    weekly_report,
)
from app.generation.service import GenerationService
from app.messaging.envelope import EventEnvelope
from app.outbox.repository import outbox_event
from tests.record_helpers import attempt_for, instant
from tests.report_helpers import FakeCodec, command_for
from tests.test_learning_client import handler_for


def execute(factory, engine, student, attempts, *, repository=None, mutate=None):
    command = command_for(student)
    requests = []

    async def scenario():
        async with internal_client(
            "http://learning.test",
            transport=httpx.MockTransport(handler_for(student, attempts, requests, mutate)),
        ) as http:
            service = GenerationService(
                factory,
                JobLocks(engine),
                RecordGenerator(LearningClient(http)),
                FakeCodec(command),
                repository=repository,
            )
            handler = GenerationConsumer(service, FakeCodec(command))
            envelope = EventEnvelope(
                type="report.generate",
                source="core-service",
                dataschema="report.generate.v1",
                subject=str(student),
                traceparent="synthetic-trace",
                data={},
            )
            await handler(envelope)
            await handler(envelope)  # re-delivery must not refetch or add item/evidence rows

    asyncio.run(scenario())
    return command, requests


def stored(factory):
    with factory() as session:
        return (
            session.execute(select(weekly_report)).mappings().all(),
            session.execute(select(report_item)).mappings().all(),
            session.execute(select(report_item_evidence)).mappings().all(),
            session.execute(select(outbox_event)).mappings().all(),
        )


def test_fixed_learning_responses_store_all_item_types_and_evidence(
    report_factory, db_engine, report_student_id
):
    from app.generation.records import ReflectionRecord

    attempt = attempt_for(
        report_student_id, texts=("첫 답변.", "왜냐하면 합성 까닭 때문이다."), status="COMPLETED"
    )
    attempt = replace(
        attempt, reflection=ReflectionRecord("NORMAL", "직접 쓴 합성 돌아보기", instant())
    )
    _, requests = execute(report_factory, db_engine, report_student_id, [attempt])
    reports, items, evidence, events = stored(report_factory)
    assert len(reports) == 1 and reports[0]["status"] == "COMPLETED"
    assert reports[0]["state"] == "INSUFFICIENT_SAMPLE" and reports[0]["inclusion_rule"]
    assert {i["item_type"] for i in items} == {
        "METRIC",
        "THINKING_TYPE",
        "CHANGE",
        "REFLECTION",
        "QUOTE",
    }
    assert len(items) == 11
    assert {(e["answer_id"], e["answer_version"]) for e in evidence} == {
        (a.id, a.version) for a in attempt.answers
    }
    assert {e["item_id"] for e in evidence} <= {i["id"] for i in items}
    assert len(events) == 2 and len(requests) == 3
    assert all(r.url.host == "learning.test" for r in requests)


def test_no_record_is_completed_with_no_ai_request(report_factory, db_engine, report_student_id):
    _, requests = execute(report_factory, db_engine, report_student_id, [])
    reports, items, evidence, events = stored(report_factory)
    assert reports[0]["status"] == "COMPLETED" and reports[0]["state"] == "NO_RECORD"
    assert len(items) == 8 and evidence == [] and len(events) == 2
    assert all(i["payload"]["value"] is None for i in items if i["item_type"] == "METRIC")
    assert all(r.method == "GET" and r.url.host == "learning.test" for r in requests)


def test_source_inconsistency_is_failed_and_saves_no_items(
    report_factory, db_engine, report_student_id
):
    def mutate(name, data):
        if name == "thinking-types":
            data["items"] = []
        return data

    execute(
        report_factory,
        db_engine,
        report_student_id,
        [attempt_for(report_student_id)],
        mutate=mutate,
    )
    reports, items, evidence, events = stored(report_factory)
    assert reports[0]["status"] == "FAILED" and reports[0]["state"] is None
    assert items == evidence == []
    assert {e["event_type"] for e in events} == {"report.started", "report.failed"}


def test_evidence_constraint_failure_rolls_back_items_state_and_completion_outbox(
    report_factory, db_engine, report_student_id
):
    from uuid import uuid4

    class BrokenEvidence(ReportRepository):
        @staticmethod
        def _save_items(session, report_id, result):
            ReportRepository._save_items(session, report_id, result)
            session.execute(
                report_item_evidence.insert().values(
                    id=uuid4(),
                    item_id=uuid4(),
                    attempt_id=uuid4(),
                    answer_id=uuid4(),
                    answer_version=1,
                )
            )

    with pytest.raises(IntegrityError):
        execute(
            report_factory,
            db_engine,
            report_student_id,
            [attempt_for(report_student_id)],
            repository=BrokenEvidence(),
        )
    reports, items, evidence, events = stored(report_factory)
    assert reports[0]["status"] == "RUNNING" and reports[0]["state"] is None
    assert items == evidence == []
    assert [e["event_type"] for e in events] == ["report.started"]


def test_private_memo_never_reaches_persisted_items(report_factory, db_engine, report_student_id):
    def mutate(name, data):
        if name == "attempts":
            data["items"][0]["draft"] = {"memo": "PRIVATE-MEMO-ONLY"}
        return data

    execute(
        report_factory,
        db_engine,
        report_student_id,
        [attempt_for(report_student_id)],
        mutate=mutate,
    )
    _, items, _, _ = stored(report_factory)
    assert "PRIVATE-MEMO-ONLY" not in json.dumps([dict(i["payload"]) for i in items])
