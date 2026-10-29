"""활성 프롬프트 버전 — GET /internal/versions (API 명세서 4.2).

버전은 각 기능의 prompts.py 상수. model.version.activated 수신 시 교체는 범위 밖.
"""

from fastapi import APIRouter

from app.analysis_agent import prompts as analysis_prompts
from app.followup import prompts as followup_prompts
from app.judgment import prompts as judgment_prompts
from app.report_narrative import prompts as report_narrative_prompts

router = APIRouter(prefix="/internal/versions", tags=["versions"])


def active_prompt_versions() -> dict[str, str]:
    return {
        "judgment": judgment_prompts.PROMPT_VERSION,
        "followup": followup_prompts.PROMPT_VERSION,
        "analysis": analysis_prompts.PROMPT_VERSION,
        "reportNarrative": report_narrative_prompts.PROMPT_VERSION,
    }


@router.get("")
async def versions() -> dict[str, dict[str, str]]:
    return {"prompts": active_prompt_versions()}
