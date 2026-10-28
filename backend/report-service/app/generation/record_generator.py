"""R2 generation stage; R3/R4 can compose its result before the terminal transaction."""

from typing import Protocol
from uuid import UUID

from app.generation.metrics import MetricsCalculator
from app.generation.models import GenerateReport, GenerationResult, WeeklyReport
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
        return self._calculator.calculate(records)
