from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import create_app
from app.clients.storage import report_key
from app.database import transaction
from app.generation.models import ItemType, ReportFile
from app.generation.records import EvidenceRecord
from app.generation.repository import ReportRepository, report_item
from app.query.router import query_service
from app.query.service import QueryService
from tests.render_helpers import fixed_result
from tests.report_helpers import command_for


def seed_report(factory, student, *, failure=False):
    repository = ReportRepository()
    with transaction(factory) as session:
        report, _ = repository.get_or_create(session, command_for(student))
        if failure:
            repository.finish(session, report.id, failure_reason="SYNTHETIC_FAILURE")
        else:
            _, result = fixed_result(student)
            result = replace(
                result,
                items=tuple(
                    replace(i, payload={**i.payload, "summary": "유료 전용 요약"})
                    if i.type == ItemType.THINKING_TYPE
                    else i
                    for i in result.items
                ),
                files=tuple(
                    ReportFile(f, report_key(student, report.id, report.revision, f), 10)
                    for f in ("PDF", "MD", "HTML")
                ),
            )
            repository.finish(session, report.id, result=result)
        return report.id


class FakeEvidence:
    def __init__(self, available=True):
        self.available, self.calls = available, 0

    async def evidence(self, student, links):
        self.calls += 1
        return tuple(
            EvidenceRecord(
                link.answer_id,
                link.attempt_id,
                link.answer_version,
                "새로 조회한 합성 원문" if self.available else None,
                self.available,
            )
            for link in links
        )


class Signer:
    def __init__(self):
        self.calls = []

    def presigned_url(self, key, ttl, filename):
        self.calls.append((key, ttl, filename))
        return {
            "url": "https://synthetic.invalid/download",
            "expiresAt": (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat(),
        }


@pytest.fixture
def api(report_factory):
    app, evidence, storage = create_app(), FakeEvidence(), Signer()

    def service():
        return QueryService(report_factory, evidence, lambda: storage, 300)

    app.dependency_overrides[query_service] = service
    with TestClient(app) as client:
        yield client, evidence, storage


def headers(student, *, premium=False):
    return {
        "X-Internal-Token": "test-token",
        "X-Student-Scope": str(student),
        "X-User-Role": "PARENT",
        "X-Report-Narrative-Enabled": str(premium).lower(),
    }


def test_detail_default_latest_and_explicit_previous_revision(
    api, report_factory, report_student_id
):
    first = seed_report(report_factory, report_student_id)
    second = seed_report(report_factory, report_student_id)
    client, _, _ = api
    latest = client.get(
        f"/internal/reports/{first}", headers=headers(report_student_id, premium=True)
    )
    assert latest.status_code == 200
    body = latest.json()
    assert body["reportId"] == str(second) and body["revision"] == 2
    assert [r["revision"] for r in body["revisions"]] == [2, 1]
    assert set(body) >= {
        "metrics",
        "thinkingTypes",
        "changes",
        "reflections",
        "quotes",
        "period",
        "inclusionRule",
        "narrative",
        "verification",
        "versions",
    }
    assert body["metrics"][0]["sourceType"] == "RECORD"
    previous = client.get(
        f"/internal/reports/{first}?revision=1", headers=headers(report_student_id, premium=True)
    )
    assert previous.status_code == 200 and previous.json()["reportId"] == str(first)


def test_free_or_missing_entitlement_header_hides_stored_ai(api, report_factory, report_student_id):
    report_id = seed_report(report_factory, report_student_id)
    client, _, _ = api
    auth = headers(report_student_id)
    auth.pop("X-Report-Narrative-Enabled")
    result = client.get(f"/internal/reports/{report_id}", headers=auth)
    assert result.status_code == 200
    body = result.json()
    assert body["narrative"] is None and body["eveningQuestion"] is None
    assert all("summary" not in group for group in body["thinkingTypes"])


@pytest.mark.parametrize("premium", [False, True])
def test_nullable_followup_survives_db_and_public_response(
    api, report_factory, report_student_id, premium
):
    report_id = seed_report(report_factory, report_student_id)
    condition = (report_item.c.report_id == report_id, report_item.c.item_type == ItemType.CHANGE)
    with transaction(report_factory) as session:
        payload = session.scalar(select(report_item.c.payload).where(*condition))
        payload = {**payload, "followup": None}
        session.execute(report_item.update().where(*condition).values(payload=payload))
    client, _, _ = api
    response = client.get(
        f"/internal/reports/{report_id}", headers=headers(report_student_id, premium=premium)
    )
    assert response.status_code == 200
    assert response.json()["childId"] == str(report_student_id)
    assert response.json()["changes"][0]["followup"] is None
    with report_factory() as session:
        assert session.scalar(select(report_item.c.payload).where(*condition)) == payload


@pytest.mark.parametrize("premium", [False, True])
@pytest.mark.parametrize(
    "code,label,written",
    [
        ("EASY", "쉬웠어요", True),
        ("NORMAL", "보통", True),
        ("HARD", "어려웠어요", True),
        (None, None, False),
    ],
)
def test_reflection_response_labels_and_null_text_preserve_stored_codes(
    api, report_factory, report_student_id, premium, code, label, written
):
    report_id = seed_report(report_factory, report_student_id)
    condition = (
        report_item.c.report_id == report_id,
        report_item.c.item_type == ItemType.REFLECTION,
    )
    with transaction(report_factory) as session:
        payload = session.scalar(select(report_item.c.payload).where(*condition))
        payload = {**payload, "difficulty": code, "text": None, "written": written}
        session.execute(report_item.update().where(*condition).values(payload=payload))

    client, _, _ = api
    response = client.get(
        f"/internal/reports/{report_id}", headers=headers(report_student_id, premium=premium)
    )
    assert response.status_code == 200
    [reflection] = response.json()["reflections"]
    assert reflection["difficulty"] == label
    assert reflection["written"] is written and reflection["text"] is None
    with report_factory() as session:
        assert session.scalar(select(report_item.c.payload).where(*condition)) == payload


def test_latest_is_selected_before_status_filter(api, report_factory, report_student_id):
    seed_report(report_factory, report_student_id)
    seed_report(report_factory, report_student_id, failure=True)
    client, _, _ = api
    result = client.get(
        f"/internal/reports?studentId={report_student_id}&status=COMPLETED",
        headers=headers(report_student_id),
    )
    assert result.status_code == 200 and result.json()["totalElements"] == 0
    result = client.get(
        f"/internal/reports?studentId={report_student_id}", headers=headers(report_student_id)
    )
    assert result.json()["items"][0]["status"] == "FAILED" and result.json()["totalElements"] == 1


@pytest.mark.parametrize("path", ["detail", "evidence", "file", "list"])
def test_student_scope_checked_on_every_endpoint(api, report_factory, report_student_id, path):
    report_id = seed_report(report_factory, report_student_id)
    client, source, storage = api
    url = {
        "detail": f"/internal/reports/{report_id}",
        "evidence": f"/internal/reports/{report_id}/evidence/{uuid4()}",
        "file": f"/internal/reports/{report_id}/files/pdf",
        "list": f"/internal/reports?studentId={report_student_id}",
    }[path]
    response = client.get(url, headers=headers(uuid4()))
    assert response.status_code == 403 and response.json()["code"] == "FORBIDDEN"
    assert source.calls == 0 and storage.calls == []


@pytest.mark.parametrize("available", [True, False])
def test_evidence_is_fresh_and_deleted_text_is_not_reused(
    api, report_factory, report_student_id, available
):
    report_id = seed_report(report_factory, report_student_id)
    with report_factory() as session:
        item_id = session.scalar(
            select(report_item.c.id).where(
                report_item.c.report_id == report_id, report_item.c.item_type == "QUOTE"
            )
        )
    client, evidence, _ = api
    evidence.available = available
    result = client.get(
        f"/internal/reports/{report_id}/evidence/{item_id}", headers=headers(report_student_id)
    )
    assert result.status_code == 200
    [item] = result.json()["items"]
    assert item["available"] is available
    if available:
        assert item["quote"] == "새로 조회한 합성 원문"
    else:
        assert "quote" not in item


@pytest.mark.parametrize("premium", [True, False])
def test_download_uses_current_entitlement_variant(api, report_factory, report_student_id, premium):
    report_id = seed_report(report_factory, report_student_id)
    client, _, storage = api
    result = client.get(
        f"/internal/reports/{report_id}/files/pdf",
        headers=headers(report_student_id, premium=premium),
    )
    assert result.status_code == 200
    assert storage.calls[0][0].endswith("/full/pdf" if premium else "/free/pdf")
    assert storage.calls[0][1] == 300


def test_missing_and_invalid_revision_errors(api, report_factory, report_student_id):
    report_id = seed_report(report_factory, report_student_id)
    client, _, _ = api
    assert (
        client.get(
            f"/internal/reports/{report_id}?revision=99", headers=headers(report_student_id)
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/internal/reports/{report_id}?revision=0", headers=headers(report_student_id)
        ).status_code
        == 400
    )
    assert (
        client.get(f"/internal/reports/{uuid4()}", headers=headers(report_student_id)).status_code
        == 404
    )


def test_openapi_matches_checked_in_contract():
    import json
    from pathlib import Path

    contract = Path(__file__).resolve().parents[3] / "contracts/openapi/report-service.yaml"
    assert create_app().openapi() == json.loads(contract.read_text(encoding="utf-8"))


def test_response_validation_does_not_log_student_text(
    api, report_factory, report_student_id, caplog
):
    report_id = seed_report(report_factory, report_student_id)
    with transaction(report_factory) as session:
        session.execute(
            report_item.update()
            .where(report_item.c.report_id == report_id, report_item.c.item_type == "METRIC")
            .values(payload={"label": "PRIVATE-STUDENT-TEXT", "count": "invalid"})
        )
    client, _, _ = api
    response = client.get(f"/internal/reports/{report_id}", headers=headers(report_student_id))
    assert response.status_code == 500 and response.json()["code"] == "INTERNAL_ERROR"
    assert "PRIVATE-STUDENT-TEXT" not in caplog.text + response.text
