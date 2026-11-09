import asyncio
from dataclasses import replace
from datetime import date, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.generation.codec import ReportV1Codec
from app.generation.daily import DailyReportBuilder
from app.generation.models import ItemType, PeriodType
from app.generation.narrative_generator import NarrativeGenerator
from app.generation.presentation import from_result, without_ai
from app.generation.record_generator import RecordGenerator
from app.generation.records import (
    EvidenceRecord,
    JudgedElement,
    JudgmentRecord,
    Period,
    RecordContractError,
)
from app.generation.repository import ReportRepository, weekly_report
from app.generation.theme_summary import ThemeSummaryBuilder
from app.messaging.contracts import InvalidEvent
from app.messaging.envelope import EventEnvelope
from app.query.schemas import ReportDetail
from app.rendering.renderer import ReportRenderer
from tests.record_helpers import attempt_for, records_for
from tests.report_helpers import command_for


def daily_fixture(day="2026-10-24"):
    student = uuid4()
    attempt = attempt_for(
        student,
        texts=("첫 답.", "근거를 보완한 답."),
        times=(f"{day}T09:00:00+09:00", f"{day}T10:00:00+09:00"),
        status="COMPLETED",
    )
    element = JudgedElement(uuid4(), "ANALYZE_REASON", False, True, "까닭", "근거를 보완")
    first = replace(attempt.answers[0], followup="왜 그런가요?")
    last = replace(attempt.answers[-1], judgment=JudgmentRecord("CORRECT", False, (element,)))
    attempt = replace(
        attempt,
        mission_id=uuid4(),
        context="THEME_REVIEW",
        answers=(first, last),
        completed_at=last.submitted_at,
    )
    period = Period(date.fromisoformat(day), date.fromisoformat(day))
    records = records_for(student, [attempt], period=period)
    learning = AsyncMock()
    learning.daily_records.return_value = records
    learning.evidence.return_value = (
        EvidenceRecord(last.id, attempt.id, last.version, last.text, True),
    )
    command = replace(
        command_for(student),
        period_from=period.start,
        period_to=period.end,
        period_type=PeriodType.DAILY,
        parent_sharing_enabled=True,
        narrative_enabled=True,
    )
    return command, records, learning


@pytest.mark.parametrize("day", ["2026-10-24", "2026-10-25", "2026-10-26"])
def test_daily_facts_weekend_and_monday_never_call_ai(day):
    command, records, learning = daily_fixture(day)
    ai = AsyncMock()
    result = asyncio.run(
        NarrativeGenerator(RecordGenerator(learning), ai, learning).generate(command, None)
    )
    assert result.narrative is result.evening_question is result.theme_summary is None
    ai.generate.assert_not_called()
    assert not ai.mock_calls
    learning.records.assert_not_called()
    assert result.items[0].payload["value"] is None
    problem = next(i for i in result.items if i.type == ItemType.PROBLEM)
    assert problem.payload["missionId"] == str(records.attempts[0].mission_id)
    assert problem.payload["context"] == "THEME_REVIEW"
    assert problem.payload["judgment"] == "CORRECT"
    assert problem.payload["followups"] == [
        {"question": "왜 그런가요?", "answer": "근거를 보완한 답."}
    ]
    assert problem.payload["quotes"][0]["verified"]
    assert problem.evidence


def test_corrected_judgment_shows_new_result_without_original_elements():
    _, records, learning = daily_fixture()
    attempt = records.attempts[0]
    last = attempt.answers[-1]
    judgment = replace(last.judgment, result="RETHINK", corrected=True)
    corrected = replace(attempt, answers=(*attempt.answers[:-1], replace(last, judgment=judgment)))
    result = asyncio.run(
        DailyReportBuilder().build(replace(records, attempts=(corrected,)), True, learning)
    )
    problem = next(i for i in result.items if i.type == ItemType.PROBLEM)
    assert problem.payload["judgment"] == "RETHINK" and problem.payload["elements"] == []


def test_private_daily_has_no_answer_quote_or_evidence_before_storage():
    command, records, learning = daily_fixture()
    result = asyncio.run(
        RecordGenerator(learning).generate(replace(command, parent_sharing_enabled=False), None)
    )
    problem = result.items[1]
    assert problem.payload["finalAnswer"] is None
    assert problem.payload["followups"] == problem.payload["quotes"] == []
    assert problem.evidence == ()
    assert problem.payload["reflection"]["text"] is None
    learning.evidence.assert_not_called()
    assert "근거를 보완한 답." not in str(result)


def test_invalid_quote_does_not_become_verified_or_no_record():
    _, records, learning = daily_fixture()
    learning.evidence.return_value = ()
    with pytest.raises(RecordContractError, match="verified"):
        asyncio.run(DailyReportBuilder().build(records, True, learning))


def test_daily_no_record_and_prior_day_submission():
    command, records, learning = daily_fixture()
    attempt = records.attempts[0]
    prior = tuple(
        replace(a, submitted_at=a.submitted_at - timedelta(days=1)) for a in attempt.answers
    )
    records = replace(records, attempts=(replace(attempt, answers=prior),))
    result = asyncio.run(DailyReportBuilder().build(records, False, learning))
    assert result.state == "OK"  # Completed today, even if submitted yesterday.
    empty = asyncio.run(DailyReportBuilder().build(replace(records, attempts=()), False, learning))
    assert empty.state == "NO_RECORD" and empty.items[0].payload["count"] == 0


def test_codec_default_weekly_daily_and_invalid_range():
    command, _, _ = daily_fixture()
    data = {
        "jobId": str(command.job_id),
        "studentId": str(command.student_id),
        "periodFrom": "2026-10-26",
        "periodTo": "2026-11-01",
        "trigger": "SCHEDULE",
        "narrativeEnabled": False,
    }

    def decode():
        return ReportV1Codec().decode(
            EventEnvelope(
                type="report.generate",
                source="core-service",
                dataschema="report.generate.v1",
                subject=str(command.student_id),
                data=data,
            )
        )

    assert decode().period_type == "WEEKLY"
    data["periodType"] = "DAILY"
    with pytest.raises(InvalidEvent):
        decode()
    data["periodTo"] = data["periodFrom"]
    assert decode().period_type == "DAILY"
    data["narrativeEnabled"] = True
    with pytest.raises(InvalidEvent):
        decode()


def test_monday_revisions_lists_and_database_constraints(db_session):
    command = command_for(uuid4())
    daily = replace(command, period_type=PeriodType.DAILY, period_to=command.period_from)
    repo = ReportRepository()
    d1, _ = repo.get_or_create(db_session, daily)
    w1, _ = repo.get_or_create(db_session, replace(command, job_id=uuid4()))
    d2, _ = repo.get_or_create(db_session, replace(daily, job_id=uuid4()))
    assert (d1.revision, w1.revision, d2.revision) == (1, 1, 2)
    rows, total = repo.latest_page(db_session, command.student_id, None, 0, 20)
    assert total == 2 and {r["id"] for r in rows} == {w1.id, d2.id}
    assert [
        r["id"] for r in repo.latest_page(db_session, command.student_id, None, 0, 20, "DAILY")[0]
    ] == [d2.id]
    assert [
        r["id"]
        for r in repo.revisions(db_session, command.student_id, command.period_from, "WEEKLY")
    ] == [w1.id]
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(
            weekly_report.update()
            .where(weekly_report.c.id == d1.id)
            .values(narrative={"text": "forbidden"})
        )


def test_daily_persistence_response_and_rendering(db_session):
    command, records, learning = daily_fixture()
    repo = ReportRepository()
    report, _ = repo.get_or_create(db_session, command)
    result = asyncio.run(DailyReportBuilder().build(records, True, learning))
    repo.finish(db_session, report.id, result=result)
    assert (
        db_session.scalar(
            select(weekly_report.c.period_type).where(weekly_report.c.id == report.id)
        )
        == "DAILY"
    )
    detail = from_result(report, result)
    ReportDetail.model_validate(detail)
    assert without_ai(detail) == detail
    rendered = ReportRenderer().render(detail, "합성학생")
    assert b"%PDF" in rendered["PDF"][:10]
    assert "근거를 보완한 답." in rendered["HTML"].decode()
    assert "일일 리포트" in rendered["MD"].decode()


def test_theme_scope_no_participation_and_http_failure():
    student = uuid4()
    period = Period(date(2026, 10, 26), date(2026, 11, 1))
    learning = AsyncMock()
    raw = {
        "studentId": str(student),
        "weekStart": "2026-10-26",
        "state": "NO_RECORD",
        "themeId": None,
        "title": None,
        "days": [],
        "completed": False,
        "reviewRetries": [],
    }
    learning.theme_summary.return_value = raw
    builder = ThemeSummaryBuilder(learning)
    assert asyncio.run(builder.build(student, period))["state"] == "NO_RECORD"
    learning.theme_summary.return_value = {**raw, "studentId": str(uuid4())}
    with pytest.raises(RecordContractError):
        asyncio.run(builder.build(student, period))
    learning.theme_summary.side_effect = RuntimeError("upstream unavailable")
    with pytest.raises(RuntimeError):
        asyncio.run(builder.build(student, period))


def test_weekly_theme_does_not_replace_original_metrics_and_checks_comparison():
    student = uuid4()
    from tests.record_helpers import PERIOD

    records = records_for(student, [attempt_for(student)])
    learning = AsyncMock()
    learning.records.return_value = records
    raw = {
        "studentId": str(student),
        "weekStart": str(PERIOD.start),
        "state": "OK",
        "themeId": str(uuid4()),
        "title": "합성 테마",
        "days": [{"day": "MON", "missionId": str(uuid4()), "completed": True}],
        "completed": False,
        "reviewRetries": [
            {
                "missionId": str(uuid4()),
                "comparison": {
                    "state": "COMPARABLE",
                    "elements": [
                        {"label": "까닭", "previousSatisfied": False, "currentSatisfied": True}
                    ],
                },
            }
        ],
    }
    learning.theme_summary.return_value = raw
    command = command_for(student)
    plain = asyncio.run(RecordGenerator(learning).generate(command, None))
    enriched = asyncio.run(
        RecordGenerator(learning, theme_builder=ThemeSummaryBuilder(learning)).generate(
            command, None
        )
    )
    assert plain.items == enriched.items
    assert enriched.theme_summary["title"] == "합성 테마"
    html = (
        ReportRenderer()
        ._templates.get_template("theme.html")
        .render(report={"themeSummary": enriched.theme_summary})
    )
    assert "까닭" in html and "미확인 → 확인" in html
    raw["reviewRetries"][0]["comparison"]["state"] = "CRITERIA_CHANGED"
    with pytest.raises(RecordContractError, match="changed criteria"):
        asyncio.run(ThemeSummaryBuilder(learning).build(student, PERIOD))


def test_daily_job_guard_accepts_one_day_and_preserves_identity(db_session):
    from app.generation.models import JobConflict

    command, _, _ = daily_fixture()
    repo = ReportRepository()
    args = (db_session, command.job_id, command.student_id, command.period_from, command.period_to)
    repo.block(*args, PeriodType.DAILY)
    assert repo.guard(*args, PeriodType.DAILY)["period_type"] == "DAILY"
    with pytest.raises(JobConflict):
        repo.guard(*args, PeriodType.WEEKLY)


def test_theme_summary_is_enabled_with_merged_producer():
    from app.config import Settings

    settings = Settings(internal_token="test-token", database_url="postgresql://unused")
    assert settings.report_theme_summary_enabled is True


def test_daily_reader_uses_completion_endpoint_and_keeps_existing_mission_fields():
    import httpx

    from app.clients.base import internal_client
    from app.clients.learning_client import LearningClient
    from app.security import UserContext, bind_user_context, reset_user_context
    from tests.record_helpers import page, wire_attempt

    command, records, _ = daily_fixture()
    attempt = records.attempts[0]
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.path.endswith("/daily-attempts")
        assert request.headers["X-Student-Scope"] == str(command.student_id)
        row = wire_attempt(attempt)
        row["mission"]["id"] = str(attempt.mission_id)
        row["context"] = "THEME_REVIEW"
        row["answers"][0]["feedback"]["followup"] = {"question": "원문 되묻기"}
        data = page(command.student_id, [row])
        data["period"] = records.period.payload()
        return httpx.Response(200, json=data)

    async def read():
        token = bind_user_context(UserContext(None, "SYSTEM", frozenset({str(command.student_id)})))
        try:
            async with internal_client(
                "http://learning.test", transport=httpx.MockTransport(handler)
            ) as client:
                return await LearningClient(client).daily_records(
                    command.student_id, records.period
                )
        finally:
            reset_user_context(token)

    actual = asyncio.run(read())
    assert len(calls) == 1
    assert actual.attempts[0].mission_id == attempt.mission_id
    assert actual.attempts[0].answers[0].followup == "원문 되묻기"
