"""learning 추억 그림책 회차 조립 응답 읽기 (docs/proposals/memory-book.md 7.2, 미도입 시험 구현).

응답 모양이 틀리면 RecordContractError(재시도해도 같으므로 영구 실패로 본다).
404(미보유·진행 중인 주)는 MemoryBookRoundNotFound로 따로 알린다.
"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError

from app.generation.records import RecordContractError
from app.security import current_user_context

Day = Literal["MON", "TUE", "WED", "THU", "FRI"]
ThinkingType = Literal["ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT"]


class MemoryBookRoundNotFound(Exception):
    """보유하지 않은 회차(learning 404 THEME_FRAME_NOT_FOUND)."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Followup(_Model):
    type: str
    question: str


class Answer(_Model):
    version: StrictInt = Field(ge=1)
    text: str
    followup: Followup | None = None


class Reflection(_Model):
    difficulty: str | None = None
    text: str | None = None


class Attempt(_Model):
    attemptId: UUID
    completedAt: datetime | None = None
    answers: list[Answer]
    reflection: Reflection | None = None


class Line(_Model):
    speaker: str
    text: str


class BookDay(_Model):
    day: Day
    missionId: UUID
    title: str
    thinkingType: ThinkingType
    question: str
    sceneImage: str | None = None
    dialogue: list[Line]
    attempt: Attempt | None = None


class Ending(_Model):
    seen: StrictBool
    outro: str | None = None
    answer: str | None = None
    outroImage: str | None = None


class MemoryBookRound(_Model):
    themeId: UUID
    weekStart: date
    themeVersionId: UUID
    title: str
    intro: str
    introImage: str | None = None
    bigQuestion: str | None = None
    days: list[BookDay] = Field(min_length=1, max_length=5)
    ending: Ending


class MemoryBookLearningClient:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def round(self, student_id: UUID, theme_id: UUID, week_start: date) -> MemoryBookRound:
        context = current_user_context()
        if context is None or context.role != "SYSTEM":
            raise RecordContractError("Memory book requires a SYSTEM context")
        context.require_student(str(student_id))
        response = await self._client.get(
            f"/internal/students/{student_id}/memory-book/{theme_id}/{week_start.isoformat()}"
        )
        if response.status_code == 404:
            raise MemoryBookRoundNotFound()
        response.raise_for_status()
        try:
            round_ = MemoryBookRound.model_validate(response.json())
        except (ValidationError, ValueError):
            raise RecordContractError("Invalid memory book round") from None
        if (round_.themeId, round_.weekStart) != (theme_id, week_start):
            raise RecordContractError("Memory book round identity mismatch")
        if round_.ending.seen is False and (
            round_.ending.outro or round_.ending.answer or round_.ending.outroImage
        ):
            # P23: 엔딩 전 내용이 섞여 오면 렌더링하지 않는다
            raise RecordContractError("Ending content before the ending")
        return round_
