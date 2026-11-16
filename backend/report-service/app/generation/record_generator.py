"""R2 generation stage; R3/R4 can compose its result before the terminal transaction."""

from dataclasses import replace
from typing import Protocol
from uuid import UUID

from app.generation.daily import DailyReportBuilder
from app.generation.metrics import MetricsCalculator
from app.generation.models import (
    EvidenceLink,
    GenerateReport,
    GenerationResult,
    ItemType,
    WeeklyReport,
)
from app.generation.records import EvidenceRecord, LearningRecords, Period, RecordContractError


class RecordReader(Protocol):
    async def records(self, student_id: UUID, period: Period) -> LearningRecords: ...

    async def daily_records(self, student_id: UUID, period: Period) -> LearningRecords: ...

    async def evidence(
        self, student_id: UUID, links: tuple[EvidenceLink, ...]
    ) -> tuple[EvidenceRecord, ...]: ...


class RecordGenerator:
    def __init__(
        self,
        learning: RecordReader,
        calculator: MetricsCalculator | None = None,
        theme_builder=None,
    ) -> None:
        self._learning = learning
        self._theme_builder = theme_builder
        self._calculator = calculator or MetricsCalculator()

    async def generate(self, command: GenerateReport, report: WeeklyReport) -> GenerationResult:
        period = Period(command.period_from, command.period_to)
        records = await (
            self._learning.daily_records(command.student_id, period)
            if command.period_type == "DAILY"
            else self._learning.records(command.student_id, period)
        )
        if records.student_id != command.student_id or records.period != period:
            raise RecordContractError("Record reader returned another student/period")
        if command.period_type == "DAILY":
            return await DailyReportBuilder().build(
                records, command.parent_sharing_enabled, self._learning
            )
        result = self._calculator.calculate(records)
        if self._theme_builder is not None:
            result = replace(
                result, theme_summary=await self._theme_builder.build(command.student_id, period)
            )
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
