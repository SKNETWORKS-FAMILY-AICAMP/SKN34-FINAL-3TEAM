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
    # M2 scores are optional; the detail prompt uses the saved criterion judgments.
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


def explanation_payload(command, attempt, answer, grade, scores):
    def redacted(value):
        text = scrub(value, command.display_name)
        for identifier in (command.student_id, attempt.id, answer.id):
            text = text.replace(str(identifier), "[식별정보]")
        return text

    # Redact the fields before joining so the essay and its quote source always agree.
    essay = None
    if answer.essay is not None:
        essay = {
            "claim": redacted(answer.essay.claim),
            "reasons": [redacted(reason) for reason in answer.essay.reasons],
            "rebuttal": redacted(answer.essay.rebuttal),
        }
    text = (
        "\n".join(
            part for part in (essay["claim"], *essay["reasons"], essay["rebuttal"]) if part.strip()
        )
        if essay is not None
        else redacted(answer.written_text)
    )
    payload = {
        "grade": grade,
        "inputType": answer.input_type,
        "text": text,
        "topic": redacted(attempt.mission_title),
    }
    if attempt.mission_question and attempt.mission_question.strip():
        payload["question"] = redacted(attempt.mission_question)
    if essay is not None:
        payload["essay"] = essay
    if scores is not None:
        payload["scores"] = scores
    judgment = answer.judgment
    if judgment is None or judgment.result == "HELD" or judgment.corrected:
        return payload

    criteria = []
    for element in judgment.elements:
        label = (element.label or "").strip()
        requirement = attempt.explanation_requirements.get(element.element_id, "").strip()
        quote = (element.quote or "").strip()
        # Omit conflicting evidence and identifiers, never recast them as a missing quote.
        if not label or (quote and (quote not in text or redacted(quote) != quote)):
            continue
        criteria.append(
            {
                "label": redacted(label),
                "requirement": redacted(requirement) if requirement else None,
                "satisfied": element.satisfied,
                "required": not element.good_thought,
                "quote": quote or None,
            }
        )
    if criteria:
        payload["criteria"] = criteria
    return payload


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
        all_activities = settings.report_local_all_activity_explanations
        budget = None if all_activities else settings.report_explanation_budget_seconds
        items, state = [], "NOT_INCLUDED"
        try:
            async with asyncio.timeout(budget):
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
                    if not all_activities and len(called) == 3:
                        break
                    selection_key = attempt.id if all_activities else attempt.thinking_type
                    if selection_key in called:
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
                    # Call once per activity in the demo, once per thinking type by default.
                    called.add(selection_key)
                    try:
                        request = explanation_payload(command, attempt, answer, grade, scores)
                        response = await asyncio.wait_for(
                            self._ai.explanation(
                                request,
                                settings.report_explanation_timeout_seconds,
                            ),
                            timeout=settings.report_explanation_timeout_seconds,
                        )
                        if not response.active:
                            continue
                        verify(response.explanation, original.text, command, request["text"])
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
