"""Core의 활성 PROMPT revision과 이미지에 포함된 실제 프롬프트 본문."""

import logging
from dataclasses import dataclass
from types import ModuleType
from typing import Annotated, Literal, Mapping
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.analysis_agent import prompts as analysis_prompts
from app.errors import ApiError
from app.followup import prompts as followup_prompts
from app.judgment import prompts as judgment_prompts
from app.report_narrative import prompts as report_narrative_prompts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/versions", tags=["versions"])

Scope = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._:/-]{0,199}$")]
PROMPT_SCOPES = {
    "judgment": "ai/judgment",
    "followup": "ai/followup",
    "analysis": "ai/analysis",
    "reportNarrative": "ai/report-narrative",
}
BUILTIN_PROMPTS: dict[str, ModuleType] = {
    "judgment": judgment_prompts,
    "followup": followup_prompts,
    "analysis": analysis_prompts,
    "reportNarrative": report_narrative_prompts,
}


class ActiveVersionItem(BaseModel):
    """core snapshot과 이벤트가 공유하는 확정 필드."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: UUID
    kind: Literal["RUBRIC", "MODEL", "PROMPT", "GENERATION"]
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    ref_id: UUID | None = Field(alias="refId")
    artifact_uri: str | None = Field(alias="artifactUri")
    scopes: tuple[Scope, ...] = Field(min_length=1, max_length=100)
    revision: int = Field(strict=True, ge=1)
    activated_at: AwareDatetime = Field(alias="activatedAt")

    @field_validator("scopes")
    @classmethod
    def unique_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate scopes")
        return value


class ActiveSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ActiveVersionItem]


@dataclass(frozen=True)
class PromptChoice:
    version: str
    body: ModuleType


class ActiveVersions:
    """요청은 PromptChoice 참조를 한 번 잡아 본문과 버전을 함께 고정한다."""

    def __init__(self, installed: Mapping[str, Mapping[str, ModuleType]] | None = None) -> None:
        self._installed = (
            {name: {module.PROMPT_VERSION: module} for name, module in BUILTIN_PROMPTS.items()}
            if installed is None
            else installed
        )
        self._builtin = {
            name: PromptChoice(module.PROMPT_VERSION, module)
            for name, module in BUILTIN_PROMPTS.items()
        }
        self._active: dict[str, ActiveVersionItem] = {}

    def replace(self, items: list[ActiveVersionItem]) -> None:
        """전체 snapshot 교체. 이벤트는 apply로 이름 한 개만 교체한다."""
        active: dict[str, ActiveVersionItem] = {}
        for item in items:
            if item.kind != "PROMPT" or item.name not in PROMPT_SCOPES:
                continue
            if item.name in active:
                raise ValueError("duplicate active prompt")
            active[item.name] = item
        self._active = active

    def apply(self, item: ActiveVersionItem) -> None:
        if item.kind != "PROMPT" or item.name not in PROMPT_SCOPES:
            return
        previous = self._active.get(item.name)
        if previous is not None:
            if item.revision < previous.revision:
                return
            if item.revision == previous.revision:
                if item != previous:
                    logger.warning(
                        "Conflicting prompt activation revision ignored name=%s", item.name
                    )
                return
        self._active[item.name] = item

    def prompt(self, name: str) -> PromptChoice:
        if name not in PROMPT_SCOPES:
            raise KeyError(name)
        item = self._active.get(name)
        if item is None or PROMPT_SCOPES[name] not in item.scopes:
            return self._builtin[name]
        body = self._installed.get(name, {}).get(item.version)
        if body is None:
            raise ApiError(
                503,
                "AI_PROMPT_VERSION_UNAVAILABLE",
                "활성 프롬프트 버전을 사용할 수 없습니다.",
                retryable=True,
            )
        return PromptChoice(item.version, body)

    def is_ready(self) -> bool:
        try:
            for name in PROMPT_SCOPES:
                self.prompt(name)
        except ApiError:
            return False
        return True

    def active_prompt_versions(self) -> dict[str, str]:
        return {name: self.prompt(name).version for name in PROMPT_SCOPES}


@router.get("")
async def versions(request: Request) -> dict[str, dict[str, str]]:
    return {"prompts": request.app.state.active_versions.active_prompt_versions()}
