"""R2 generation stage; R3/R4 can compose its result before the terminal transaction."""

from dataclasses import replace
from typing import Protocol
from uuid import UUID

from app.generation.metrics import MetricsCalculator
from app.generation.models import GenerateReport, GenerationResult, ItemType, WeeklyReport
from app.generation.records import LearningRecords, Period, RecordContractError


class RecordReader(Protocol):
    async def records(self, student_id: UUID, period: Period) -> LearningRecords: ...


class RecordGenerator:
    def __init__(self, learning: RecordReader, calculator: MetricsCalculator | None = None) -> None:
        self._learning = learning
        self._calculator = calculator or MetricsCalculator()

    async def generate(self, command: GenerateReport, report: WeeklyReport) -> GenerationResult:
        period = Period(command.period_from, command.period_to)
        records = await self._learning.records(command.student_id, period)
        if records.student_id != command.student_id or records.period != period:
            raise RecordContractError("Record reader returned another student/period")
        result = self._calculator.calculate(records)
        if command.parent_sharing_enabled:
            return result
        # Remove raw text and evidence BEFORE AI composition, persistence and file rendering.
        safe = []
        allowed = {
            ItemType.THINKING_TYPE: {"type", "state", "missions"},
            ItemType.CHANGE: {"attemptId", "counts"},
            ItemType.REFLECTION: {"attemptId", "written", "difficulty"},
        }
        for item in result.items:
            if item.type == ItemType.QUOTE:
                continue
            payload = (
                item.payload
                if item.type == ItemType.METRIC
                else {
                    key: value for key, value in item.payload.items() if key in allowed[item.type]
                }
            )
            if item.type == ItemType.CHANGE:
                payload = {
                    **payload,
                    "first": {"text": None},
                    "revised": {"text": None},
                    "followup": None,
                }
            elif item.type == ItemType.REFLECTION:
                payload = {**payload, "text": None}
            safe.append(replace(item, payload=payload, evidence=()))
        return replace(result, items=tuple(safe), narrative=None, evening_question=None)
