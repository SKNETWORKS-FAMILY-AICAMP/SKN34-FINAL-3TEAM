"""retrieve(자리) → plan_theme(줄거리 생성) → check_theme(코드 검사).

실패하면 사유를 넣어 다시 만든다(상한·마감).
"""

from langgraph.runtime import Runtime

from app.theme_draft.checks import DAYS, check_theme
from app.theme_draft.models import GeneratedTheme
from app.theme_draft.nodes import DEADLINE_REASON, THEME_CALL_TYPE, ThemeContext, ThemeState


async def retrieve(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    """지식 검색 자리(#470). 기능 스위치가 꺼져 있으면 요청의 성취기준으로 지금 틀대로 동작한다."""
    if runtime.context.settings.theme_knowledge_enabled:
        # #470에서 주제 → 유형별 성취기준 후보·근거 조각 검색을 붙인다. 그 전에는 켜도 동작이 같다.
        pass
    return {}


async def plan_theme(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    ctx = runtime.context
    generated = await ctx.llm.generate(
        system=ctx.prompt.body.PLAN_SYSTEM,
        user=ctx.prompt.body.plan_user(ctx.request, state.get("plan_feedback") or []),
        output=GeneratedTheme,
        call_type=THEME_CALL_TYPE,
        prompt_version=ctx.prompt.version,
        max_tokens=ctx.settings.theme_plan_max_tokens,
        deadline=ctx.deadline,
        timeout=ctx.settings.theme_llm_timeout,
        max_retries=ctx.settings.theme_llm_retries,
    )
    return {
        "theme": generated.data.model_dump(),
        "plan_attempts": state.get("plan_attempts", 0) + 1,
    }


async def check_theme_node(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    ctx = runtime.context
    codes = {s.code for m in ctx.request.missions for s in m.standards}
    bad = check_theme(state["theme"], ctx.grade, codes)
    if not bad:
        # 줄거리가 새로 정해지면 미션·대화는 다섯 요일 모두 새로
        return {"plan_bad": [], "days_todo": list(DAYS), "mission_seed": {}}
    out: ThemeState = {
        "plan_bad": bad,
        "plan_feedback": [*(state.get("plan_feedback") or []), ("THEME", bad)],
    }
    attempts = state.get("plan_attempts", 0)
    if attempts > ctx.settings.theme_max_regen:
        out["failure"] = {"stage": "THEME", "reasons": bad}
        out["theme"] = None
    elif not ctx.can_regenerate():
        out["failure"] = {"stage": "THEME", "reasons": [*bad, DEADLINE_REASON]}
        out["theme"] = None
    return out
