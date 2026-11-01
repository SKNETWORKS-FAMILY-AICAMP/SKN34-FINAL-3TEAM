from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.clients.ai_client import NarrativeResponse
from app.generation.models import GenerationResult, ItemType, ReportItem, ReportState
from app.generation.presentation import assemble, without_ai
from app.generation.records import EvidenceRecord
from app.generation.verifier import ReportVerifier, allowed_numbers
from app.query.schemas import Change, ReportDetail
from tests.render_helpers import fixed_detail


def test_assembly_isolated_payloads_masks_unverified_quotes_and_preserves_order():
    payloads = [
        (ItemType.REFLECTION, "reflection-1", {"difficulty": "NORMAL", "nested": ["original"]}),
        (ItemType.QUOTE, "quote-1", {"text": "PRIVATE-UNVERIFIED", "verified": False}),
        (ItemType.QUOTE, "quote-2", {"text": "검증된 인용", "verified": True}),
        (ItemType.CHANGE, None, {"followup": None}),
    ]
    original = deepcopy(payloads)
    view = assemble({"childId": "synthetic"}, payloads)
    assert view["reflections"][0]["difficulty"] == "보통"
    assert [x["itemId"] for x in view["quotes"]] == ["quote-1", "quote-2"]
    assert [x["text"] for x in view["quotes"]] == [None, "검증된 인용"]
    assert view["changes"] == [{"followup": None}]
    view["reflections"][0]["nested"].append("mutation")
    assert payloads == original
    with pytest.raises(ValueError, match="Unknown"):
        assemble({}, [("UNKNOWN", None, {})])


def test_free_view_removes_only_ai_content_without_mutating_paid_view():
    paid = fixed_detail()
    paid["thinkingTypes"][0]["summary"] = "유료 서술"
    original = deepcopy(paid)
    free = without_ai(paid)
    assert free["narrative"] is None and free["eveningQuestion"] is None
    assert all("summary" not in x for x in free["thinkingTypes"])
    assert paid == original
    assert free["metrics"] == paid["metrics"] and free["quotes"] == paid["quotes"]
    free["metrics"][0]["count"] = 999
    assert paid == original


def numbers_result():
    return GenerationResult(
        ReportState.OK,
        items=(
            ReportItem(
                ItemType.METRIC,
                1,
                {
                    "count": 1000,
                    "numerator": 1,
                    "denominator": 8,
                    "value": 0.125,
                },
                ReportState.OK,
                True,
            ),
            ReportItem(ItemType.CHANGE, 2, {"counts": {"chars": [20, 35]}}, ReportState.OK, True),
        ),
    )


def response(text, citations=None):
    return NarrativeResponse.model_validate(
        {
            "narrative": {"text": text, "source": "LLM"},
            "eveningQuestion": "어떤 생각이 기억에 남니?",
            "citedQuotes": citations or [],
            "versions": {"prompt": "test@1", "model": "test@1"},
        }
    )


@pytest.mark.parametrize(
    "text,matched",
    [
        ("1,000건, 12.50%, 20글자에서 35글자", True),
        ("0.13과 13%", True),
        ("12.51%", False),
        ("１０００건", False),
        ("①건", False),
        ("1e3건", False),
    ],
)
def test_numeric_rounding_percentage_change_and_unsupported_unicode(text, matched):
    result = numbers_result()
    assert {Decimal("0.125"), Decimal("0.13"), Decimal("12.50"), Decimal("13")} <= allowed_numbers(
        result
    )
    checked = ReportVerifier().verify(response(text), result, ())
    assert checked.numbers_matched is matched
    assert checked.quotes_matched and checked.content_allowed
    assert checked.payload()["numbersMatched"] is matched


@pytest.mark.parametrize(
    "fault", [None, "unavailable", "missing-text", "wrong-attempt", "missing-id"]
)
def test_citation_identity_availability_and_numeric_source_text(fault):
    attempt_id, answer_id = uuid4(), uuid4()
    source = EvidenceRecord(answer_id, attempt_id, 2, "나는 999개의 별을 보았다고 썼다.", True)
    citation = {
        "answerId": str(answer_id),
        "attemptId": str(attempt_id),
        "answerVersion": 2,
        "quote": source.text,
    }
    if fault == "unavailable":
        source = replace(source, available=False)
    elif fault == "missing-text":
        source = replace(source, text=None)
    elif fault == "wrong-attempt":
        citation["attemptId"] = str(uuid4())
    elif fault == "missing-id":
        citation["answerId"] = str(uuid4())
    checked = ReportVerifier().verify(
        response('"나는 999개의 별을 보았다고 썼다."', [citation]), numbers_result(), (source,)
    )
    assert checked.quotes_matched is (fault is None)
    assert checked.numbers_matched  # 원문 인용의 숫자를 report 집계 수치로 오판하지 않는다.
    assert checked.passed is (fault is None)


def test_query_schema_round_trip_and_nullable_followup_does_not_become_missing():
    detail = fixed_detail()
    parsed = ReportDetail.model_validate(detail).model_dump(mode="json", by_alias=True)
    assert parsed["period"] == detail["period"]
    assert parsed["reflections"][0]["difficulty"] == "보통"
    change = detail["changes"][0]
    change["followup"] = None
    assert Change.model_validate(change).followup is None
    del change["followup"]
    with pytest.raises(ValidationError):
        Change.model_validate(change)
