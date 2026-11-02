"""#209 허용된 표시 설정. 공개 권한·계산식·원문을 변경하는 필드는 없다."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


def settings_for(report: dict) -> TemplateSettings:
    snapshot = (report.get("versions") or {}).get("template")
    return TemplateSettings.model_validate(snapshot["settings"]) if snapshot else TemplateSettings()


def validate_snapshot(value: dict) -> dict:
    if (
        set(value) != {"settings", "revision"}
        or type(value["revision"]) is not int
        or value["revision"] < 0
    ):
        raise ValueError("Invalid template snapshot")
    return {
        "settings": TemplateSettings.model_validate(value["settings"]).model_dump(by_alias=True),
        "revision": value["revision"],
    }
