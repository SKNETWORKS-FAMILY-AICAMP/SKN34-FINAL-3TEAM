"""Validated theme facts from learning #385; never inferred from daily reports."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool
from pydantic.alias_generators import to_camel

from app.generation.records import RecordContractError


class ThemeModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class ThemeDay(ThemeModel):
    day: Literal["MON", "TUE", "WED", "THU", "FRI"]
    mission_id: UUID
    title: str | None = None
    completed: StrictBool


class ComparedElement(ThemeModel):
    label: str
    previous_satisfied: StrictBool
    current_satisfied: StrictBool


class RetryComparison(ThemeModel):
    state: Literal["NO_PREVIOUS", "COMPARABLE", "CRITERIA_CHANGED"]
    elements: list[ComparedElement]


class ReviewRetry(ThemeModel):
    mission_id: UUID
    title: str | None = None
    comparison: RetryComparison | None = None


class ThemeSummary(ThemeModel):
    state: Literal["OK", "NO_RECORD"]
    theme_id: UUID | None
    title: str | None
    days: list[ThemeDay]
    completed: StrictBool
    review_retries: list[ReviewRetry]


class ThemeSummaryInput(ThemeSummary):
    student_id: UUID
    week_start: date


class ThemeSummaryBuilder:
    def __init__(self, learning):
        self._learning = learning

    async def build(self, student_id, period):
        raw = await self._learning.theme_summary(student_id, period.start)
        value = ThemeSummaryInput.model_validate(raw)
        if value.student_id != student_id or value.week_start != period.start:
            raise RecordContractError("Theme summary scope mismatch")
        days = [day.day for day in value.days]
        if len(set(days)) != len(days) or len(days) > 5:
            raise RecordContractError("Invalid theme day range")
        if value.state == "NO_RECORD":
            if (
                value.completed
                or value.days
                or value.review_retries
                or value.theme_id is not None
                or value.title is not None
            ):
                raise RecordContractError("Nonparticipation must not contain theme observations")
        elif value.theme_id is None or not value.title:
            raise RecordContractError("Participated theme requires identity")
        if value.completed and (len(days) != 5 or not all(day.completed for day in value.days)):
            raise RecordContractError("Theme completion requires all five completed days")
        for retry in value.review_retries:
            if retry.comparison and retry.comparison.state != "COMPARABLE":
                if retry.comparison.elements:
                    raise RecordContractError("Cannot compare elements across changed criteria")
        return value.model_dump(mode="json", by_alias=True, exclude={"student_id", "week_start"})
