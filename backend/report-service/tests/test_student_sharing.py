import asyncio
import json
from dataclasses import replace
from uuid import uuid4

import pytest

from app.generation.models import ItemType
from app.generation.narrative_generator import NarrativeGenerator
from app.generation.pipeline import StudentDisplayName
from app.generation.record_generator import RecordGenerator
from app.generation.records import ReflectionRecord
from app.rendering.renderer import ReportRenderer
from tests.record_helpers import attempt_for, instant, records_for
from tests.report_helpers import command_for
from tests.test_pipeline import Capture, Names, invoke


class Records:
    def __init__(self, value):
        self.value = value

    async def records(self, student_id, period):
        return self.value


class NoExternalCalls:
    async def narrative(self, payload):
        pytest.fail("private records must not be sent for AI narration")

    async def evidence(self, student_id, links):
        pytest.fail("private originals must not be requested as narration evidence")


@pytest.mark.parametrize("sharing", [False, True])
def test_current_profile_controls_generation_not_a_stale_message(sharing):
    command = replace(
        command_for(uuid4()), narrative_enabled=True, parent_sharing_enabled=not sharing
    )
    capture = Capture()
    invoke(Names(StudentDisplayName(command.student_id, "별명", sharing)), capture, command)
    assert capture.command.parent_sharing_enabled is sharing
    assert capture.command.narrative_enabled is sharing
    assert command.parent_sharing_enabled is not sharing


def test_private_generation_retains_numbers_without_originals_evidence_or_ai():
    student = uuid4()
    attempt = replace(
        attempt_for(student, texts=("합성비밀 첫 답", "합성비밀 두 번째 답")),
        reflection=ReflectionRecord("NORMAL", "합성비밀 돌아보기", instant()),
    )
    records = records_for(student, [attempt])
    command = replace(command_for(student), parent_sharing_enabled=False, narrative_enabled=True)
    generator = NarrativeGenerator(
        RecordGenerator(Records(records)), NoExternalCalls(), NoExternalCalls()
    )
    result = asyncio.run(generator.generate(command, None))
    public = asyncio.run(
        RecordGenerator(Records(records)).generate(
            replace(command, parent_sharing_enabled=True), None
        )
    )
    assert [i.payload for i in result.items if i.type == ItemType.METRIC] == [
        i.payload for i in public.items if i.type == ItemType.METRIC
    ]
    assert all(not i.evidence for i in result.items)
    assert not any(i.type == ItemType.QUOTE for i in result.items)
    assert "합성비밀" not in json.dumps([i.payload for i in result.items], ensure_ascii=False)
    assert result.narrative is result.evening_question is None
    change = next(i for i in result.items if i.type == ItemType.CHANGE)
    assert change.payload["counts"]["chars"][0] > 0
    # StrictUndefined HTML and Markdown accept the redacted nullable shape.
    report = {
        "thinkingTypes": [],
        "changes": [change.payload],
        "reflections": [],
        "quotes": [],
        "metrics": [],
        "period": {"from": "2026-10-19", "to": "2026-10-25"},
        "revision": 1,
        "state": "OK",
        "inclusionRule": "P08",
        "generatedAt": None,
    }
    assert "합성비밀" not in ReportRenderer.markdown(report, "별명")


def test_private_generation_commits_only_redacted_items_and_renders_private_files(
    report_factory, db_engine, report_student_id
):
    from sqlalchemy import select

    from app.generation.consumer import GenerationConsumer
    from app.generation.locking import JobLocks
    from app.generation.pipeline import NamedGenerator
    from app.generation.repository import report_item, report_item_evidence, weekly_report
    from app.generation.service import GenerationService
    from app.messaging.envelope import EventEnvelope
    from app.rendering.generator import RenderingGenerator
    from tests.report_helpers import FakeCodec

    class Storage:
        def __init__(self):
            self.files = {}

        def put(self, key, body, content_type):
            self.files[key] = body

        def delete_prefix(self, prefix):
            self.files = {k: v for k, v in self.files.items() if not k.startswith(prefix)}

    command = replace(command_for(report_student_id), narrative_enabled=True)
    data = records_for(
        report_student_id,
        [attempt_for(report_student_id, texts=("합성비밀 첫답", "합성비밀 새답"))],
    )
    storage = Storage()
    generator = NamedGenerator(
        Names(StudentDisplayName(report_student_id, "합성 별명", False)),
        RenderingGenerator(
            NarrativeGenerator(
                RecordGenerator(Records(data)), NoExternalCalls(), NoExternalCalls()
            ),
            ReportRenderer(),
            storage,
        ),
    )
    service = GenerationService(report_factory, JobLocks(db_engine), generator, FakeCodec(command))
    asyncio.run(
        GenerationConsumer(service, FakeCodec(command))(
            EventEnvelope(
                type="report.generate",
                source="core-service",
                subject=str(report_student_id),
                dataschema="report.generate.v1",
                data={},
            )
        )
    )
    with report_factory() as session:
        report = session.execute(select(weekly_report)).mappings().one()
        items = session.execute(select(report_item)).mappings().all()
        evidence = session.execute(select(report_item_evidence)).mappings().all()
    assert report["status"] == "COMPLETED"
    assert report["narrative"] is None
    assert not evidence
    assert "합성비밀" not in json.dumps([i["payload"] for i in items], ensure_ascii=False)
    assert any(i["item_type"] == "METRIC" for i in items)
    assert len(storage.files) == 6  # full/free × HTML, PDF, Markdown
    for key, body in storage.files.items():
        if key.lower().endswith((".html", ".md")):
            assert "합성비밀" not in body.decode("utf-8")
        elif key.lower().endswith(".pdf"):
            from io import BytesIO

            from pypdf import PdfReader

            text = "".join(page.extract_text() for page in PdfReader(BytesIO(body)).pages)
            assert "합성비밀" not in text
