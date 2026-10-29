"""Synthetic fixtures for #51 calculations and the merged #27 response."""

from datetime import date, datetime
from uuid import uuid4

from app.generation.records import (
    AnswerRecord,
    AttemptRecord,
    ChangePair,
    LearningRecords,
    Period,
    ThinkingMission,
    ThinkingType,
)

PERIOD = Period(date(2026, 10, 19), date(2026, 10, 25))


def instant(value="2026-10-20T10:00:00+09:00"):
    return datetime.fromisoformat(value)


def attempt_for(student_id, *, texts=("직접 만든 첫 답변.",), times=None, status="IN_PROGRESS"):
    answers = tuple(
        AnswerRecord(
            uuid4(), i + 1, instant(times[i]) if times else instant(), text, "DONE", text or ""
        )
        for i, text in enumerate(texts)
    )
    return AttemptRecord(
        id=uuid4(),
        student_id=student_id,
        mission_title="합성 미션",
        thinking_type=ThinkingType.ANALYZE,
        status=status,
        answers=answers,
        hint_opened_at=(),
        completed_at=instant() if status == "COMPLETED" else None,
    )


def records_for(student_id, attempts=(), *, period=PERIOD):
    pairs = []
    for attempt in attempts:
        answers = sorted(
            (a for a in attempt.answers if period.at_or_before_end(a.submitted_at)),
            key=lambda a: a.version,
        )
        if len(answers) > 1 and answers[0].text is not None and answers[-1].text is not None:
            first, last = answers[0], answers[-1]
            pairs.append(
                ChangePair(attempt.id, "합성 되묻기", first.id, first.text, last.id, last.text)
            )
    return LearningRecords(
        student_id,
        period,
        tuple(attempts),
        tuple(ThinkingMission(a.thinking_type, a.id, a.mission_title) for a in attempts),
        tuple(pairs),
    )


def wire_attempt(attempt):
    return {
        "attemptId": str(attempt.id),
        "studentId": str(attempt.student_id),
        "mission": {"title": attempt.mission_title, "thinkingType": attempt.thinking_type},
        "status": attempt.status,
        "answers": [
            {
                "answerId": str(a.id),
                "version": a.version,
                "submittedAt": a.submitted_at.isoformat(),
                "text": a.text,
                "inputType": "NARRATIVE",
                "content": {"text": a.written_text},
                "feedback": {"status": a.process_status},
            }
            for a in attempt.answers
        ],
        "hintUsages": [{"openedAt": t.isoformat()} for t in attempt.hint_opened_at],
        "completedAt": attempt.completed_at.isoformat() if attempt.completed_at else None,
        "reflection": {
            "difficulty": attempt.reflection.difficulty,
            "text": attempt.reflection.text,
            "createdAt": attempt.reflection.created_at.isoformat(),
        }
        if attempt.reflection
        else None,
    }


def scope(student_id, *, period=PERIOD):
    return {"studentId": str(student_id), "period": period.payload(), "state": "OK"}


def page(student_id, items, *, index=0, size=100, total=None):
    return {
        **scope(student_id),
        "items": items,
        "page": index,
        "size": size,
        "totalElements": len(items) if total is None else total,
    }


def wire_thinking(student_id, attempts=()):
    return {
        **scope(student_id),
        "items": [
            {
                "type": t,
                "state": "OK" if any(a.thinking_type == t for a in attempts) else "NO_RECORD",
                "missions": [
                    {"attemptId": str(a.id), "title": a.mission_title}
                    for a in attempts
                    if a.thinking_type == t
                ],
            }
            for t in ThinkingType
        ],
    }


def wire_changes(student_id, attempts=()):
    return page(
        student_id,
        [
            {
                "attemptId": str(p.attempt_id),
                "followup": p.followup,
                "first": {"answerId": str(p.first_answer_id), "text": p.first_text},
                "revised": {"answerId": str(p.revised_answer_id), "text": p.revised_text},
            }
            for p in records_for(student_id, attempts).changes
        ],
    )
