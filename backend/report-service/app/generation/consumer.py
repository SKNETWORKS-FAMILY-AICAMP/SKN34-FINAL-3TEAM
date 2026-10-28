"""Handler for EventConsumer with #42's report.generate contract and SYSTEM scope."""

from typing import Any
from uuid import UUID

from app.generation.ports import ReportEventCodec
from app.generation.service import GenerationService
from app.messaging.contracts import InvalidEvent
from app.messaging.envelope import EventEnvelope
from app.security import UserContext, bind_user_context, reset_user_context

GENERATE_QUEUE = "report.report.generate"


class GenerationConsumer:
    def __init__(self, service: GenerationService, codec: ReportEventCodec) -> None:
        self._service = service
        self._codec = codec

    async def __call__(self, envelope: EventEnvelope[dict[str, Any]]) -> None:
        if envelope.type != "report.generate" or not envelope.subject:
            raise InvalidEvent("Expected report.generate with a student subject")
        command = self._codec.decode(envelope)
        if UUID(envelope.subject) != command.student_id:
            raise InvalidEvent("Envelope subject and requested student do not match")
        reset = bind_user_context(
            UserContext(
                user_id=None,
                role="SYSTEM",
                student_scope=frozenset({str(command.student_id)}),
                traceparent=envelope.traceparent,
            )
        )
        try:
            await self._service.generate(command)
        finally:
            reset_user_context(reset)
