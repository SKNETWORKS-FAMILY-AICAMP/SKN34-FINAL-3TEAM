"""memorybook.generate 명령 소비 (docs/proposals/memory-book.md 7.2).

SYSTEM 역할·그 학생 범위로 처리한다.
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.memory_book.models import GENERATE_SCHEMA, GENERATE_TYPE, GenerateMemoryBook
from app.messaging.contracts import InvalidEvent, uuid_text
from app.security import UserContext, bind_user_context, reset_user_context

MEMORY_BOOK_QUEUE = "report.memorybook.generate"


class RoundData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    themeId: UUID
    weekStart: date

    @field_validator("themeId", mode="before")
    @classmethod
    def uuid_field(cls, value):
        return uuid_text(value)

    @field_validator("weekStart")
    @classmethod
    def monday(cls, value: date):
        if value.weekday() != 0:
            raise ValueError("weekStart must be a Monday")
        return value


class GenerateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bookId: UUID
    studentId: UUID
    # 1차는 회차 1개(D3). 묶음은 길이 상한만 풀면 된다
    rounds: list[RoundData] = Field(min_length=1, max_length=1)
    requestedBy: UUID | None = None

    @field_validator("bookId", "studentId", "requestedBy", mode="before")
    @classmethod
    def uuid_field(cls, value):
        return None if value is None else uuid_text(value)


class MemoryBookConsumer:
    def __init__(self, service):
        self._service = service

    async def __call__(self, envelope):
        try:
            if (envelope.type, envelope.source, envelope.dataschema) != (
                GENERATE_TYPE,
                "core-service",
                GENERATE_SCHEMA,
            ):
                raise ValueError("Unsupported memory book command")
            data = GenerateData.model_validate(envelope.data)
            if uuid_text(envelope.subject) != data.studentId:
                raise ValueError("Student identity mismatch")
            command = GenerateMemoryBook(
                data.bookId,
                data.studentId,
                data.rounds[0].themeId,
                data.rounds[0].weekStart,
                envelope.time,
            )
        except (ValueError, TypeError, AttributeError, ValidationError):
            raise InvalidEvent("Invalid memorybook.generate v1 contract") from None
        reset = bind_user_context(
            UserContext(None, "SYSTEM", frozenset({str(command.student_id)}), envelope.traceparent)
        )
        try:
            await self._service.generate(command)
        finally:
            reset_user_context(reset)
