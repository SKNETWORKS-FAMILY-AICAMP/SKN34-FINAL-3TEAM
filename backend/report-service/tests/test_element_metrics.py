"""#344 FN-RPT-05 thinking-element metrics from stored judgments (synthetic records only)."""

from dataclasses import replace
from uuid import uuid4

import pytest

from app.generation.metrics import MetricsCalculator
from app.generation.models import ItemType, ReportState
from app.generation.records import (
    AnswerRecord,
    AttemptRecord,
    JudgedElement,
    JudgmentRecord,
    ThinkingType,
)
from app.generation.verifier import allowed_numbers
from tests.record_helpers import PERIOD, instant, records_for

BASE_METRICS = ["답변 제출 시도 수", "완료한 시도 수", "도움 없이 시작한 비율"]


def element(code, satisfied, *, good=False, element_id=None):
    return JudgedElement(element_id or uuid4(), code, good, satisfied)


def judged(*elements, result="PARTIAL", trial=True):
    return JudgmentRecord(result, trial, tuple(elements))


def answer(version, judgment, *, status="DONE", input_type="NARRATIVE", minute=0, day=20):
    # PERIOD is 2026-10-19 ~ 2026-10-25 (KST); day=18 is the previous week.
    return AnswerRecord(
        uuid4(),
        version,
        instant(f"2026-10-{day:02d}T10:{minute:02d}:00+09:00"),
        "합성 답변",
        status,
        "합성 답변",
        input_type,
        judgment,
    )


def attempt(student, *answers, thinking=ThinkingType.ANALYZE):
    return AttemptRecord(
        id=uuid4(),
        student_id=student,
        mission_title="합성 미션",
        thinking_type=thinking,
        status="IN_PROGRESS",
        answers=tuple(answers),
        hint_opened_at=(),
    )


def metrics(student, attempts):
    result = MetricsCalculator().calculate(records_for(student, attempts))
    return {i.payload["label"]: i for i in result.items if i.type == ItemType.METRIC}


def analyze_attempt(student, met=2, *, trial=True):
    codes = ["e1", "ANALYZE_RELATION", "ANALYZE_REASON"]
    elements = [element(code, i < met) for i, code in enumerate(codes)]
    return attempt(
        student, answer(1, judged(*elements, element("e2", True, good=True), trial=trial))
    )


def test_no_judgment_keeps_only_record_metrics():
    student = uuid4()
    pending = attempt(student, answer(1, None, status="PENDING"))
    failed_then_pending = attempt(
        student, answer(1, None, status="FAILED"), answer(2, None, status="RUNNING", minute=1)
    )
    assert list(metrics(student, [pending, failed_then_pending])) == BASE_METRICS


def test_first_answer_rate_counts_required_elements_only():
    student = uuid4()
    found = metrics(student, [analyze_attempt(student) for _ in range(5)])
    item = found["처음 답에서 확인된 생각 요소"]
    payload = item.payload
    # good-thought element (e2) is never in the denominator (FN-RPT-05)
    assert (payload["numerator"], payload["denominator"], payload["count"]) == (10, 15, 10)
    assert payload["value"] == pytest.approx(10 / 15)
    assert payload["state"] == ReportState.OK and item.state == ReportState.OK
    assert payload["sourceType"] == "AI_OBSERVATION"
    assert payload["formula"].endswith("(시범 판정 포함)")
    assert payload["period"] == PERIOD.payload()
    assert found["분석하기 · 처음 답에서 확인된 생각 요소"].payload["denominator"] == 15
    assert len(item.evidence) == 5
    assert list(found)[:3] == BASE_METRICS


def test_below_five_attempts_shows_counts_only():
    student = uuid4()
    payload = metrics(student, [analyze_attempt(student) for _ in range(4)])[
        "처음 답에서 확인된 생각 요소"
    ].payload
    assert payload["state"] == ReportState.INSUFFICIENT_SAMPLE
    assert payload["value"] is None and payload["count"] == 8


def test_non_trial_judgments_have_no_trial_note():
    student = uuid4()
    payload = metrics(student, [analyze_attempt(student, trial=False)])[
        "처음 답에서 확인된 생각 요소"
    ].payload
    assert "시범" not in payload["formula"]


def test_held_answer_codes_and_choice_missions_are_excluded():
    student = uuid4()
    held = attempt(student, answer(1, judged(element("e1", True), result="HELD")))
    choice = attempt(student, answer(1, judged(element("ANSWER_KEY", True), result="CORRECT")))
    solve = attempt(
        student,
        answer(
            1,
            judged(
                element("SOLVE_DEFINE", True),
                element("SOLVE_PLAN", False),
                element("FINAL_ANSWER", True),
            ),
        ),
        thinking=ThinkingType.SOLVE,
    )
    found = metrics(student, [held, choice, solve])
    payload = found["처음 답에서 확인된 생각 요소"].payload
    assert (payload["numerator"], payload["denominator"]) == (1, 2)
    assert "분석하기 · 처음 답에서 확인된 생각 요소" not in found
    assert found["문제 해결하기 · 처음 답에서 확인된 생각 요소"].payload["denominator"] == 2


def test_corrected_judgments_are_not_counted_like_held():
    student = uuid4()
    kept = attempt(student, answer(1, judged(element("ANALYZE_REASON", True))))
    corrected = attempt(
        student, answer(1, replace(judged(element("ANALYZE_REASON", True)), corrected=True))
    )
    values = metrics(student, [kept, corrected])
    rate = next(i for label, i in values.items() if label not in BASE_METRICS)
    assert (rate.payload["numerator"], rate.payload["denominator"]) == (1, 1)
    assert len(rate.evidence) == 1


def test_only_choice_missions_add_no_element_metrics():
    student = uuid4()
    choice = attempt(student, answer(1, judged(element("ANSWER_KEY", False), result="RETHINK")))
    assert list(metrics(student, [choice])) == BASE_METRICS


def test_revision_counts_missing_elements_found_in_any_later_answer():
    student = uuid4()
    claim, evidence, other = uuid4(), uuid4(), uuid4()
    first = answer(
        1,
        judged(
            element("EVALUATE_CLAIM", True, element_id=claim),
            element("EVALUATE_EVIDENCE", False, element_id=evidence),
            element("EVALUATE_PERSPECTIVE", False, element_id=other),
        ),
    )
    # A revised answer is judged on its own text, so earlier elements may read false again.
    second = answer(
        2,
        judged(
            element("EVALUATE_CLAIM", False, element_id=claim),
            element("EVALUATE_EVIDENCE", True, element_id=evidence),
            element("EVALUATE_PERSPECTIVE", False, element_id=other),
        ),
        minute=1,
    )
    held = answer(
        3,
        judged(element("EVALUATE_PERSPECTIVE", True, element_id=other), result="HELD"),
        minute=2,
    )
    found = metrics(
        student, [attempt(student, first, second, held, thinking=ThinkingType.EVALUATE)]
    )
    payload = found["되묻기 후 새로 확인된 생각 요소"].payload
    assert (payload["numerator"], payload["denominator"]) == (1, 2)
    assert len(found["되묻기 후 새로 확인된 생각 요소"].evidence) == 2


def test_revision_needs_a_usable_first_answer_and_missing_elements():
    student = uuid4()
    held_first = attempt(
        student,
        answer(1, judged(element("e1", False), result="HELD")),
        answer(2, judged(element("e1", True)), minute=1),
    )
    all_met = attempt(
        student,
        answer(1, judged(element("e1", True))),
        answer(2, judged(element("e1", True)), minute=1),
    )
    assert "되묻기 후 새로 확인된 생각 요소" not in metrics(student, [held_first, all_met])


def test_argument_rate_uses_evaluate_essays_with_all_three_codes():
    student = uuid4()

    def essay(perspective, *, input_type="ESSAY", codes=None):
        elements = [element("EVALUATE_CLAIM", True), element("EVALUATE_EVIDENCE", True)]
        elements.append(element("EVALUATE_PERSPECTIVE", perspective))
        if codes is not None:
            elements = [element(code, True) for code in codes]
        return attempt(
            student,
            answer(1, judged(*elements), input_type=input_type),
            thinking=ThinkingType.EVALUATE,
        )

    found = metrics(
        student,
        [
            essay(True),
            essay(False),
            essay(True, input_type="NARRATIVE"),
            essay(True, codes=["EVALUATE_CLAIM", "EVALUATE_EVIDENCE"]),
        ],
    )
    payload = found["따져 보기 논술 · 주장·근거·반론을 모두 쓴 처음 답"].payload
    assert (payload["numerator"], payload["denominator"]) == (1, 2)


def test_good_thoughts_may_appear_in_any_judged_answer():
    student = uuid4()
    optional = uuid4()
    first = answer(
        1, judged(element("e1", True), element("e2", False, good=True, element_id=optional))
    )
    second = answer(
        2,
        judged(element("e1", True), element("e2", True, good=True, element_id=optional)),
        minute=1,
    )
    other = attempt(
        student, answer(1, judged(element("e1", True), element("e3", False, good=True)))
    )
    payload = metrics(student, [attempt(student, first, second), other])[
        "들어가면 좋은 생각"
    ].payload
    assert (payload["numerator"], payload["denominator"]) == (1, 2)


def test_standard_element_appearance_counts_attempts_per_code():
    student = uuid4()
    with_evidence = [
        attempt(
            student,
            answer(1, judged(element("EVALUATE_EVIDENCE", met), element("e1", True))),
            thinking=ThinkingType.EVALUATE,
        )
        for met in (True, False, True)
    ]
    found = metrics(student, with_evidence)
    payload = found["생각 요소 · 근거"].payload
    assert (payload["numerator"], payload["denominator"]) == (2, 3)
    assert not any(label.startswith("생각 요소 · e") for label in found)
    assert "생각 요소 · 주장" not in found


def test_element_metric_numbers_are_allowed_in_narrative():
    student = uuid4()
    result = MetricsCalculator().calculate(
        records_for(student, [analyze_attempt(student) for _ in range(5)])
    )
    numbers = {str(n) for n in allowed_numbers(result)}
    assert {"10", "15", "66.67"} <= numbers


def test_pending_first_answer_still_counts_later_good_thoughts_only():
    student = uuid4()
    pending_first = replace(answer(1, None, status="PENDING"))
    later = answer(2, judged(element("e1", True), element("e2", True, good=True)), minute=1)
    found = metrics(student, [attempt(student, pending_first, later)])
    assert "처음 답에서 확인된 생각 요소" not in found
    assert found["들어가면 좋은 생각"].payload["numerator"] == 1


def test_first_answer_from_previous_week_is_not_counted_again():
    student = uuid4()
    reason = uuid4()
    previous_first = answer(
        1,
        judged(
            element("ANALYZE_RELATION", True), element("ANALYZE_REASON", False, element_id=reason)
        ),
        day=18,
    )
    revised_now = answer(
        2,
        judged(
            element("ANALYZE_RELATION", False), element("ANALYZE_REASON", True, element_id=reason)
        ),
        day=20,
    )
    found = metrics(student, [attempt(student, previous_first, revised_now)])
    # The first answer belongs to last week's report; only this week's revision counts here.
    assert "처음 답에서 확인된 생각 요소" not in found
    assert "생각 요소 · 원인·특징·관계" not in found
    payload = found["되묻기 후 새로 확인된 생각 요소"].payload
    assert (payload["numerator"], payload["denominator"]) == (1, 1)
    assert "기간 안" in payload["formula"]


def test_elements_filled_before_the_period_are_not_new_again():
    student = uuid4()
    claim, evidence = uuid4(), uuid4()
    first = answer(
        1,
        judged(
            element("EVALUATE_CLAIM", False, element_id=claim),
            element("EVALUATE_EVIDENCE", False, element_id=evidence),
        ),
        day=17,
    )
    filled_last_week = answer(
        2, judged(element("EVALUATE_CLAIM", True, element_id=claim)), day=18, minute=1
    )
    now = answer(
        3,
        judged(
            element("EVALUATE_CLAIM", True, element_id=claim),
            element("EVALUATE_EVIDENCE", True, element_id=evidence),
        ),
        day=21,
    )
    found = metrics(
        student, [attempt(student, first, filled_last_week, now, thinking=ThinkingType.EVALUATE)]
    )
    payload = found["되묻기 후 새로 확인된 생각 요소"].payload
    assert (payload["numerator"], payload["denominator"]) == (1, 1)


def test_good_thought_shown_last_week_is_not_counted_this_week():
    student = uuid4()
    optional = uuid4()
    last_week = answer(
        1,
        judged(element("e1", True), element("e2", True, good=True, element_id=optional)),
        day=18,
    )
    this_week = answer(
        2,
        judged(element("e1", True), element("e2", True, good=True, element_id=optional)),
        day=20,
    )
    assert "들어가면 좋은 생각" not in metrics(student, [attempt(student, last_week, this_week)])
