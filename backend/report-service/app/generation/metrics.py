"""P08 calculations from submitted records only. No inferred text, AI calls or scores."""

import re
from collections import Counter
from dataclasses import replace

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
    LearningRecords,
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
        "sentences": sum(bool(part.strip()) for part in re.split(r"[.?!\r\n]+", text)),
        "reasonConnectives": sum(text.count(word) for word in REASON_CONNECTIVES),
    }


def _link(attempt: AttemptRecord, answer: AnswerRecord) -> EvidenceLink:
    return EvidenceLink(attempt.id, answer.id, answer.version)


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
                before, after = text_counts(first.text), text_counts(last.text)
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
