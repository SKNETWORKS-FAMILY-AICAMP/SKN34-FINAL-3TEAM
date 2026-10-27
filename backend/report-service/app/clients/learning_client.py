"""Strict reader for API 4.1.1's #51 proposal; real #27 compatibility is still pending."""

from datetime import date
from typing import Literal
from uuid import UUID

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StrictInt
from pydantic.alias_generators import to_camel

from app.clients.base import internal_client
from app.config import get_settings
from app.generation.models import EvidenceLink
from app.generation.records import (
    AnswerRecord,
    AttemptRecord,
    ChangePair,
    EvidenceRecord,
    LearningRecords,
    Period,
    RecordContractError,
    ReflectionRecord,
    ThinkingMission,
    ThinkingType,
)
from app.security import current_user_context


class InputModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class PeriodInput(InputModel):
    from_: date = Field(alias="from")
    to: date


class ScopeInput(InputModel):
    child_id: UUID
    period: PeriodInput
    state: Literal["OK", "NO_RECORD", "INSUFFICIENT_SAMPLE", "PROCESSING", "FAILED"]


class PageInput(ScopeInput):
    page: StrictInt = Field(ge=0)
    size: StrictInt = Field(ge=1, le=100)
    total_elements: StrictInt = Field(ge=0)
    items: list[dict]


class FeedbackInput(InputModel):
    status: Literal["PENDING", "RUNNING", "DONE", "FAILED"]


class AnswerInput(InputModel):
    answer_id: UUID
    version: StrictInt = Field(ge=1)
    submitted_at: AwareDatetime
    text: str | None
    feedback: FeedbackInput


class MissionInput(InputModel):
    title: str
    thinking_type: ThinkingType


class HintInput(InputModel):
    opened_at: AwareDatetime


class ReflectionInput(InputModel):
    difficulty: str
    text: str | None
    created_at: AwareDatetime


class AttemptInput(InputModel):
    attempt_id: UUID
    student_id: UUID
    mission: MissionInput
    status: Literal["IN_PROGRESS", "COMPLETED"]
    answers: list[AnswerInput]
    hint_usages: list[HintInput]
    completed_at: AwareDatetime | None = None
    reflection: ReflectionInput | None = None
    available: StrictBool = True

    def record(self) -> AttemptRecord:
        return AttemptRecord(
            id=self.attempt_id,
            student_id=self.student_id,
            mission_title=self.mission.title,
            thinking_type=self.mission.thinking_type,
            status=self.status,
            answers=tuple(
                AnswerRecord(a.answer_id, a.version, a.submitted_at, a.text, a.feedback.status)
                for a in self.answers
            ),
            hint_opened_at=tuple(h.opened_at for h in self.hint_usages),
            completed_at=self.completed_at,
            reflection=ReflectionRecord(
                self.reflection.difficulty, self.reflection.text, self.reflection.created_at
            )
            if self.reflection is not None
            else None,
        )


class ThinkingMissionInput(InputModel):
    attempt_id: UUID
    title: str


class ThinkingInput(InputModel):
    type: ThinkingType
    state: Literal["OK", "NO_RECORD", "INSUFFICIENT_SAMPLE"]
    missions: list[ThinkingMissionInput]


class ThinkingResponse(ScopeInput):
    items: list[ThinkingInput]


class ChangeAnswerInput(InputModel):
    answer_id: UUID
    text: str


class ChangeInput(InputModel):
    attempt_id: UUID
    followup: str
    first: ChangeAnswerInput
    revised: ChangeAnswerInput

    def record(self) -> ChangePair:
        return ChangePair(
            self.attempt_id,
            self.followup,
            self.first.answer_id,
            self.first.text,
            self.revised.answer_id,
            self.revised.text,
        )


class LearningClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        # Production callers use internal_client(); tests inject MockTransport on that client.
        self._client = client

    @classmethod
    def configured(cls) -> "LearningClient":
        return cls(internal_client(get_settings().learning_url))

    async def close(self) -> None:
        await self._client.aclose()

    async def evidence(
        self, student_id: UUID, links: tuple[EvidenceLink, ...]
    ) -> tuple[EvidenceRecord, ...]:
        context = current_user_context()
        if context is None:
            raise RecordContractError("Evidence lookup requires a user context")
        context.require_student(str(student_id))
        expected = {}
        for link in links:
            if link.answer_id in expected and expected[link.answer_id] != link:
                raise RecordContractError("Conflicting evidence identity")
            expected[link.answer_id] = link
        results = []
        keys = list(expected)
        for start in range(0, len(keys), 50):
            batch = keys[start : start + 50]
            response = await self._client.get(
                "/internal/records/evidence",
                params={"answerIds": ",".join(str(key) for key in batch)},
            )
            if response.status_code == 410:
                results.extend(
                    EvidenceRecord(
                        key, expected[key].attempt_id, expected[key].answer_version, None, False
                    )
                    for key in batch
                )
                continue
            response.raise_for_status()
            parsed = EvidenceResponse.model_validate(response.json())
            seen = set()
            for item in parsed.items:
                if item.answer_id not in batch or item.answer_id in seen:
                    raise RecordContractError("Unexpected or duplicate evidence answer")
                seen.add(item.answer_id)
                link = expected[item.answer_id]
                if item.available and (
                    item.attempt_id != link.attempt_id
                    or item.answer_version != link.answer_version
                    or item.quote is None
                ):
                    raise RecordContractError("Evidence identity/version is inconsistent")
                results.append(
                    EvidenceRecord(
                        item.answer_id,
                        link.attempt_id,
                        link.answer_version,
                        item.quote if item.available else None,
                        item.available,
                        item.mission_title if item.available else None,
                        item.submitted_at if item.available else None,
                    )
                )
            if seen != set(batch):
                raise RecordContractError("Evidence response is incomplete")
        return tuple(results)

    @staticmethod
    def _check_scope(response: ScopeInput, student_id: UUID, period: Period) -> None:
        if response.child_id != student_id or (response.period.from_, response.period.to) != (
            period.start,
            period.end,
        ):
            raise RecordContractError("Learning response student/period differs from request")
        if response.state in ("PROCESSING", "FAILED"):
            raise RecordContractError("Learning records are not ready")

    async def _get(self, student_id: UUID, suffix: str, params: dict) -> dict:
        response = await self._client.get(
            f"/internal/records/students/{student_id}/{suffix}", params=params
        )
        response.raise_for_status()
        return response.json()

    async def _pages(self, student_id: UUID, period: Period, suffix: str) -> list[dict]:
        items, page, expected_total, expected_size = [], 0, None, None
        attempt_ids = set()
        while True:
            raw = await self._get(
                student_id,
                suffix,
                {
                    **period.payload(),
                    "page": page,
                    "size": 100,
                },
            )
            response = PageInput.model_validate(raw)
            self._check_scope(response, student_id, period)
            if response.page != page:
                raise RecordContractError("Learning returned the wrong page")
            if expected_total is None:
                expected_total = response.total_elements
                expected_size = response.size
            if response.total_elements != expected_total:
                raise RecordContractError("Learning record count changed during pagination")
            if response.size != expected_size:
                raise RecordContractError("Learning page size changed during pagination")
            if (
                len(response.items) > response.size
                or len(items) + len(response.items) > expected_total
            ):
                raise RecordContractError("Learning page size/total is inconsistent")
            for item in response.items:
                try:
                    attempt_id = UUID(item["attemptId"])
                except (KeyError, ValueError, TypeError) as exc:
                    raise RecordContractError("Learning item has no valid attempt ID") from exc
                if attempt_id in attempt_ids:
                    raise RecordContractError("Duplicate attempt across learning pages")
                attempt_ids.add(attempt_id)
            items.extend(response.items)
            if len(items) == expected_total:
                return items
            if len(response.items) != response.size:
                raise RecordContractError("Learning records have a missing page")
            page += 1

    async def records(self, student_id: UUID, period: Period) -> LearningRecords:
        context = current_user_context()
        if context is None:
            raise RecordContractError("Learning calls require a scoped user context")
        context.require_student(str(student_id))
        # No automatic retry. A failed page is a failed generation, never an empty result.
        raw_attempts = await self._pages(student_id, period, "attempts")
        raw_thinking = await self._get(student_id, "thinking-types", period.payload())
        thinking = ThinkingResponse.model_validate(raw_thinking)
        self._check_scope(thinking, student_id, period)
        if len({group.type for group in thinking.items}) != len(thinking.items):
            raise RecordContractError("Duplicate thinking type")
        if any(group.state == "NO_RECORD" and group.missions for group in thinking.items):
            raise RecordContractError("Thinking NO_RECORD group contains records")
        raw_changes = await self._pages(student_id, period, "changes")
        attempts = []
        for raw in raw_attempts:
            if raw.get("available") is False:
                # Tombstones intentionally carry no answer, draft or memo content.
                continue
            item = AttemptInput.model_validate(raw)
            if item.student_id != student_id:
                raise RecordContractError("Learning returned another student's attempt")
            attempts.append(item.record())
        return LearningRecords(
            student_id,
            period,
            tuple(attempts),
            tuple(
                ThinkingMission(group.type, mission.attempt_id, mission.title)
                for group in thinking.items
                for mission in group.missions
            ),
            tuple(ChangeInput.model_validate(raw).record() for raw in raw_changes),
        )


class EvidenceInput(InputModel):
    answer_id: UUID
    attempt_id: UUID | None = None
    answer_version: StrictInt | None = None
    quote: str | None = None
    available: StrictBool
    mission_title: str | None = None
    submitted_at: AwareDatetime | None = None


class EvidenceResponse(InputModel):
    items: list[EvidenceInput]
