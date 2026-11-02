import asyncio
import json
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest

from app.clients.ai_client import AiClient, NarrativeResponse
from app.clients.base import internal_client
from app.generation.metrics import MetricsCalculator
from app.generation.models import ItemType, ReportState
from app.generation.narrative_generator import NarrativeGenerator
from app.generation.records import EvidenceRecord
from app.generation.verifier import ReportVerifier
from tests.record_helpers import attempt_for, records_for
from tests.report_helpers import command_for


def fixture():
    student = uuid4()
    attempt = attempt_for(student)
    result = MetricsCalculator().calculate(records_for(student, [attempt]))
    answer = attempt.answers[0]
    response = {
        "narrative": {
            "text": "답변 제출 시도 1건이 확인되었습니다.",
            "source": "LLM",
            "modelExplanation": None,
        },
        "eveningQuestion": "어떤 생각이 기억에 남니?",
        "citedQuotes": [],
        "versions": {"prompt": "synthetic-report@1", "model": "synthetic-model@1"},
    }
    evidence = (EvidenceRecord(answer.id, attempt.id, answer.version, answer.text, True),)
    return student, attempt, result, response, evidence


class Previous:
    def __init__(self, result):
        self.result = result

    async def generate(self, command, report):
        return self.result


class EvidenceReader:
    def __init__(self, evidence):
        self.data, self.calls = evidence, 0

    async def evidence(self, student, links):
        self.calls += 1
        return self.data


def run_generator(student, result, response, evidence, *, enabled=True, status=200):
    sent = []

    async def scenario():
        def handle(request):
            sent.append(json.loads(request.content))
            return httpx.Response(status, json=response)

        async with internal_client("http://ai.test", transport=httpx.MockTransport(handle)) as http:
            generator = NarrativeGenerator(
                Previous(result), AiClient(http), EvidenceReader(evidence)
            )
            return await generator.generate(
                replace(
                    command_for(student), narrative_enabled=enabled, display_name="합성학생비밀별명"
                ),
                None,
            )

    return asyncio.run(scenario()), sent


@pytest.mark.parametrize(
    "kind",
    ["valid", "number", "quote", "version", "hidden-quote", "level", "korean-number", "scientific"],
)
def test_verifier_rejects_unsupported_claims(kind):
    _, attempt, result, raw, evidence = fixture()
    if kind == "number":
        raw["narrative"]["text"] = "제출 시도는 999건입니다."
    elif kind in ("quote", "version"):
        raw["citedQuotes"] = [
            {
                "attemptId": str(attempt.id),
                "answerId": str(attempt.answers[0].id),
                "answerVersion": 2 if kind == "version" else 1,
                "quote": attempt.answers[0].text if kind == "version" else "만든 적 없는 인용",
            }
        ]
    elif kind == "hidden-quote":
        raw["eveningQuestion"] = '"만든 적 없는 인용"을 쓴 이유가 뭐니?'
    elif kind == "level":
        raw["narrative"]["text"] = "사고력 향상이 확인되었습니다."
    elif kind == "korean-number":
        raw["narrative"]["text"] = "열 번 했습니다."
    elif kind == "scientific":
        raw["narrative"]["text"] = "제출 시도는 1e1건입니다."
    checked = ReportVerifier().verify(NarrativeResponse.model_validate(raw), result, evidence)
    assert checked.passed is (kind == "valid")


def test_valid_narrative_versions_and_verified_candidates():
    student, _, result, raw, evidence = fixture()
    generated, sent = run_generator(student, result, raw, evidence)
    assert generated.narrative["source"] == "LLM"
    assert generated.versions == {"prompt": "synthetic-report@1", "model": "synthetic-model@1"}
    assert generated.verification == {
        "numbersMatched": True,
        "quotesMatched": True,
        "contentAllowed": True,
    }
    assert all(i.verified for i in generated.items if i.type == ItemType.QUOTE)
    assert len(sent) == 1
    assert [q["answerVersion"] for q in sent[0]["quotes"]] == [1]


@pytest.mark.parametrize("fault", ["number", "quote"])
def test_mismatch_uses_code_template_only(fault):
    student, attempt, result, raw, evidence = fixture()
    if fault == "number":
        raw["narrative"]["text"] = "999건 했습니다."
    else:
        raw["citedQuotes"] = [
            {
                "attemptId": str(attempt.id),
                "answerId": str(attempt.answers[0].id),
                "answerVersion": 1,
                "quote": "없는 문장",
            }
        ]
    generated, _ = run_generator(student, result, raw, evidence)
    assert generated.narrative["source"] == "TEMPLATE" and "1건" in generated.narrative["text"]
    assert generated.evening_question is None
    assert not generated.verification["numbersMatched" if fault == "number" else "quotesMatched"]


@pytest.mark.parametrize(
    "enabled,state", [(False, ReportState.INSUFFICIENT_SAMPLE), (True, ReportState.NO_RECORD)]
)
def test_free_and_no_record_skip_ai_and_evidence(enabled, state):
    student, _, result, raw, _ = fixture()
    result = replace(result, state=state)
    generated, sent = run_generator(student, result, raw, (), enabled=enabled)
    assert sent == [] and generated.narrative is None and generated.evening_question is None


@pytest.mark.parametrize("status", [500, 503])
def test_ai_api_error_propagates_without_template(status):
    student, _, result, raw, evidence = fixture()
    with pytest.raises(httpx.HTTPStatusError):
        run_generator(student, result, raw, evidence, status=status)


def test_known_nickname_and_identity_fields_are_not_sent():
    student, _, result, raw, evidence = fixture()
    modified = tuple(
        replace(
            i,
            payload={
                **i.payload,
                "summary": "합성학생비밀별명 이야기",
                "nickname": "합성학생비밀별명",
            },
        )
        for i in result.items
    )
    _, sent = run_generator(student, replace(result, items=modified), raw, evidence)
    body = json.dumps(sent, ensure_ascii=False)
    assert "합성학생비밀별명" not in body and '"nickname"' not in body


def test_deleted_evidence_removes_candidate_text():
    student, _, result, raw, evidence = fixture()
    generated, _ = run_generator(
        student, result, raw, (replace(evidence[0], available=False, text=None),)
    )
    [quote] = [i for i in generated.items if i.type == ItemType.QUOTE]
    assert quote.payload["text"] is None and not quote.verified


@pytest.mark.parametrize("case", ["valid", "gone", "version", "missing"])
def test_learning_evidence_lookup_checks_identity_and_deleted_records(case):
    from app.clients.learning_client import LearningClient
    from app.generation.models import EvidenceLink
    from app.generation.records import RecordContractError
    from app.security import UserContext, bind_user_context, reset_user_context

    student, attempt, _, _, _ = fixture()
    answer = attempt.answers[0]
    link = EvidenceLink(attempt.id, answer.id, 1)

    async def scenario():
        def handler(request):
            assert request.url.path == "/internal/records/evidence"
            assert request.url.params["answerIds"] == str(answer.id)
            if case == "gone":
                return httpx.Response(410)
            data = {
                "items": []
                if case == "missing"
                else [
                    {
                        "answerId": str(answer.id),
                        "attemptId": str(attempt.id),
                        "answerVersion": 2 if case == "version" else 1,
                        "quote": answer.text,
                        "available": True,
                    }
                ]
            }
            return httpx.Response(200, json=data)

        reset = bind_user_context(UserContext(None, "SYSTEM", frozenset({str(student)})))
        try:
            async with internal_client(
                "http://learning.test", transport=httpx.MockTransport(handler)
            ) as http:
                return await LearningClient(http).evidence(student, (link,))
        finally:
            reset_user_context(reset)

    if case in ("version", "missing"):
        with pytest.raises(RecordContractError):
            asyncio.run(scenario())
    else:
        [result] = asyncio.run(scenario())
        assert result.available is (case == "valid")
        assert result.text == (answer.text if case == "valid" else None)


@pytest.mark.parametrize(
    "api_status,expected", [(200, "COMPLETED"), (503, "FAILED"), ("timeout", "FAILED")]
)
def test_pipeline_persists_narrative_or_api_failure(
    report_factory, db_engine, report_student_id, api_status, expected
):
    from sqlalchemy import select

    from app.generation.consumer import GenerationConsumer
    from app.generation.locking import JobLocks
    from app.generation.repository import weekly_report
    from app.generation.service import GenerationService
    from app.messaging.envelope import EventEnvelope
    from tests.report_helpers import FakeCodec

    attempt = attempt_for(report_student_id)
    result = MetricsCalculator().calculate(records_for(report_student_id, [attempt]))
    _, _, _, response, _ = fixture()
    evidence = (
        EvidenceRecord(attempt.answers[0].id, attempt.id, 1, attempt.answers[0].text, True),
    )
    command = replace(
        command_for(report_student_id), narrative_enabled=True, display_name="합성별명"
    )

    async def scenario():
        def handle(request):
            if api_status == "timeout":
                raise httpx.ReadTimeout("Synthetic API timeout", request=request)
            return httpx.Response(api_status, json=response)

        async with internal_client(
            "http://ai.test",
            transport=httpx.MockTransport(handle),
        ) as http:
            generator = NarrativeGenerator(
                Previous(result), AiClient(http), EvidenceReader(evidence)
            )
            service = GenerationService(
                report_factory, JobLocks(db_engine), generator, FakeCodec(command)
            )
            await GenerationConsumer(service, FakeCodec(command))(
                EventEnvelope(
                    type="report.generate",
                    source="core-service",
                    subject=str(report_student_id),
                    dataschema="report.generate.v1",
                    data={},
                )
            )

    asyncio.run(scenario())
    with report_factory() as session:
        row = session.execute(select(weekly_report)).mappings().one()
    assert row["status"] == expected
    if api_status == 200:
        assert row["narrative"]["source"] == "LLM"
        assert row["versions"] == response["versions"]
    else:
        assert row["narrative"] is None and row["failure_reason"] == "GENERATION_FAILED"
