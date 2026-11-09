"""P08 calculations from submitted records only. No inferred text, AI calls or scores.

Thinking-element metrics (FN-RPT-05, #344) count judgment results already stored by learning.
"""

import re
from collections import Counter
from dataclasses import dataclass, field, replace

from app.generation.models import (
    EvidenceLink,
    GenerationResult,
    ItemType,
    ReportItem,
    ReportState,
)
from app.generation.records import (
    AnswerRecord,
    AttemptRecord,
    JudgedElement,
    JudgmentRecord,
    LearningRecords,
    Period,
    RecordContractError,
    ThinkingType,
)

# #51 owner confirmed this server list on 2026-10-27; kept in one place.
REASON_CONNECTIVES = ("왜냐하면", "때문", "그래서", "따라서")
INCLUSION_RULE = (
    "기간 내 답변 제출이 있는 시도(미완료 포함), 처리 실패만 있는 시도·삭제 기록 제외. "
    "최초 답변과 조회 종료일 이전 마지막 답변을 비교하며, 도움은 최초 답변 전 열람 기준."
)


def sample_state(count: int) -> ReportState:
    if count == 0:
        return ReportState.NO_RECORD
    return ReportState.INSUFFICIENT_SAMPLE if count < 5 else ReportState.OK


def text_counts(text: str) -> dict[str, int]:
    return {
        "chars": len(text),
        "sentences": sum(bool(part.strip()) for part in re.split(r"[.?!\n]+", text)),
        "reasonConnectives": sum(text.count(word) for word in REASON_CONNECTIVES),
    }


def _link(attempt: AttemptRecord, answer: AnswerRecord) -> EvidenceLink:
    return EvidenceLink(attempt.id, answer.id, answer.version)


# FN 1.5: answer elements are counted as correctness, not as thinking elements.
ANSWER_CODES = frozenset({"ANSWER_KEY", "FINAL_ANSWER"})
# FN 1.5 standard element codes and names (#262), in the spec's order.
STANDARD_ELEMENTS = {
    "ANALYZE_RELATION": "원인·특징·관계",
    "ANALYZE_REASON": "까닭 잇기",
    "EVALUATE_CLAIM": "주장",
    "EVALUATE_EVIDENCE": "근거",
    "EVALUATE_PERSPECTIVE": "다른 관점·반론",
    "CREATE_NEW": "새로운 생각",
    "CREATE_WHY": "왜 나은지",
    "CREATE_CONNECT": "연결·변형",
    "SOLVE_DEFINE": "문제 정하기",
    "SOLVE_PLAN": "방법 세우기",
    "SOLVE_CHECK": "결과 확인",
    "REFLECT_CHANGE": "바뀐 생각",
    "REFLECT_REASON": "바뀐 까닭",
    "REFLECT_CONNECT": "생각 과정·경험과 연결",
}
ARGUMENT_CODES = ("EVALUATE_CLAIM", "EVALUATE_EVIDENCE", "EVALUATE_PERSPECTIVE")
TYPE_LABELS = {
    ThinkingType.ANALYZE: "분석하기",
    ThinkingType.EVALUATE: "따져 보기",
    ThinkingType.CREATE: "새로 만들기",
    ThinkingType.SOLVE: "문제 해결하기",
    ThinkingType.REFLECT: "돌아보기",
}
TRIAL_NOTE = " (시범 판정 포함)"


def usable_judgment(answer: AnswerRecord) -> JudgmentRecord | None:
    """Pending/running/failed answers carry no judgment; HELD results are not counted (#344).
    A correction changes only the result, so its original elements are not counted either (#244)."""
    judgment = answer.judgment
    if (
        answer.process_status != "DONE"
        or judgment is None
        or judgment.result == "HELD"
        or judgment.corrected
    ):
        return None
    return judgment


def thinking_elements(judgment: JudgmentRecord) -> tuple[JudgedElement, ...]:
    return tuple(e for e in judgment.elements if e.code not in ANSWER_CODES)


@dataclass
class ElementTally:
    numerator: int = 0
    denominator: int = 0
    attempts: set = field(default_factory=set)
    trial: bool = False
    evidence: list[EvidenceLink] = field(default_factory=list)

    def add(self, attempt, numerator, denominator, judged) -> None:
        """judged: (answer, judgment) pairs this attempt contributed with."""
        self.numerator += numerator
        self.denominator += denominator
        self.attempts.add(attempt.id)
        self.trial = self.trial or any(judgment.trial for _, judgment in judged)
        self.evidence.extend(_link(attempt, answer) for answer, _ in judged)


def _satisfied(judged) -> set:
    return {e.element_id for _, j in judged for e in j.elements if e.satisfied}


def element_tallies(
    attempts: tuple[AttemptRecord, ...], period: Period
) -> list[tuple[str, str, ElementTally]]:
    """(label, formula, tally) for FN-RPT-05 metrics that have at least one contributing attempt.

    First answer = version 1 (P08). Revised answers = versions 2.. up to the period end.
    Each observation belongs to the week its answer was submitted, so an attempt that spans
    two weekly reports never counts the same first answer or newly shown element twice.
    """
    first_all = ElementTally()
    first_by_type = {t: ElementTally() for t in ThinkingType}
    revision, argument, good = ElementTally(), ElementTally(), ElementTally()
    standard = {code: ElementTally() for code in STANDARD_ELEMENTS}
    for attempt in attempts:
        first_answer = attempt.answers[0]
        first = usable_judgment(first_answer)
        first_in_period = period.includes(first_answer.submitted_at)
        later = [(a, j) for a in attempt.answers[1:] if (j := usable_judgment(a)) is not None]
        later_before = [(a, j) for a, j in later if not period.includes(a.submitted_at)]
        later_now = [(a, j) for a, j in later if period.includes(a.submitted_at)]
        judged = ([(first_answer, first)] if first is not None else []) + later
        judged_before = [(a, j) for a, j in judged if not period.includes(a.submitted_at)]
        judged_now = [(a, j) for a, j in judged if period.includes(a.submitted_at)]

        # Good thoughts are optional, so any judged answer may show them; each is credited to
        # the week it first appears.
        optional = {e.element_id for _, j in judged for e in thinking_elements(j) if e.good_thought}
        remaining = optional - _satisfied(judged_before)
        if remaining and judged_now:
            shown = _satisfied(judged_now) & remaining
            good.add(attempt, len(shown), len(remaining), judged_now)

        if first is None:
            continue
        elements = thinking_elements(first)
        required = [e for e in elements if not e.good_thought]
        if required and first_in_period:
            met = sum(e.satisfied for e in required)
            for tally in (first_all, first_by_type[attempt.thinking_type]):
                tally.add(attempt, met, len(required), [(first_answer, first)])
        # Missing elements already shown in a revision before this period were counted then.
        missing = {e.element_id for e in required if not e.satisfied} - _satisfied(later_before)
        if missing and later_now:
            found = _satisfied(later_now) & missing
            revision.add(attempt, len(found), len(missing), [(first_answer, first), *later_now])

        if not first_in_period:
            continue
        if attempt.thinking_type == ThinkingType.EVALUATE and first_answer.input_type == "ESSAY":
            codes = {e.code for e in elements}
            shown_codes = {e.code for e in elements if e.satisfied}
            if set(ARGUMENT_CODES) <= codes:
                complete = set(ARGUMENT_CODES) <= shown_codes
                argument.add(attempt, int(complete), 1, [(first_answer, first)])

        for code, tally in standard.items():
            present = [e for e in elements if e.code == code]
            if present:
                met = any(e.satisfied for e in present)
                tally.add(attempt, int(met), 1, [(first_answer, first)])

    rows = [
        (
            "처음 답에서 확인된 생각 요소",
            "기간 안에 낸 처음 답에서 확인된 필수 생각 요소 수 / 그 처음 답의 필수 생각 요소 수",
            first_all,
        ),
        *(
            (
                f"{TYPE_LABELS[t]} · 처음 답에서 확인된 생각 요소",
                f"{TYPE_LABELS[t]} 시도의 기간 안 처음 답에서 확인된 필수 생각 요소 수"
                " / 필수 생각 요소 수",
                first_by_type[t],
            )
            for t in ThinkingType
        ),
        (
            "되묻기 후 새로 확인된 생각 요소",
            "처음 답에서 빠졌다가 기간 안의 2번째 이후 답에서 확인된 필수 생각 요소 수"
            " / 처음 답에서 빠졌고 기간 전에 채우지 않은 필수 생각 요소 수",
            revision,
        ),
        (
            "따져 보기 논술 · 주장·근거·반론을 모두 쓴 처음 답",
            "기간 안 처음 답에 주장·근거·반론이 모두 확인된 따져 보기 논술 시도 수"
            " / 기간 안에 처음 답을 낸 따져 보기 논술 시도 수",
            argument,
        ),
        (
            "들어가면 좋은 생각",
            "기간 안의 답에서 처음 확인된 들어가면 좋은 생각 수"
            " / 기간 전에 확인되지 않은 들어가면 좋은 생각 요소 수",
            good,
        ),
        *(
            (
                f"생각 요소 · {name}",
                f"기간 안 처음 답에 '{name}' 요소가 확인된 시도 수"
                f" / '{name}' 요소가 있고 기간 안에 처음 답을 낸 시도 수",
                standard[code],
            )
            for code, name in STANDARD_ELEMENTS.items()
        ),
    ]
    return [row for row in rows if row[2].attempts]


def element_metric_payload(label: str, formula: str, tally: ElementTally, period: Period) -> dict:
    # P08: below five contributing attempts show counts only.
    state = sample_state(len(tally.attempts))
    return {
        "label": label,
        "count": tally.numerator,
        "numerator": tally.numerator,
        "denominator": tally.denominator,
        "formula": formula + (TRIAL_NOTE if tally.trial else ""),
        "value": tally.numerator / tally.denominator
        if state == ReportState.OK and tally.denominator
        else None,
        "period": period.payload(),
        # FN 1.5: only the LLM judges thinking elements, so these counts are AI observations.
        "sourceType": "AI_OBSERVATION",
        "state": state,
    }


class MetricsCalculator:
    def calculate(self, records: LearningRecords) -> GenerationResult:
        period = records.period
        attempts = self._eligible(records)
        self._check_thinking(records, attempts)
        pairs = {}
        for pair in records.changes:
            if pair.attempt_id in pairs:
                raise RecordContractError("Duplicate change pair for one attempt")
            pairs[pair.attempt_id] = pair

        items, sequences = [], Counter()

        def append(kind, payload, state, evidence=(), *, verified=False):
            items.append(
                ReportItem(
                    kind, sequences[kind], payload, state, verified, tuple(dict.fromkeys(evidence))
                )
            )
            sequences[kind] += 1

        total = len(attempts)
        state = sample_state(total)
        all_links = tuple(
            _link(a, next(v for v in a.answers if period.includes(v.submitted_at)))
            for a in attempts
        )
        completed = sum(
            a.status == "COMPLETED"
            and a.completed_at is not None
            and period.at_or_before_end(a.completed_at)
            for a in attempts
        )
        unassisted = [
            a for a in attempts if not any(t < a.answers[0].submitted_at for t in a.hint_opened_at)
        ]

        for label, numerator, formula, ratio, evidence in (
            ("답변 제출 시도 수", total, "집계 대상 시도 수", False, all_links),
            (
                "완료한 시도 수",
                completed,
                "조회 종료일까지 완료한 집계 대상 시도 수",
                False,
                tuple(
                    _link(a, a.answers[-1])
                    for a in attempts
                    if a.status == "COMPLETED"
                    and a.completed_at is not None
                    and period.at_or_before_end(a.completed_at)
                ),
            ),
            (
                "도움 없이 시작한 비율",
                len(unassisted),
                "최초 답변 전 도움 열람 없는 시도 수 / 집계 대상 시도 수",
                True,
                tuple(_link(a, a.answers[0]) for a in attempts),
            ),
        ):
            append(
                ItemType.METRIC,
                {
                    "label": label,
                    "count": numerator,
                    "numerator": numerator,
                    "denominator": total,
                    "formula": formula,
                    "value": numerator / total if ratio and total >= 5 else None,
                    "period": period.payload(),
                    "sourceType": "RECORD",
                    "state": state,
                },
                state,
                evidence,
            )

        for label, formula, tally in element_tallies(attempts, period):
            payload = element_metric_payload(label, formula, tally, period)
            append(ItemType.METRIC, payload, payload["state"], tuple(tally.evidence))

        for thinking_type in ThinkingType:
            matching = [a for a in attempts if a.thinking_type == thinking_type]
            group_state = ReportState.OK if matching else ReportState.NO_RECORD
            append(
                ItemType.THINKING_TYPE,
                {
                    "type": thinking_type,
                    "state": group_state,
                    "missions": [
                        {"attemptId": str(a.id), "title": a.mission_title} for a in matching
                    ],
                },
                group_state,
                tuple(_link(a, a.answers[-1]) for a in matching),
            )

        for attempt in attempts:
            first, last = attempt.answers[0], attempt.answers[-1]
            if len(attempt.answers) > 1 and first.text is not None and last.text is not None:
                pair = pairs.get(attempt.id)
                if pair is None or (
                    pair.first_answer_id,
                    pair.first_text,
                    pair.revised_answer_id,
                    pair.revised_text,
                ) != (first.id, first.text, last.id, last.text):
                    raise RecordContractError(
                        "Change pair differs from first/latest submitted answer"
                    )
                before, after = text_counts(first.written_text), text_counts(last.written_text)
                append(
                    ItemType.CHANGE,
                    {
                        "attemptId": str(attempt.id),
                        "followup": pair.followup,
                        "first": {"answerId": str(first.id), "text": first.text},
                        "revised": {"answerId": str(last.id), "text": last.text},
                        "counts": {key: [before[key], after[key]] for key in before},
                    },
                    ReportState.OK,
                    (_link(attempt, first), _link(attempt, last)),
                )

            reflection = attempt.reflection
            written = reflection is not None and period.includes(reflection.created_at)
            append(
                ItemType.REFLECTION,
                {
                    "attemptId": str(attempt.id),
                    "written": written,
                    "difficulty": reflection.difficulty if written else None,
                    "text": reflection.text if written else None,
                },
                ReportState.OK if written else ReportState.NO_RECORD,
                (_link(attempt, last),),
            )

            if last.text is not None and last.text.strip():
                # R3 verifies candidates against learning evidence before marking them verified.
                append(
                    ItemType.QUOTE,
                    {
                        "attemptId": str(attempt.id),
                        "answerId": str(last.id),
                        "text": last.text,
                        "verified": False,
                    },
                    ReportState.OK,
                    (_link(attempt, last),),
                )

        return GenerationResult(state, INCLUSION_RULE, tuple(items))

    @staticmethod
    def _eligible(records: LearningRecords) -> tuple[AttemptRecord, ...]:
        eligible, attempt_ids, answer_ids = [], set(), set()
        for attempt in records.attempts:
            if attempt.id in attempt_ids or attempt.student_id != records.student_id:
                raise RecordContractError("Duplicate or out-of-scope attempt")
            attempt_ids.add(attempt.id)
            versions = set()
            for answer in attempt.answers:
                if answer.id in answer_ids or answer.version in versions or answer.version < 1:
                    raise RecordContractError("Duplicate answer ID/version")
                answer_ids.add(answer.id)
                versions.add(answer.version)
                # Validate timestamp offsets even for records outside the period.
                records.period.at_or_before_end(answer.submitted_at)
            for opened_at in attempt.hint_opened_at:
                records.period.at_or_before_end(opened_at)
            if attempt.status == "COMPLETED" and attempt.completed_at is None:
                raise RecordContractError("Completed attempt has no completion time")
            if attempt.completed_at is not None:
                records.period.at_or_before_end(attempt.completed_at)
            answers = tuple(
                sorted(
                    (a for a in attempt.answers if records.period.at_or_before_end(a.submitted_at)),
                    key=lambda a: a.version,
                )
            )
            if not any(records.period.includes(a.submitted_at) for a in answers):
                continue
            if all(a.process_status == "FAILED" for a in answers):
                continue
            if [a.version for a in answers] != list(range(1, len(answers) + 1)):
                raise RecordContractError("First/intermediate submitted answers are missing")
            if any(
                a.submitted_at > b.submitted_at for a, b in zip(answers, answers[1:], strict=False)
            ):
                raise RecordContractError("Answer versions have inconsistent submission times")
            eligible.append(replace(attempt, answers=answers))
        return tuple(sorted(eligible, key=lambda a: str(a.id)))

    @staticmethod
    def _check_thinking(records: LearningRecords, attempts: tuple[AttemptRecord, ...]) -> None:
        by_attempt = {}
        for mission in records.thinking_missions:
            if mission.attempt_id in by_attempt:
                raise RecordContractError("Attempt occurs in multiple thinking groups")
            by_attempt[mission.attempt_id] = mission
        for attempt in attempts:
            mission = by_attempt.get(attempt.id)
            if mission is None or (mission.type, mission.title) != (
                attempt.thinking_type,
                attempt.mission_title,
            ):
                raise RecordContractError("Thinking types disagree with submitted records")
