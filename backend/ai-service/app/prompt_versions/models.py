"""core 활성 버전 계약과 요청이 고정해 쓰는 프롬프트 선택."""

from dataclasses import dataclass
from types import ModuleType
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

Scope = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._:/-]{0,199}$")]
PROMPT_SCOPES = {
    "judgment": "ai/judgment",
    "followup": "ai/followup",
    "analysis": "ai/analysis",
    "reportNarrative": "ai/report-narrative",
    "reportTemplate": "ai/report-template",
    "missionDraft": "ai/mission-draft",
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
