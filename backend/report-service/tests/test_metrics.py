from dataclasses import replace
from datetime import datetime
from uuid import uuid4

import pytest

from app.generation.metrics import REASON_CONNECTIVES, MetricsCalculator, text_counts
from app.generation.models import ItemType, ReportState
from app.generation.records import RecordContractError, ReflectionRecord, ThinkingType
from tests.record_helpers import PERIOD, attempt_for, instant, records_for


def items(result, kind):
    return [i for i in result.items if i.type == kind]


@pytest.mark.parametrize(
    "count,state",
    [
        (0, "NO_RECORD"),
        (1, "INSUFFICIENT_SAMPLE"),
        (4, "INSUFFICIENT_SAMPLE"),
        (5, "OK"),
        (6, "OK"),
    ],
)
def test_sample_boundary_and_ratio(count, state):
    student = uuid4()
    result = MetricsCalculator().calculate(
        records_for(student, [attempt_for(student) for _ in range(count)])
    )
    assert result.state == state
    metric = items(result, ItemType.METRIC)[-1].payload
    assert metric["value"] == (1.0 if count >= 5 else None)
    assert metric["count"] == metric["numerator"] == metric["denominator"] == count
    assert metric["period"] == PERIOD.payload()
    assert metric["sourceType"] == "RECORD" and metric["formula"]


def test_help_is_compared_to_first_submission_not_any_help():
    student = uuid4()
    attempts = [attempt_for(student) for _ in range(5)]
    attempts[0] = replace(attempts[0], hint_opened_at=(instant("2026-10-20T09:59:59+09:00"),))
    attempts[1] = replace(attempts[1], hint_opened_at=(instant(),))  # equal is not before
    attempts[2] = replace(attempts[2], hint_opened_at=(instant("2026-10-20T10:00:01+09:00"),))
    result = MetricsCalculator().calculate(records_for(student, attempts))
    metric = items(result, ItemType.METRIC)[-1].payload
    assert metric["numerator"] == metric["count"] == 4
    assert metric["denominator"] == 5 and metric["value"] == 0.8


def test_failed_only_and_no_submission_are_excluded_but_pending_included():
    student = uuid4()
    failed, pending = attempt_for(student), attempt_for(student)
    failed = replace(failed, answers=(replace(failed.answers[0], process_status="FAILED"),))
    pending = replace(pending, answers=(replace(pending.answers[0], process_status="PENDING"),))
    result = MetricsCalculator().calculate(
        records_for(student, [failed, pending, attempt_for(student, texts=())])
    )
    metric = items(result, ItemType.METRIC)[0].payload
    assert metric["count"] == 1 and result.state == ReportState.INSUFFICIENT_SAMPLE


@pytest.mark.parametrize(
    "text,chars,sentences,connectives",
    [
        ("", 0, 0, 0),
        (" \r\n .?! ", 8, 0, 0),
        ("가 나.왜?그래!\r\n마지막", 14, 4, 0),
        ("가🙂", 2, 1, 0),
        ("가\r나", 3, 1, 0),  # learning's delimiters are . ? ! and LF (not lone CR).
        ("왜냐하면 왜냐하면 때문에 그래서 따라서", 21, 1, 5),
    ],
)
def test_text_rules_are_literal_and_include_spaces(text, chars, sentences, connectives):
    assert text_counts(text) == {
        "chars": chars,
        "sentences": sentences,
        "reasonConnectives": connectives,
    }
    assert REASON_CONNECTIVES == ("왜냐하면", "때문", "그래서", "따라서")


def test_kst_boundaries_and_first_latest_ignore_future_answers():
    student = uuid4()
    attempt = attempt_for(
        student,
        texts=("이전 주 첫 답변", "이번 주 답변", "미래 답변"),
        times=(
            "2026-10-18T14:59:59+00:00",
            "2026-10-25T14:59:59.999999+00:00",
            "2026-10-25T15:00:00+00:00",
        ),
    )
    attempt = replace(attempt, hint_opened_at=(instant("2026-10-18T14:59:58+00:00"),))
    result = MetricsCalculator().calculate(records_for(student, [attempt]))
    change = items(result, ItemType.CHANGE)[0].payload
    assert change["first"]["text"] == "이전 주 첫 답변"
    assert change["revised"]["text"] == "이번 주 답변"
    assert items(result, ItemType.METRIC)[-1].payload["numerator"] == 0
    assert all(
        link.answer_id != attempt.answers[2].id for item in result.items for link in item.evidence
    )


@pytest.mark.parametrize(
    "submitted,expected",
    [
        ("2026-10-18T14:59:59.999999+00:00", 0),
        ("2026-10-18T15:00:00+00:00", 1),
        ("2026-10-25T14:59:59.999999+00:00", 1),
        ("2026-10-25T15:00:00+00:00", 0),
    ],
)
def test_period_uses_kst_half_open_timestamp_boundary(submitted, expected):
    student = uuid4()
    attempt = attempt_for(student, times=(submitted,))
    result = MetricsCalculator().calculate(records_for(student, [attempt]))
    assert items(result, ItemType.METRIC)[0].payload["count"] == expected


def test_completed_count_uses_as_of_end_and_reflections_are_not_invented():
    student = uuid4()
    done = attempt_for(student, status="COMPLETED")
    future_done = replace(
        attempt_for(student, status="COMPLETED"), completed_at=instant("2026-10-26T01:00:00+09:00")
    )
    done = replace(done, reflection=ReflectionRecord("NORMAL", "", instant()))
    future_done = replace(
        future_done,
        reflection=ReflectionRecord(
            "NORMAL", "미래 돌아보기", instant("2026-10-26T01:00:00+09:00")
        ),
    )
    result = MetricsCalculator().calculate(records_for(student, [done, future_done]))
    assert items(result, ItemType.METRIC)[1].payload["count"] == 1
    reflections = {i.payload["attemptId"]: i.payload for i in items(result, ItemType.REFLECTION)}
    assert reflections[str(done.id)]["written"] is True
    assert reflections[str(done.id)]["text"] == ""
    assert reflections[str(future_done.id)] == {
        "attemptId": str(future_done.id),
        "written": False,
        "difficulty": None,
        "text": None,
    }


def test_all_five_thinking_types_and_unverified_quote_candidates():
    student = uuid4()
    attempt = replace(attempt_for(student), thinking_type=ThinkingType.SOLVE)
    result = MetricsCalculator().calculate(records_for(student, [attempt]))
    groups = items(result, ItemType.THINKING_TYPE)
    assert {i.payload["type"] for i in groups} == set(ThinkingType)
    assert sum(i.state == ReportState.NO_RECORD for i in groups) == 4
    [quote] = items(result, ItemType.QUOTE)
    assert quote.payload["text"] == attempt.answers[0].text
    assert quote.verified is False and quote.payload["verified"] is False
    assert quote.evidence[0].answer_version == 1


@pytest.mark.parametrize(
    "fault", ["student", "attempt_id", "answer_id", "version", "thinking", "change"]
)
def test_inconsistent_source_is_an_error_instead_of_empty_data(fault):
    student = uuid4()
    attempt = attempt_for(student, texts=("첫 답변", "보완 답변"))
    records = records_for(student, [attempt])
    if fault == "student":
        records = replace(records, student_id=uuid4())
    elif fault == "attempt_id":
        records = replace(records, attempts=(attempt, attempt))
    elif fault == "answer_id":
        bad = replace(
            attempt,
            answers=(attempt.answers[0], replace(attempt.answers[1], id=attempt.answers[0].id)),
        )
        records = replace(records, attempts=(bad,))
    elif fault == "version":
        records = replace(records, attempts=(replace(attempt, answers=(attempt.answers[1],)),))
    elif fault == "thinking":
        records = replace(records, thinking_missions=())
    elif fault == "change":
        records = replace(records, changes=(replace(records.changes[0], revised_text="바뀐 원문"),))
    with pytest.raises(RecordContractError):
        MetricsCalculator().calculate(records)


def test_naive_timestamp_is_rejected():
    student = uuid4()
    attempt = attempt_for(student)
    bad = replace(
        attempt, answers=(replace(attempt.answers[0], submitted_at=datetime(2026, 10, 20)),)
    )
    with pytest.raises(ValueError, match="offset"):
        MetricsCalculator().calculate(records_for(student, [bad]))


def test_non_text_answers_do_not_create_text_or_fake_changes():
    student = uuid4()
    attempt = attempt_for(student, texts=(None, None))
    result = MetricsCalculator().calculate(records_for(student, [attempt]))
    assert not items(result, ItemType.CHANGE) and not items(result, ItemType.QUOTE)
