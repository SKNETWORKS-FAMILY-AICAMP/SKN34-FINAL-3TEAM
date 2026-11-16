"""#479 synthetic report -> learning/AI contracts, persistence and rendered artifacts."""

import asyncio
import json
from dataclasses import replace
from io import BytesIO

import httpx
import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.clients.ai_client import AiClient, ExplanationResponse
from app.clients.base import internal_client
from app.clients.learning_client import LearningClient
from app.generation.explanation_generator import ExplanationGenerator
from app.generation.models import ItemType, PeriodType
from app.generation.presentation import from_result, without_ai
from app.generation.records import EvidenceRecord, JudgmentRecord, RecordContractError, ThinkingType
from app.generation.repository import (
    ReportRepository,
    report_item,
    report_item_evidence,
    weekly_report,
)
from app.query.service import QueryService
from app.rendering.renderer import ReportRenderer
from app.security import UserContext, bind_user_context, reset_user_context
from tests.record_helpers import PERIOD, attempt_for, page, wire_attempt
from tests.render_helpers import fixed_result
from tests.report_helpers import command_for

TEXT = "나무가 그늘을 만들어 줍니다. 그래서 나무를 보호해야 합니다."
EXPLANATION = "잘한 점: 나무의 역할을 그늘이라는 구체적인 예로 설명했습니다."
SCORES = dict(
    hol=3,
    task_1=3,
    content_1=3,
    content_2=3,
    content_3=3,
    organization_1=3,
    organization_2=3,
    expression_1=3,
    expression_2=3,
)


def scored(student, kind=ThinkingType.ANALYZE, **kwargs):
    attempt = attempt_for(student, texts=(TEXT,), **kwargs)
    answer = replace(
        attempt.answers[0],
        judgment=JudgmentRecord(
            "PARTIAL", False, (), model_scores={"m2": {"scores": dict(SCORES)}, "m1": None}
        ),
    )
    return replace(attempt, thinking_type=kind, answers=(answer,))


class Records:
    def __init__(self, attempts):
        self.attempts, self.calls = attempts, 0

    async def explanation_attempts(self, student, period):
        self.calls += 1
        return self.attempts

    async def evidence(self, student, links):
        return tuple(
            EvidenceRecord(link.answer_id, link.attempt_id, link.answer_version, TEXT, True)
            for link in links
        )


class Base:
    def __init__(self, result):
        self.result = result

    async def generate(self, command, report):
        return self.result


class AI:
    def __init__(self, *, fault=None, quote=TEXT, text=EXPLANATION):
        self.calls, self.fault, self.quote, self.text = [], fault, quote, text

    async def explanation(self, payload, timeout):
        self.calls.append((payload, timeout))
        if self.fault == "timeout":
            await asyncio.sleep(1)
        if isinstance(self.fault, Exception):
            raise self.fault
        if self.fault == "inactive":
            return ExplanationResponse(active=False)
        return ExplanationResponse.model_validate(
            {
                "active": True,
                "explanation": {"text": self.text, "quote": self.quote},
                "versions": {"model": "synthetic@1", "prompt": "synthetic@1"},
            }
        )


def setup_case(attempts=None, ai=None):
    report, base = fixed_result()
    command = replace(
        command_for(report.student_id),
        display_name="합성별명",
        grade=5,
        explanation_enabled=True,
        parent_sharing_enabled=True,
        narrative_enabled=True,
    )
    learning = Records(attempts if attempts is not None else [scored(report.student_id)])
    ai = ai or AI()
    generator = ExplanationGenerator(Base(base), ai, learning)
    return command, report, base, learning, ai, generator


def test_scoreless_m2_preparation_is_not_an_explanation_candidate():
    student = fixed_result()[0].student_id
    attempt = scored(student)
    answer = replace(
        attempt.answers[0],
        judgment=JudgmentRecord(
            "CORRECT",
            False,
            (),
            model_scores={
                "m2": None,
                "m2Preparation": {"chars": 3, "notices": ["EMPTY_AFTER_CLEANING"]},
            },
        ),
    )
    command, report, base, _, ai, generator = setup_case([replace(attempt, answers=(answer,))])
    result = asyncio.run(generator.generate(command, report))
    assert not ai.calls
    assert result.items == base.items
    assert result.state == base.state


def test_latest_answer_per_type_max_three_and_existing_report_unchanged():
    student = fixed_result()[0].student_id
    rows = [
        scored(student, kind, times=[f"2026-10-{20 + i}T10:00:00+09:00"])
        for i, kind in enumerate(ThinkingType)
    ]
    newer = scored(student, ThinkingType.REFLECT, times=["2026-10-25T20:00:00+09:00"])
    rows.extend([newer, scored(student, times=["2026-10-26T00:00:00+09:00"])])
    command, report, base, _, ai, generator = setup_case(rows)
    result = asyncio.run(generator.generate(command, report))
    explanations = [i for i in result.items if i.type == ItemType.EXPLANATION]
    assert len(explanations) == len(ai.calls) == 3
    assert explanations[0].payload["answerId"] == str(newer.answers[0].id)
    assert len({i.payload["thinkingType"] for i in explanations}) == 3
    assert result.items[: len(base.items)] == base.items
    assert result.narrative == base.narrative and result.state == base.state
    assert result.narrative["modelExplanation"] is None
    assert result.explanation_state == "INCLUDED"
    for item in explanations:
        assert item.verified and item.evidence[0].answer_version == item.payload["answerVersion"]
    assert set(ai.calls[0][0]) == {"grade", "inputType", "text", "scores"}
    assert ai.calls[0][1] == 130


@pytest.mark.parametrize("fault", ["inactive", "timeout", RuntimeError("PRIVATE RAW TEXT")])
def test_failures_only_omit_explanation(monkeypatch, caplog, fault):
    monkeypatch.setenv("REPORT_EXPLANATION_TIMEOUT_SECONDS", "0.01")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        command, report, base, _, _, generator = setup_case(ai=AI(fault=fault))
        result = asyncio.run(generator.generate(command, report))
        assert result.explanation_state == "NOT_INCLUDED"
        assert result.items == base.items and result.state == base.state
        assert "PRIVATE RAW TEXT" not in caplog.text
    finally:
        get_settings.cache_clear()


def test_total_budget_preserves_already_verified_items(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("REPORT_EXPLANATION_BUDGET_SECONDS", "0.03")
    get_settings.cache_clear()

    class Partial(AI):
        async def explanation(self, payload, timeout):
            if self.calls:
                await asyncio.sleep(1)
            return await super().explanation(payload, timeout)

    try:
        student = fixed_result()[0].student_id
        command, report, base, _, _, generator = setup_case(
            [scored(student, kind) for kind in list(ThinkingType)[:3]], Partial()
        )
        result = asyncio.run(generator.generate(command, report))
        assert result.explanation_state == "INCLUDED"
        assert len(result.items) == len(base.items) + 1
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "changes,state",
    [
        ({"period_type": PeriodType.DAILY}, None),
        ({"explanation_enabled": False}, None),
        ({"parent_sharing_enabled": False}, "NO_TARGET"),
    ],
)
def test_daily_free_private_make_no_explanation_calls(changes, state):
    command, report, _, learning, ai, generator = setup_case()
    if changes.get("period_type") == PeriodType.DAILY:
        changes = {**changes, "period_to": command.period_from}
    result = asyncio.run(generator.generate(replace(command, **changes), report))
    assert result.explanation_state == state
    assert not ai.calls and learning.calls == 0


@pytest.mark.parametrize("grade", [None, True, 3, 4, 7, 9])
def test_missing_or_unsupported_grade_does_not_invent_a_grade(grade):
    command, report, _, _, ai, generator = setup_case()
    result = asyncio.run(generator.generate(replace(command, grade=grade), report))
    assert result.explanation_state == "NOT_INCLUDED" and not ai.calls


def test_no_scores_is_no_target_and_essay_grade_four_is_supported():
    student = fixed_result()[0].student_id
    command, report, _, _, ai, generator = setup_case([attempt_for(student)])
    assert asyncio.run(generator.generate(command, report)).explanation_state == "NO_TARGET"
    assert not ai.calls
    attempt = scored(student)
    answer = replace(
        attempt.answers[0],
        input_type="ESSAY",
        judgment=JudgmentRecord(
            "PARTIAL", False, (), model_scores={"m2": {"scores": {"org": 2, "cont": 3, "exp": 1}}}
        ),
    )
    command, report, _, _, ai, generator = setup_case([replace(attempt, answers=(answer,))])
    result = asyncio.run(generator.generate(replace(command, grade=4), report))
    assert result.explanation_state == "INCLUDED"
    assert ai.calls[0][0]["scores"] == {"org": 2, "cont": 3, "exp": 1}


@pytest.mark.parametrize(
    "quote,text",
    [
        ("없는 인용", EXPLANATION),
        ("", EXPLANATION),
        (TEXT, "점수는 높습니다."),
        (TEXT, "총 3개입니다."),
        (TEXT, "사고력이 좋아졌어요."),
        (TEXT, '"없는 구절"을 썼습니다.'),
        (TEXT, "합성별명이 잘했습니다."),
        (TEXT, "세 문장으로 표현했습니다."),
        (TEXT, "한 문장으로 표현했습니다."),
        (TEXT, "생각을 두번 고쳤습니다."),
    ],
)
def test_invalid_quotes_numbers_and_claims_are_not_saved(quote, text):
    command, report, base, _, _, generator = setup_case(ai=AI(quote=quote, text=text))
    result = asyncio.run(generator.generate(command, report))
    assert result.items == base.items and result.explanation_state == "NOT_INCLUDED"


@pytest.mark.parametrize(
    "text",
    [
        "잘한 점: 정확한 문장으로 그늘의 역할을 설명했습니다.",
        "함께 이야기해 볼 점: 적절한 글자 수를 생각해 보면 좋겠습니다.",
    ],
)
def test_adjective_ending_is_not_a_korean_count(text):
    # #508: "-한" adjective endings are not the numeral "한".
    command, report, base, _, _, generator = setup_case(ai=AI(text=text))
    result = asyncio.run(generator.generate(command, report))
    assert result.explanation_state == "INCLUDED"
    assert result.items[-1].payload["text"] == text


def test_excluded_latest_answer_falls_back_to_same_type():
    # #508: pre-call exclusions try the next answer of the same type before giving up.
    student = fixed_result()[0].student_id
    valid = scored(student, times=["2026-10-20T10:00:00+09:00"])
    stale = scored(student, times=["2026-10-21T10:00:00+09:00"])
    latest = scored(student, times=["2026-10-22T10:00:00+09:00"])
    latest = replace(
        latest,
        answers=(
            replace(
                latest.answers[0],
                judgment=replace(latest.answers[0].judgment, corrected=True),
            ),
        ),
    )

    class StaleEvidence(Records):
        async def evidence(self, student, links):
            if links[0].answer_id == stale.answers[0].id:
                return (EvidenceRecord(links[0].answer_id, links[0].attempt_id, 99, TEXT, True),)
            return await super().evidence(student, links)

    command, report, _, _, ai, _ = setup_case()
    learning = StaleEvidence([latest, stale, valid])
    generator = ExplanationGenerator(Base(fixed_result()[1]), ai, learning)
    result = asyncio.run(generator.generate(command, report))
    explanations = [i for i in result.items if i.type == ItemType.EXPLANATION]
    assert result.explanation_state == "INCLUDED" and len(ai.calls) == 1
    assert explanations[0].payload["answerId"] == str(valid.answers[0].id)


def test_failed_call_does_not_retry_same_type():
    student = fixed_result()[0].student_id
    rows = [scored(student, times=[f"2026-10-2{i}T10:00:00+09:00"]) for i in range(3)]
    command, report, _, _, ai, generator = setup_case(rows, AI(fault="inactive"))
    result = asyncio.run(generator.generate(command, report))
    assert result.explanation_state == "NOT_INCLUDED" and len(ai.calls) == 1


@pytest.mark.parametrize("quote", [TEXT, None])
def test_pdf_html_markdown_and_free_projection(quote):
    command, report, _, _, _, generator = setup_case(ai=AI(quote=quote))
    result = asyncio.run(generator.generate(command, report))
    detail = from_result(report, result)
    assert detail["explanations"]["items"][0]["quote"] == quote
    rendered = ReportRenderer().render(detail, command.display_name)
    assert EXPLANATION in rendered["HTML"].decode() and EXPLANATION in rendered["MD"].decode()
    pdf = PdfReader(BytesIO(rendered["PDF"]))
    assert "대표 답변 설명" in "\n".join(page.extract_text() for page in pdf.pages)
    free = ReportRenderer().render(without_ai(detail), command.display_name)
    assert all(EXPLANATION not in free[f].decode() for f in ("HTML", "MD"))


@pytest.mark.parametrize(
    "has_scores,state,notice",
    [
        (True, "NOT_INCLUDED", "설명 미포함"),
        (False, "NO_TARGET", "설명 대상 답변이 없어"),
    ],
)
def test_omitted_explanations_render_in_all_formats(has_scores, state, notice):
    student = fixed_result()[0].student_id
    attempts = [scored(student)] if has_scores else [attempt_for(student)]
    command, report, base, _, _, generator = setup_case(attempts, AI(fault="inactive"))
    result = asyncio.run(generator.generate(command, report))
    assert result.explanation_state == state and result.state == base.state
    rendered = ReportRenderer().render(from_result(report, result), command.display_name)
    assert all(notice in rendered[fmt].decode() for fmt in ("HTML", "MD"))
    pdf = PdfReader(BytesIO(rendered["PDF"]))
    assert notice in "\n".join(page.extract_text() for page in pdf.pages)


def test_system_opt_in_learning_and_ai_wire_contracts():
    student = fixed_result()[0].student_id
    attempt = scored(student)
    wire = wire_attempt(attempt)
    wire["answers"][0]["feedback"]["judgment"] = {
        "result": "PARTIAL",
        "trial": False,
        "elements": [],
        "modelScores": {"m2": {"scores": SCORES}, "m1": None, "skipped": None},
    }

    def handler(request):
        assert request.headers["X-User-Role"] == "SYSTEM"
        assert request.headers["X-Student-Scope"] == str(student)
        if request.method == "GET":
            assert request.url.params["includeModelScores"] == "true"
            return httpx.Response(200, json=page(student, [wire]))
        assert request.url.path == "/internal/report-explanations"
        assert set(json.loads(request.content)) == {"grade", "inputType", "text", "scores"}
        return httpx.Response(
            200,
            json={
                "active": True,
                "explanation": {"text": EXPLANATION, "quote": None},
                "versions": {"model": "test@1", "prompt": "test@1"},
            },
        )

    async def run():
        async with internal_client(
            "http://synthetic", transport=httpx.MockTransport(handler)
        ) as http:
            client = LearningClient(http)
            reset = bind_user_context(UserContext(None, "PARENT", frozenset([str(student)])))
            try:
                with pytest.raises(RecordContractError):
                    await client.explanation_attempts(student, PERIOD)
            finally:
                reset_user_context(reset)
            reset = bind_user_context(UserContext(None, "SYSTEM", frozenset([str(student)])))
            try:
                records = await client.explanation_attempts(student, PERIOD)
                assert records[0].answers[0].judgment.model_scores["m2"]["scores"] == SCORES
                response = await AiClient(http).explanation(
                    {"grade": 5, "inputType": "NARRATIVE", "text": TEXT, "scores": SCORES}, 130
                )
                assert response.active and response.explanation.quote is None
            finally:
                reset_user_context(reset)

    asyncio.run(run())


@pytest.mark.parametrize("fault", [None, "inactive", RuntimeError("synthetic outage")])
def test_real_db_persists_state_items_and_evidence_and_free_hides(
    report_factory, report_student_id, fault
):
    command, _, base, _, _, generator = setup_case(
        [scored(report_student_id)], AI(fault=fault, quote=None)
    )
    command = replace(command, student_id=report_student_id)
    repository = ReportRepository()
    with report_factory.begin() as session:
        report, _ = repository.get_or_create(session, command)
    result = asyncio.run(generator.generate(command, report))
    with report_factory.begin() as session:
        terminal = repository.finish(session, report.id, result=result)
        assert terminal.status == "COMPLETED"
        row = (
            session.execute(select(weekly_report).where(weekly_report.c.id == report.id))
            .mappings()
            .one()
        )
        assert row["verification"]["explanationState"] == result.explanation_state
        items = (
            session.execute(
                select(report_item).where(
                    report_item.c.report_id == report.id, report_item.c.item_type == "EXPLANATION"
                )
            )
            .mappings()
            .all()
        )
        assert len(items) == (0 if fault else 1)
        if items:
            link = (
                session.execute(
                    select(report_item_evidence).where(
                        report_item_evidence.c.item_id == items[0]["id"]
                    )
                )
                .mappings()
                .one()
            )
            assert str(link["answer_id"]) == items[0]["payload"]["answerId"]

    async def query():
        reset = bind_user_context(UserContext(None, "PARENT", frozenset([str(report_student_id)])))
        try:
            service = QueryService(report_factory, None, None, None)
            paid = await service.detail(report.id, None, True)
            free = await service.detail(report.id, None, False)
            assert paid["explanations"]["state"] == result.explanation_state
            assert free["explanations"] is None
            assert EXPLANATION not in json.dumps(free, ensure_ascii=False, default=str)
        finally:
            reset_user_context(reset)

    asyncio.run(query())
