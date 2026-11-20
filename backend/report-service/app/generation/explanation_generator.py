"""Optional weekly explanations (#479): failures never invalidate the base report."""

import asyncio
import logging
import re
from dataclasses import replace

from app.config import get_settings
from app.generation.models import EvidenceLink, ItemType, ReportItem
from app.generation.narrative_generator import scrub
from app.generation.records import Period, RecordContractError
from app.generation.verifier import KOREAN_COUNT, QUOTED, UNSUPPORTED_CLAIM

logger = logging.getLogger(__name__)
FORBIDDEN = re.compile(r"점수|등급|레벨|순위|사고력|백분위|백분율|퍼센트|퍼센트포인트")


EXPLAINED_INPUTS = ("NARRATIVE", "ESSAY")
NUMBER = re.compile(r"\d+")


def candidates(attempts, period):
    # 2026-11-16 local Gemma detail: an m2 score is no longer required; the detail prompt reads
    # the answer and mission title only, and scores are forwarded when they exist.
    rows = [
        (attempt, answer)
        for attempt in attempts
        for answer in attempt.answers
        if period.includes(answer.submitted_at)
        and answer.process_status == "DONE"
        and answer.input_type in EXPLAINED_INPUTS
    ]
    # Newest first. The caller tries the next answer of the same type when one fails the
    # pre-call checks, so an excluded latest answer does not empty its type (#508).
    rows.sort(key=lambda row: (row[1].submitted_at, row[1].version, str(row[1].id)), reverse=True)
    return rows


SCORE_RANGES = {
    "NARRATIVE": {
        "hol": (1, 4),
        **dict.fromkeys(
            (
                "task_1",
                "content_1",
                "content_2",
                "content_3",
                "organization_1",
                "organization_2",
                "expression_1",
                "expression_2",
            ),
            (1, 5),
        ),
    },
    "ESSAY": dict.fromkeys(("org", "cont", "exp"), (0, 3)),
}


STORED_GRADES = range(3, 10)  # core stored grade: elementary 3 (3) to middle 3 (9), P26
# Middle schoolers get grade-6 content until middle school is supported (P03), the same cap as
# core StudentGrade.learning.
EXPLANATION_GRADE_MAX = 6


def explanation_grade(grade):
    """Stored grade (3~9) to the grade used for explanations; None when untrusted (#830)."""
    if type(grade) is not int or grade not in STORED_GRADES:
        return None
    return min(grade, EXPLANATION_GRADE_MAX)


def input_scores(answer, grade):
    """m2 scores when present (validated), otherwise None. Scope and text are always checked."""
    if type(grade) is not int or not (
        answer.input_type == "NARRATIVE"
        and grade in (5, 6)
        or answer.input_type == "ESSAY"
        and grade in (4, 5, 6)
    ):
        raise RecordContractError("Explanation is outside the supported scope")
    judgment = answer.judgment
    if (judgment is not None and judgment.corrected) or not answer.written_text.strip():
        raise RecordContractError("Explanation requires an unchanged answer")
    models = judgment.model_scores if judgment is not None else None
    model = models.get("m2") if isinstance(models, dict) else None
    if model is None:
        return None
    scores = model.get("scores") if isinstance(model, dict) else None
    ranges = SCORE_RANGES[answer.input_type]
    if (
        not isinstance(scores, dict)
        or set(scores) != set(ranges)
        or any(
            type(scores[key]) is not int or not low <= scores[key] <= high
            for key, (low, high) in ranges.items()
        )
    ):
        raise RecordContractError("Invalid explanation score input")
    return scores


def unsupported_numbers(text, original):
    """Numbers and counted phrases are allowed only when the student wrote them (e.g. "30분")."""
    if any(char.isnumeric() and char not in "0123456789" for char in text):
        return True
    if not set(NUMBER.findall(text)) <= set(NUMBER.findall(original)):
        return True  # whole numbers only: "3" is not allowed by an original "30"
    return any(match.group(0) not in original for match in KOREAN_COUNT.finditer(text))


def verify(explanation, original, command, request_text):
    text, quote = explanation.text, explanation.quote
    if (
        not text.strip()
        or unsupported_numbers(text, original)
        or FORBIDDEN.search(text)
        or UNSUPPORTED_CLAIM.search(text)
        or command.display_name in text
        or str(command.student_id) in text
        or any(value not in original for value in QUOTED.findall(text))
    ):
        raise RecordContractError("Explanation content was rejected")
    if quote is not None and (
        not quote.strip() or quote not in original or quote not in request_text
    ):
        raise RecordContractError("Explanation quote does not match the submitted answer")


class ExplanationGenerator:
    def __init__(self, previous, ai, learning):
        self._previous, self._ai, self._learning = previous, ai, learning

    async def generate(self, command, report):
        result = await self._previous.generate(command, report)
        if command.period_type != "WEEKLY" or not command.explanation_enabled:
            return result
        if not command.parent_sharing_enabled:
            return replace(result, explanation_state="NO_TARGET")
        settings = get_settings()
        items, state = [], "NOT_INCLUDED"
        try:
            async with asyncio.timeout(settings.report_explanation_budget_seconds):
                if not command.display_name:
                    raise RecordContractError("Explanation requires a trusted profile")
                period = Period(command.period_from, command.period_to)
                attempts = await self._learning.explanation_attempts(command.student_id, period)
                if any(attempt.student_id != command.student_id for attempt in attempts):
                    raise RecordContractError("Explanation records are outside the student scope")
                rows = candidates(attempts, period)
                grade = explanation_grade(command.grade)
                if not rows:
                    state = "NO_TARGET"
                elif grade is None:
                    # A missing grade excludes every answer; skip per-answer fallback.
                    raise RecordContractError("Explanation requires a trusted grade")
                called = set()
                for attempt, answer in rows:
                    if len(called) == 3:
                        break
                    if attempt.thinking_type in called:
                        continue
                    try:
                        scores = input_scores(answer, grade)
                        link = EvidenceLink(attempt.id, answer.id, answer.version)
                        evidence = await self._learning.evidence(command.student_id, (link,))
                        if len(evidence) != 1:
                            raise RecordContractError("Explanation evidence missing")
                        original = evidence[0]
                        if (
                            not original.available
                            or not original.text
                            or (original.attempt_id, original.answer_id, original.version)
                            != (attempt.id, answer.id, answer.version)
                            or original.text != answer.text
                        ):
                            raise RecordContractError(
                                "Explanation evidence is unavailable or stale"
                            )
                    except Exception:
                        # Try the next answer of the same type; no sLLM call was made.
                        logger.warning("Report explanation candidate skipped before call")
                        continue
                    # One sLLM call per type at most, whatever its outcome.
                    called.add(attempt.thinking_type)
                    try:
                        text = scrub(answer.written_text, command.display_name)
                        # Identifier strings in a submitted answer are not forwarded either.
                        for identifier in (command.student_id, attempt.id, answer.id):
                            text = text.replace(str(identifier), "[식별정보]")
                        response = await asyncio.wait_for(
                            self._ai.explanation(
                                {
                                    "grade": grade,
                                    "inputType": answer.input_type,
                                    "text": text,
                                    "topic": attempt.mission_title,
                                    **({"scores": scores} if scores is not None else {}),
                                },
                                settings.report_explanation_timeout_seconds,
                            ),
                            timeout=settings.report_explanation_timeout_seconds,
                        )
                        if not response.active:
                            continue
                        verify(response.explanation, original.text, command, text)
                        payload = {
                            "attemptId": str(attempt.id),
                            "answerId": str(answer.id),
                            "answerVersion": answer.version,
                            "missionTitle": attempt.mission_title,
                            "thinkingType": attempt.thinking_type,
                            "quote": response.explanation.quote,
                            "text": response.explanation.text,
                        }
                        items.append(
                            ReportItem(
                                ItemType.EXPLANATION,
                                len(items),
                                payload,
                                result.state,
                                True,
                                (link,),
                            )
                        )
                    except Exception:
                        # No response body, student text, score or exception message in logs.
                        logger.warning(
                            "Report explanation omitted after call or verification failure"
                        )
        except Exception:
            logger.warning("Report explanation stage incomplete; base report retained")
        return replace(
            result, items=(*result.items, *items), explanation_state="INCLUDED" if items else state
        )
