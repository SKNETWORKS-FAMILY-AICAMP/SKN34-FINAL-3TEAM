"""core #43 snapshot/event의 scoring 대상 계약."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

Scope = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._:/-]{0,199}$")]


class ActiveModelVersion(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: UUID
    kind: Literal["MODEL"]
    name: str = Field(pattern=r"^(m2|m1)-.+$")
    version: str = Field(min_length=1)
    ref_id: None = Field(alias="refId")
    artifact_uri: str = Field(alias="artifactUri", min_length=1)
    scopes: tuple[Scope, ...] = Field(min_length=1, max_length=100)
    revision: int = Field(strict=True, ge=1)
    activated_at: AwareDatetime = Field(alias="activatedAt")

    @field_validator("scopes")
    @classmethod
    def unique_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate scopes")
        return value


def scoring_versions(payload: object) -> list[ActiveModelVersion]:
    """다른 서비스의 PROMPT/RUBRIC 등은 모델 로더로 전달하지 않는다."""
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("invalid active snapshot")
    versions = []
    names = set()
    for item in payload["items"]:
        if not isinstance(item, dict):
            raise ValueError("invalid snapshot item")
        name = item.get("name")
        if (
            item.get("kind") not in {"MODEL", "PROMPT", "RUBRIC", "GENERATION"}
            or not isinstance(name, str)
            or not name
        ):
            raise ValueError("invalid snapshot identity")
        if item.get("kind") != "MODEL":
            continue
        if not name.startswith(("m2-", "m1-")):
            continue
        version = ActiveModelVersion.model_validate(item)
        if name in names:
            raise ValueError("duplicate active model")
        names.add(name)
        versions.append(version)
    return versions
