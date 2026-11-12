"""retrieve(자리) → plan_theme(줄거리 생성, rulesOut은 코드가 표에서 채움) → check_theme(코드 검사).

실패하면 사유를 넣어 다시 만든다(상한·마감). 사유가 모두 칸 하나만 고치면 되는 것(글자 수·증거
발견 줄의 단서 값·후보 이름)이면 줄거리 전체 대신 fix_theme이 그 칸만 고쳐 쓰고 다시 검사한다
(상한 theme_max_text_fix, 넘으면 줄거리 다시 생성). 줄거리를 새로 만들면 다른 칸이 새로 틀리고
한 번에 130~170초가 걸려서(실측 2026-11-11 repo-*-4).
"""

import copy

from langgraph.runtime import Runtime

from app.theme_draft.checks import DAYS, check_theme, fill_rules_out, fix_targets, set_text_at
from app.theme_draft.models import GeneratedFixes, GeneratedTheme
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
        "theme": fill_rules_out(generated.data.model_dump()),
        "plan_attempts": state.get("plan_attempts", 0) + 1,
        "fix_attempts": 0,
    }


async def fix_theme(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    """검사에 걸린 칸만 고쳐 쓴다. 받은 경로가 아닌 칸은 무시하고 결과는 check_theme이 다시
    본다."""
    ctx = runtime.context
    targets = state.get("fix_targets") or {}
    theme = copy.deepcopy(state["theme"])
    assert theme is not None
    generated = await ctx.llm.generate(
        system=ctx.prompt.body.FIX_SYSTEM,
        user=ctx.prompt.body.fix_user(theme, targets),
        output=GeneratedFixes,
        call_type=THEME_CALL_TYPE,
        prompt_version=ctx.prompt.version,
        max_tokens=ctx.settings.theme_dialogue_max_tokens,
        deadline=ctx.deadline,
        timeout=ctx.settings.theme_llm_timeout,
        max_retries=ctx.settings.theme_llm_retries,
    )
    for fix in generated.data.fixes:
        if fix.path in targets:
            set_text_at(theme, fix.path, fix.text.strip())
    return {
        "theme": theme,
        "fix_attempts": state.get("fix_attempts", 0) + 1,
        "fix_targets": {},
    }


async def fix_clues(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    """글 검토 CLUE_LOGIC(처음 한 번): 지목된 요일 단서 문장만 고쳐 쓰고 코드 검사를 다시 한다.

    단서는 학생이 그날 미션을 마친 뒤 보는 글이라 미션·대화에 들어가지 않아, 단서만 바꿔도 미션·
    대화는 그대로 둔다. 고친 단서가 코드 검사에 걸리면 줄거리부터 다시 만든다.
    """
    ctx = runtime.context
    targets = state.get("fix_targets") or {}
    theme = copy.deepcopy(state["theme"])
    assert theme is not None
    generated = await ctx.llm.generate(
        system=ctx.prompt.body.FIX_SYSTEM,
        user=ctx.prompt.body.fix_user(theme, targets),
        output=GeneratedFixes,
        call_type=THEME_CALL_TYPE,
        prompt_version=ctx.prompt.version,
        max_tokens=ctx.settings.theme_dialogue_max_tokens,
        deadline=ctx.deadline,
        timeout=ctx.settings.theme_llm_timeout,
        max_retries=ctx.settings.theme_llm_retries,
    )
    for fix in generated.data.fixes:
        if fix.path in targets:
            set_text_at(theme, fix.path, fix.text.strip())
    codes = {s.code for m in ctx.request.missions for s in m.standards}
    bad = check_theme(theme, ctx.grade, codes)
    out: ThemeState = {"fix_targets": {}, "clue_fixed": True}
    if bad:
        reasons = state.get("review_reasons") or []
        feedback = [*(state.get("plan_feedback") or []), ("REVIEW", reasons), ("THEME", bad)]
        return {**out, "plan_feedback": feedback, "plan_attempts": 0, "review_route": "PLAN"}
    return {**out, "theme": theme, "review_route": "REVIEW"}


def after_fix_clues(state: ThemeState) -> str:
    return "plan_theme" if state.get("review_route") == "PLAN" else "review_story"


async def check_theme_node(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    ctx = runtime.context
    codes = {s.code for m in ctx.request.missions for s in m.standards}
    bad = check_theme(state["theme"], ctx.grade, codes)
    if not bad:
        # 줄거리가 새로 정해지면 미션·대화는 다섯 요일 모두 새로
        return {"plan_bad": [], "days_todo": list(DAYS), "mission_seed": {}}
    targets = fix_targets(bad)
    if (
        targets
        and state.get("fix_attempts", 0) < ctx.settings.theme_max_text_fix
        and ctx.can_regenerate()
    ):
        return {"plan_bad": bad, "fix_targets": targets}
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
