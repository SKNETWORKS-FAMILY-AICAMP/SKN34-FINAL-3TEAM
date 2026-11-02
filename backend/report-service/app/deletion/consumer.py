"""Consume the shared #45 student.deleted.v1 contract with exact student scope."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.deletion.state import DeleteStudent
from app.messaging.contracts import InvalidEvent, uuid_text
from app.security import UserContext, bind_user_context, reset_user_context

DELETION_QUEUE = "report.student.deleted"


class DeletionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    studentId: UUID
    deletionRequestId: UUID
    scope: Literal["PROFILE", "RECORDS"]

    @field_validator("studentId", "deletionRequestId", mode="before")
    @classmethod
    def uuid_field(cls, value):
        return uuid_text(value)


class StudentDeletedConsumer:
    def __init__(self, service):
        self._service = service

    async def __call__(self, envelope):
        try:
            if (envelope.type, envelope.source, envelope.dataschema) != (
                "student.deleted",
                "core-service",
                "student.deleted.v1",
            ):
                raise ValueError("Unsupported deletion identity")
            data = DeletionData.model_validate(envelope.data)
            if uuid_text(envelope.subject) != data.studentId:
                raise ValueError("Student identity mismatch")
            if envelope.time.utcoffset() is None:
                raise ValueError("Missing time offset")
            command = DeleteStudent(
                uuid_text(envelope.id),
                data.studentId,
                data.deletionRequestId,
                data.scope,
                envelope.time,
            )
        except (ValueError, TypeError, AttributeError):
            raise InvalidEvent("Invalid student.deleted v1 contract") from None
        reset = bind_user_context(
            UserContext(None, "SYSTEM", frozenset({str(command.student_id)}), envelope.traceparent)
        )
        try:
            await self._service.delete(command)
        finally:
            reset_user_context(reset)
