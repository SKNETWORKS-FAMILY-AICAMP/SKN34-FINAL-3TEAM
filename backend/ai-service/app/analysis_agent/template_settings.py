"""#209 허용된 표시 설정. 공개 권한·계산식·원문을 변경하는 필드는 없다."""

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.errors import ApiError
from app.llm.base import LlmClient, LlmUnavailable
from app.prompt_versions.models import PromptChoice

SECTIONS = ("thinkingTypes", "changes", "reflections", "quotes", "narrative", "eveningQuestion")
METRICS = {
    "ATTEMPTS": "답변 제출 시도 수",
    "COMPLETED": "완료한 시도 수",
    "UNASSISTED": "도움 없이 시작한 비율",
}


class TemplateSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)
    section_order: list[str] = Field(default_factory=lambda: list(SECTIONS), alias="sectionOrder")
    highlight_metrics: list[Literal["ATTEMPTS", "COMPLETED", "UNASSISTED"]] = Field(
        default_factory=list, alias="highlightMetrics"
    )
    tone: Literal["DEFAULT", "EASY", "CONCISE"] = "DEFAULT"

    @model_validator(mode="after")
    def validate_selection(self):
        if len(self.section_order) != len(SECTIONS) or set(self.section_order) != set(SECTIONS):
            raise ValueError("섹션은 빠짐없이 한 번씩 포함해야 합니다")
        if len(set(self.highlight_metrics)) != len(self.highlight_metrics):
            raise ValueError("강조 지표는 중복할 수 없습니다")
        return self


class TemplateProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)
    current: TemplateSettings


class TemplateProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    settings: TemplateSettings | None = None
    clarification: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def one_result(self):
        if (self.settings is None) == (self.clarification is None):
            raise ValueError("변경안 또는 확인 질문 하나만 필요합니다")
        if self.clarification is not None and not self.clarification.strip():
            raise ValueError("빈 확인 질문은 허용하지 않습니다")
        return self


async def propose_template(
    body: TemplateProposalRequest, llm: LlmClient, prompt: PromptChoice
) -> TemplateProposal:
    """prompt는 호출자가 요청 시작 때 고른 본문·버전(#280)."""
    try:
        result = await llm.generate(
            system=prompt.body.SYSTEM,
            user=prompt.body.build_user(body),
            output=TemplateProposal,
            call_type="ANALYSIS",
            prompt_version=prompt.version,
            max_tokens=1000,
            deadline=time.monotonic() + 20,
        )
        return result.data
    except LlmUnavailable as exc:
        raise ApiError(
            503, "AI_UNAVAILABLE", "설정 변경안을 만들지 못했습니다.", retryable=exc.retryable
        ) from exc
