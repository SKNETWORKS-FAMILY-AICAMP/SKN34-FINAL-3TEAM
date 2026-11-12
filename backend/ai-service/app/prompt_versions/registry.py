"""이미지에 포함된 프롬프트 본문과 이름별 활성 revision 상태."""

import logging
from types import ModuleType
from typing import Mapping

from app.analysis_agent import prompts as analysis_prompts
from app.analysis_agent import template_prompts
from app.errors import ApiError
from app.followup import prompts as followup_prompts
from app.judgment import prompts as judgment_prompts
from app.mission_draft import prompts as mission_draft_prompts
from app.prompt_versions.models import PROMPT_SCOPES, ActiveVersionItem, PromptChoice, tracked
from app.report_explanation import prompts as report_explanation_prompts
from app.report_narrative import prompts as report_narrative_prompts
from app.theme_draft import prompts as theme_draft_prompts

logger = logging.getLogger(__name__)

BUILTIN_PROMPTS: dict[str, ModuleType] = {
    "judgment": judgment_prompts,
    "followup": followup_prompts,
    "analysis": analysis_prompts,
    "reportNarrative": report_narrative_prompts,
    "reportTemplate": template_prompts,
    "missionDraft": mission_draft_prompts,
    "reportExplanation": report_explanation_prompts,
    "themeDraft": theme_draft_prompts,
}


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
            if not tracked(item):
                continue
            if item.name in active:
                raise ValueError("duplicate active version")
            active[item.name] = item
        self._active = active

    def apply(self, item: ActiveVersionItem) -> None:
        if not tracked(item):
            return
        previous = self._active.get(item.name)
        if previous is not None:
            if item.revision < previous.revision:
                return
            if item.revision == previous.revision:
                if item != previous:
                    logger.warning("Conflicting activation revision ignored name=%s", item.name)
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

    def model(self, name: str, scope: str) -> ActiveVersionItem | None:
        """활성 MODEL 중 그 scope가 승인된 것. 없으면 None (설명 모델 #477)"""
        item = self._active.get(name)
        if item is None or item.kind != "MODEL" or scope not in item.scopes:
            return None
        return item

    def is_ready(self) -> bool:
        try:
            for name in PROMPT_SCOPES:
                self.prompt(name)
        except ApiError:
            return False
        return True

    def active_prompt_versions(self) -> dict[str, str]:
        return {name: self.prompt(name).version for name in PROMPT_SCOPES}
