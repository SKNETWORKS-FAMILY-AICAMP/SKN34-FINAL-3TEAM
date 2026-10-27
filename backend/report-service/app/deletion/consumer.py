"""Known student.deleted fields from architecture 1.4; shared schema remains #45-owned."""

from uuid import UUID

from app.deletion.state import DeleteStudent
from app.security import UserContext, bind_user_context, reset_user_context

DELETION_QUEUE = "report.student.deleted"


class StudentDeletedConsumer:
    def __init__(self, service):
        self._service = service

    async def __call__(self, envelope):
        if envelope.type != "student.deleted" or envelope.dataschema != "student.deleted.v1":
            raise ValueError("Unsupported student deletion contract")
        if (
            not envelope.subject
            or "deletionRequestId" not in envelope.data
            or "scope" not in envelope.data
        ):
            raise ValueError("Student deletion fields are missing")
        command = DeleteStudent(
            UUID(envelope.id),
            UUID(envelope.subject),
            UUID(envelope.data["deletionRequestId"]),
            envelope.data["scope"],
            envelope.time,
        )
        reset = bind_user_context(
            UserContext(None, "SYSTEM", frozenset({str(command.student_id)}), envelope.traceparent)
        )
        try:
            await self._service.delete(command)
        finally:
            reset_user_context(reset)
