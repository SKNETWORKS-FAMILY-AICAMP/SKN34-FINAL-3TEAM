"""R3 composes R2, verifies AI output and uses a template only on verification failure."""

from dataclasses import replace

from app.clients.ai_client import AiClient
from app.clients.learning_client import LearningClient
from app.generation.models import (
    GenerateReport,
    GenerationResult,
    ItemType,
    ReportState,
    WeeklyReport,
)
from app.generation.ports import ReportGenerator
from app.generation.records import RecordContractError
from app.generation.verifier import ReportVerifier


def scrub(value, display_name):
    if isinstance(value, dict):
        return {
            k: scrub(v, display_name)
            for k, v in value.items()
            if k not in {"name", "nickname", "studentName", "studentId", "childId"}
        }
    if isinstance(value, list):
        return [scrub(v, display_name) for v in value]
    if isinstance(value, str) and display_name:
        return value.replace(display_name, "[학생]")
    return value


class NarrativeGenerator:
    def __init__(self, previous: ReportGenerator, ai: AiClient, learning: LearningClient) -> None:
        self._previous, self._ai, self._learning = previous, ai, learning

    async def generate(self, command: GenerateReport, report: WeeklyReport) -> GenerationResult:
        result = await self._previous.generate(command, report)
        if not command.narrative_enabled or result.state == ReportState.NO_RECORD:
            return replace(
                result,
                narrative=None,
                evening_question=None,
                verification={
                    "numbersMatched": True,
                    "quotesMatched": True,
                    "contentAllowed": True,
                },
                versions={"prompt": None, "model": None},
            )
        if not command.display_name:
            raise RecordContractError("A trusted display name is required for privacy filtering")
        groups = {
            ItemType.METRIC: "metrics",
            ItemType.THINKING_TYPE: "thinkingTypes",
            ItemType.CHANGE: "changes",
            ItemType.REFLECTION: "reflections",
            ItemType.QUOTE: "quotes",
        }
        payload = {
            name: [item.payload for item in result.items if item.type == kind]
            for kind, name in groups.items()
        }
        response = await self._ai.narrative(scrub(payload, command.display_name))
        links = tuple(
            link for item in result.items if item.type == ItemType.QUOTE for link in item.evidence
        )
        evidence = await self._learning.evidence(command.student_id, links)
        verification = ReportVerifier().verify(response, result, evidence)
        by_id = {str(e.answer_id): e for e in evidence}
        verified_items = []
        for item in result.items:
            if item.type == ItemType.QUOTE:
                original = by_id.get(item.payload["answerId"])
                verified = bool(
                    original
                    and original.available
                    and original.text
                    and item.payload["text"] in original.text
                )
                payload = {**item.payload, "verified": verified}
                if original is not None and not original.available:
                    payload["text"] = None
                verified_items.append(replace(item, verified=verified, payload=payload))
            else:
                verified_items.append(
                    replace(item, verified=item.type in (ItemType.METRIC, ItemType.CHANGE))
                )
        if verification.passed:
            narrative = response.narrative.model_dump(by_alias=True)
            question = response.evening_question
        else:
            count = next(i.payload["count"] for i in result.items if i.type == ItemType.METRIC)
            narrative = {
                "text": (
                    f"이번 주에는 답변 제출 시도 {count}건이 확인되었습니다. "
                    "기록에서 내용을 확인해 주세요."
                ),
                "source": "TEMPLATE",
                "modelExplanation": None,
            }
            question = None
        return replace(
            result,
            items=tuple(verified_items),
            narrative=narrative,
            verification=verification.payload(),
            versions=response.versions.model_dump(),
            evening_question=question,
        )
