import asyncio
import io
import re
from dataclasses import replace
from pathlib import Path

import boto3
import pytest
from moto import mock_aws
from pypdf import PdfReader
from sqlalchemy import select

from app.clients.storage import ObjectStorage, report_key
from app.generation.consumer import GenerationConsumer
from app.generation.locking import JobLocks
from app.generation.models import ItemType
from app.generation.presentation import from_result, without_ai
from app.generation.repository import report_file, weekly_report
from app.generation.service import GenerationService
from app.messaging.envelope import EventEnvelope
from app.rendering.generator import RenderingGenerator
from app.rendering.renderer import ReportRenderer
from tests.render_helpers import fixed_detail, fixed_result
from tests.report_helpers import FakeCodec, command_for


def pdf_text(body):
    pages = []
    for page in PdfReader(io.BytesIO(body)).pages:
        lines = [
            line
            for line in page.extract_text().splitlines()
            if not re.fullmatch(r"\s*\d+\s*/\s*\d+\s*", line)
        ]
        pages.append("\n".join(lines))
    # Font metrics can wrap a Korean word at a different position on Windows/Linux.
    # HTML/MD snapshots preserve whitespace; PDF text snapshots compare logical content.
    return re.sub(r"\s+", "", "".join(pages))


@pytest.fixture(scope="module")
def rendered():
    return ReportRenderer().render(fixed_detail(), "합성학생")


def test_three_formats_match_reviewed_snapshots(rendered):
    root = Path(__file__).parent / "snapshots"
    assert rendered["HTML"].decode() == (root / "weekly.html").read_text(encoding="utf-8")
    assert rendered["MD"].decode() == (root / "weekly.md").read_text(encoding="utf-8")
    assert (
        pdf_text(rendered["PDF"]) == (root / "weekly-pdf.txt").read_text(encoding="utf-8").strip()
    )
    assert "합성학생의주간리포트" in pdf_text(rendered["PDF"])


def test_html_and_markdown_escape_source_content():
    detail = fixed_detail()
    detail["quotes"][0]["text"] = '<script>window.fetch("https://untrusted.invalid")</script>'
    # HTML template can be checked independently without another browser process.
    renderer = ReportRenderer()
    html = renderer._templates.get_template("weekly.html").render(report=detail, name="<img src=x>")
    assert "<script>" not in html and "&lt;script&gt;" in html and "<img src=x>" not in html
    md = renderer.markdown(detail, "<img src=x>")
    assert "<script>" not in md and "<img src=x>" not in md


def test_free_projection_cannot_reveal_old_ai_summary():
    detail = fixed_detail()
    detail["thinkingTypes"][0]["summary"] = "AI가 작성한 요약"
    free = without_ai(detail)
    assert free["narrative"] is None and free["eveningQuestion"] is None
    assert all("summary" not in group for group in free["thinkingTypes"])
    assert detail["narrative"] is not None  # no mutation of the paid stored report


@pytest.mark.parametrize(
    "code,label", [("EASY", "쉬웠어요"), ("NORMAL", "보통"), ("HARD", "어려웠어요")]
)
def test_reflection_labels_match_detail_and_files_without_changing_stored_code(code, label):
    report, result = fixed_result()
    result = replace(
        result,
        items=tuple(
            replace(item, payload={**item.payload, "difficulty": code})
            if item.type == ItemType.REFLECTION
            else item
            for item in result.items
        ),
    )
    detail = from_result(report, result)
    assert detail["reflections"][0]["difficulty"] == label
    assert without_ai(detail)["reflections"][0]["difficulty"] == label
    renderer = ReportRenderer()
    html = renderer._templates.get_template("weekly.html").render(report=detail, name="합성학생")
    markdown = renderer.markdown(detail, "합성학생")
    assert label in html and label in markdown
    assert code not in html and code not in markdown
    [stored] = [item.payload for item in result.items if item.type == ItemType.REFLECTION]
    assert stored["difficulty"] == code


@mock_aws
def test_s3_upload_signature_and_student_scoped_cleanup(rendered):
    from uuid import uuid4

    client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="synthetic",
        aws_secret_access_key="synthetic",
    )
    client.create_bucket(Bucket="synthetic-reports")
    storage = ObjectStorage(client, "synthetic-reports")
    student, other, report = uuid4(), uuid4(), uuid4()
    for format, data in rendered.items():
        storage.put(report_key(student, report, 1, format), data, "application/octet-stream")
    other_key = report_key(other, report, 1, "PDF")
    storage.put(other_key, b"other student", "application/pdf")
    signed = storage.presigned_url(report_key(student, report, 1, "PDF"), 300, "weekly.pdf")
    assert "url" in signed and "expiresAt" in signed
    storage.delete_prefix(f"reports/{student}/")
    assert [i["Key"] for i in client.list_objects_v2(Bucket="synthetic-reports")["Contents"]] == [
        other_key
    ]


class FakeRenderer:
    def render(self, detail, display_name):
        return {"HTML": b"<html>synthetic</html>", "MD": b"synthetic", "PDF": b"%PDF-synthetic"}


class FakeStorage:
    def __init__(self, fail=False):
        self.keys, self.fail = [], fail

    def put(self, key, body, content_type):
        if self.fail:
            raise ConnectionError("synthetic upload failure")
        self.keys.append(key)

    def delete_prefix(self, prefix):
        self.keys = [key for key in self.keys if not key.startswith(prefix)]


@pytest.mark.parametrize("failure", [False, True])
def test_upload_success_or_failure_is_saved_with_report_status(
    report_factory, db_engine, report_student_id, failure
):
    _, result = fixed_result(report_student_id)

    class Previous:
        async def generate(self, command, report):
            return result

    storage = FakeStorage(failure)
    command = replace(command_for(report_student_id), display_name="합성학생")
    generator = RenderingGenerator(Previous(), FakeRenderer(), storage)
    service = GenerationService(report_factory, JobLocks(db_engine), generator, FakeCodec(command))

    async def run():
        await GenerationConsumer(service, FakeCodec(command))(
            EventEnvelope(
                type="report.generate",
                source="core-service",
                subject=str(report_student_id),
                dataschema="report.generate.v1",
                data={},
            )
        )

    asyncio.run(run())
    with report_factory() as session:
        report = session.execute(select(weekly_report)).mappings().one()
        files = session.execute(select(report_file)).mappings().all()
    assert report["status"] == ("FAILED" if failure else "COMPLETED")
    assert len(files) == (0 if failure else 3)
    assert len(storage.keys) == (0 if failure else 6)
