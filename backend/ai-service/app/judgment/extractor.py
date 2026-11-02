"""LLM 근거 구절 추출. 판정은 하지 않음 (LLM 추출과 코드 판정 분리, FN-JDG-03)."""

from typing import Literal

from pydantic import Field

from app.judgment.models import ApiModel, JudgmentRequest
from app.llm.base import LlmClient, LlmResult
from app.versions import PromptChoice

EvidenceStatus = Literal["FOUND", "NOT_FOUND", "UNCLEAR"]


class ElementEvidence(ApiModel):
    element_id: str
    status: EvidenceStatus
    quote: str | None


class Extraction(ApiModel):
    elements: list[ElementEvidence] = Field(default_factory=list)


async def extract(
    llm: LlmClient, request: JudgmentRequest, prompt: PromptChoice
) -> LlmResult[Extraction]:
    return await llm.generate(
        system=prompt.body.SYSTEM,
        user=prompt.body.build_user(request.answer_text, request.grade, request.rubric.elements),
        output=Extraction,
        call_type="JUDGMENT",
        prompt_version=prompt.version,
    )
