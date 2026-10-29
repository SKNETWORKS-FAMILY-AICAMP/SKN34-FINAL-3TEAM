"""R2–R4 composition with the #119 scoped core student profile contract."""

from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID

from app.clients.ai_client import AiClient
from app.clients.learning_client import LearningClient
from app.clients.storage import ObjectStorage
from app.generation.models import GenerateReport, GenerationResult, WeeklyReport
from app.generation.narrative_generator import NarrativeGenerator
from app.generation.ports import ReportGenerator
from app.generation.record_generator import RecordGenerator
from app.generation.records import RecordContractError
from app.rendering.generator import RenderingGenerator
from app.rendering.renderer import ReportRenderer
from app.security import current_user_context


@dataclass(frozen=True)
class StudentDisplayName:
    student_id: UUID
    nickname: str


class DisplayNameProvider(Protocol):
    # Internal Python interface, NOT a proposed core HTTP response contract.
    async def lookup(self, student_id: UUID) -> StudentDisplayName: ...


class NamedGenerator:
    def __init__(self, provider: DisplayNameProvider, previous: ReportGenerator):
        self._provider, self._previous = provider, previous

    async def generate(self, command: GenerateReport, report: WeeklyReport) -> GenerationResult:
        context = current_user_context()
        if context is None or context.role != "SYSTEM":
            raise RecordContractError("Display name lookup requires a SYSTEM context")
        context.require_student(str(command.student_id))
        profile = await self._provider.lookup(command.student_id)
        if (
            profile.student_id != command.student_id
            or not isinstance(profile.nickname, str)
            or not profile.nickname.strip()
        ):
            raise RecordContractError("Display name lookup returned an invalid student/name")
        # Resolve once before privacy filtering and rendering; never trust a message nickname.
        return await self._previous.generate(
            replace(command, display_name=profile.nickname), report
        )


def build_pipeline(
    provider: DisplayNameProvider,
    learning: LearningClient,
    ai: AiClient,
    storage: ObjectStorage,
) -> ReportGenerator:
    return NamedGenerator(
        provider,
        RenderingGenerator(
            NarrativeGenerator(RecordGenerator(learning), ai, learning),
            ReportRenderer(),
            storage,
        ),
    )
