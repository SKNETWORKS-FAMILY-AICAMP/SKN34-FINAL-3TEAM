"""P24 daily facts. No model, narrative, ratios or parent template is involved."""

from app.generation.metrics import thinking_elements
from app.generation.models import EvidenceLink, GenerationResult, ItemType, ReportItem, ReportState
from app.generation.records import RecordContractError

INCLUSION_RULE = "해당 KST 날짜에 완료한 모든 시도. 주말 되돌아보기 재시도·추가 문제 포함."


class DailyReportBuilder:
    async def build(self, records, sharing, learning):
        problems = []
        seen = set()
        for attempt in records.attempts:
            if attempt.student_id != records.student_id or attempt.id in seen:
                raise RecordContractError("Invalid daily attempt identity")
            seen.add(attempt.id)
            if (
                attempt.status != "COMPLETED"
                or attempt.completed_at is None
                or not records.period.includes(attempt.completed_at)
            ):
                continue
            if attempt.mission_id is None:
                raise RecordContractError("Daily report requires the source mission ID")
            answers = sorted(
                (a for a in attempt.answers if a.submitted_at <= attempt.completed_at),
                key=lambda a: a.version,
            )
            if not answers or len({a.version for a in answers}) != len(answers):
                raise RecordContractError("Missing or duplicate daily answers")
            last = answers[-1]
            judgment = last.judgment if last.process_status == "DONE" else None
            elements = thinking_elements(judgment) if judgment else ()
            quotes, links = [], []
            if sharing:
                # Re-fetch evidence before storage; never manufacture an excerpt.
                candidates = [
                    (a, e.quote)
                    for a in answers
                    if a.judgment and a.process_status == "DONE"
                    for e in a.judgment.elements
                    if e.quote
                ]
                requested = tuple(
                    dict.fromkeys(EvidenceLink(attempt.id, a.id, a.version) for a, _ in candidates)
                )
                evidence = (
                    await learning.evidence(records.student_id, requested) if requested else ()
                )
                sources = {(e.attempt_id, e.answer_id, e.version): e for e in evidence}
                for answer, quote in candidates:
                    source = sources.get((attempt.id, answer.id, answer.version))
                    if (
                        source is None
                        or not source.available
                        or source.text is None
                        or quote not in source.text
                    ):
                        raise RecordContractError("Daily quote could not be verified")
                    entry = {"answerId": str(answer.id), "text": quote, "verified": True}
                    if entry not in quotes:
                        quotes.append(entry)
                        links.append(EvidenceLink(attempt.id, answer.id, answer.version))
            reflection = attempt.reflection
            payload = {
                "missionId": str(attempt.mission_id),
                "attemptId": str(attempt.id),
                "title": attempt.mission_title,
                "context": attempt.context,
                "judgment": judgment.result if judgment else None,
                "followups": [
                    {
                        "question": a.followup,
                        "answer": answers[i + 1].text if i + 1 < len(answers) else None,
                    }
                    for i, a in enumerate(answers)
                    if a.followup
                ]
                if sharing
                else [],
                "finalAnswer": last.text if sharing else None,
                "elements": [
                    {"label": e.label or e.code, "satisfied": e.satisfied} for e in elements
                ]
                if judgment and judgment.result != "HELD" and not judgment.corrected
                else [],
                "reflection": {
                    "written": reflection is not None,
                    "difficulty": reflection.difficulty if reflection else None,
                    "text": reflection.text if reflection and sharing else None,
                },
                "quotes": quotes,
            }
            problems.append(
                ReportItem(
                    ItemType.PROBLEM,
                    len(problems) + 1,
                    payload,
                    ReportState.OK,
                    True,
                    tuple(dict.fromkeys(links)),
                )
            )
        count = len(problems)
        state = ReportState.OK if count else ReportState.NO_RECORD
        metric = ReportItem(
            ItemType.METRIC,
            1,
            {
                "label": "완료한 활동",
                "value": None,
                "count": count,
                "numerator": count,
                "denominator": count,
                "formula": "해당 날짜에 완료한 시도 수",
                "period": records.period.payload(),
                "sourceType": "RECORD",
                "state": state,
            },
            state,
            True,
        )
        return GenerationResult(
            state,
            INCLUSION_RULE,
            (metric, *problems),
            verification={"numbersMatched": True, "quotesMatched": True},
        )
