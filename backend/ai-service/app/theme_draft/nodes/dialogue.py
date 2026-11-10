"""generate_dialogue(요일마다 Send로 병렬). 실패한 요일만 사유를 넣어 다시(상한·마감).

끝내 실패하면 그 요일 대화는 빼고 warnings(DIALOGUE)에 남긴다(#437 기준안).
그날 증거 발견 줄(discovery)은 코드가 마지막 줄로 그대로 넣는다(단서는 미션 뒤 learning이 보여 줌).
"""

from typing import Any

from langgraph.runtime import Runtime

from app.theme_draft.checks import check_dialogue, dialogue_lines, theme_day
from app.theme_draft.models import GeneratedDialogue
from app.theme_draft.nodes import DEADLINE_REASON, THEME_CALL_TYPE, ThemeContext, ThemeState, uniq


async def generate_dialogue(payload: dict[str, Any], runtime: Runtime[ThemeContext]) -> ThemeState:
    """payload: {day, theme, draft}. 그 요일의 dialogues·dialogue_omitted를 돌려준다."""
    ctx = runtime.context
    day, theme, draft = payload["day"], payload["theme"], payload["draft"]
    feedback: list[str] = []
    bad: list[str] = []
    for attempt in range(ctx.settings.theme_max_regen + 1):
        if attempt and not ctx.can_regenerate():
            bad = [*bad, DEADLINE_REASON]
            break
        generated = await ctx.llm.generate(
            system=ctx.prompt.body.DIALOGUE_SYSTEM,
            user=ctx.prompt.body.dialogue_user(theme, day, draft, ctx.grade, feedback),
            output=GeneratedDialogue,
            call_type=THEME_CALL_TYPE,
            prompt_version=ctx.prompt.version,
            max_tokens=ctx.settings.theme_dialogue_max_tokens,
            deadline=ctx.deadline,
            timeout=ctx.settings.theme_llm_timeout,
            max_retries=ctx.settings.theme_llm_retries,
        )
        out = generated.data.model_dump()
        bad = check_dialogue(
            theme, day, out, draft, ctx.grade, ctx.settings.followup_example_overlap_chars
        )
        if not bad:
            return {
                "dialogues": {day: dialogue_lines(out, theme_day(theme, day)["discovery"])},
                "dialogue_omitted": {day: []},
            }
        feedback = uniq([*feedback, *bad])
    return {"dialogues": {day: None}, "dialogue_omitted": {day: bad}}
