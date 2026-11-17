"""retrieve(자리) → plan_theme(줄거리 생성, rulesOut은 코드가 표에서 채움) → check_theme(코드 검사).

실패하면 사유를 넣어 다시 만든다(상한·마감). 사유가 모두 칸 하나만 고치면 되는 것(글자 수·증거
발견 줄의 단서 값·후보 이름·배정과 다른 증거 종류)이면 줄거리 전체 대신 fix_theme이 그 칸만 고쳐
쓰고 다시 검사한다
(상한 theme_max_text_fix, 넘으면 줄거리 다시 생성). 줄거리를 새로 만들면 다른 칸이 새로 틀리고
한 번에 130~170초가 걸려서(실측 2026-11-11 repo-*-4).
"""

import copy

from langgraph.runtime import Runtime

from app.theme_draft.checks import (
    DAYS,
    apply_evidence_plan,
    apply_facts,
    check_theme,
    evidence_plan_problems,
    fill_rules_out,
    finalize_texts,
    fit_evidence_plan,
    fit_media,
    fix_targets,
    plan_slot,
    repair_logic,
    set_text_at,
    theme_day,
)
from app.theme_draft.families import story_type
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
    theme = fill_rules_out(generated.data.model_dump())
    # 줄거리 종류(#634): 주제가 learning 씨앗이면 코드가 주제에서 읽은 값(모델이 다른 종류를
    # 고르지 못하게), 관리자 자유 글이면 모델 값. 검사·칸 고쳐 쓰기·그림이 이 값으로 규칙을 고름
    if seeded := ctx.prompt.body.seed_story_type(ctx.request):
        theme["storyType"] = seeded
    # LLM이 쓴 종료 이야기는 마무리 장면(내부 칸 outroStory). 다섯 단서 정리는 코드가 표로 계산해
    # 앞에 붙인다(finalize_texts, #535 7차). 단서 앞 그때 시각도 코드가 붙임
    theme["outroStory"] = theme.get("outro") or ""
    # 시작 이야기 끝에 규칙 문장을 코드가 붙이는 종류(#634 ④ 시간 탐정 마을 규칙): 모델 몫은 내부 칸
    # introStory, 학생이 보는 intro는 finalize_texts가 합침
    if story_type(theme).intro_notes:
        theme["introStory"] = theme.get("intro") or ""
    # 증거 종류·기록 매체 배정(내부 칸, 응답에는 넣지 않음). 줄거리와 다르면 check_theme이
    # CLUE_EVIDENCE로 그날 칸만 고쳐 쓰게 함(#535)
    theme["evidencePlan"] = ctx.prompt.body.evidence_plan_for(ctx.request)
    # 범주가 있는 사실표 종류(소리 탐정)의 후보 범주(내부 칸, 코드가 정함 — SAME_KIND가 봄, #634 ⑤)
    if group := ctx.prompt.body.candidate_group_for(ctx.request):
        theme["candidateGroup"] = group
    targets = code_adjust(theme)
    if targets and ctx.can_regenerate():
        # 코드가 배정·조건을 고친 칸만 한 번에 고쳐 씀(LLM 1번, 바뀐 것이 있을 때만).
        # 결과는 check_theme이 봄
        apply_evidence_plan(theme)
        fixed = await ctx.llm.generate(
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
        for fix in fixed.data.fixes:
            if fix.path in targets:
                set_text_at(theme, fix.path, fix.text.strip())
    finalize_texts(theme)
    return {
        "theme": theme,
        "plan_attempts": state.get("plan_attempts", 0) + 1,
        "fix_attempts": 0,
    }


def code_adjust(theme: dict) -> dict[str, list[str]]:
    """줄거리를 만든 직후 코드가 고치는 두 가지(#535 6차 원인, 사용자 결정 2026-11-16 배정 유지·
    원인 고침).

    1. 흔적 배정을 흔적으로 남을 수 있는 특징의 날로 옮긴다(fit_evidence_plan). 옮긴 날은 그날
       단서·증거 발견 줄·수사 연결 문장을 새 종류로 고쳐 써야 함(CLUE_EVIDENCE와 같은 칸)
    2. 정답 논리(LOGIC)가 틀리면 특징 표는 두고 요일 조건만 가장 적게 바꾼다(repair_logic).
       바꾼 날은 단서 문장을 다시 씀(종료 이야기 정리는 코드가 표로 다시 붙임,
       finalize_texts). 못 맞추면 지금처럼 check_theme → 다시 생성
    고칠 칸 {경로: [사유]}를 돌려준다(바뀐 것이 없으면 빈 사전).
    """
    targets: dict[str, list[str]] = {}
    # 0. 사실표 종류(#634 동물·선물·재료): 특징 값을 사실표 값으로 맞춤. 그 특징을 쓰는 날 단서는
    #    새 값으로 고쳐 씀
    for feature in apply_facts(theme):
        fill_rules_out(theme)
        for d in theme.get("days") or []:
            cond = d.get("condition") or {}
            if cond.get("feature") == feature:
                targets.setdefault(f"{d['day']}.clue", []).append(
                    f"FACT_FIX {d['day']} 특징 '{feature}' 값을 코드가 사실표로 "
                    f"맞춤(허용 값 "
                    f"{cond.get('allowed')}): 단서 문장을 새 값에 맞게"
                )
    # 흔적 배정 옮기기 뒤 기록 매체를 그날 특징에 맞춤(#634 ⑤: 소리는 사진으로 알 수 없음)
    for day in dict.fromkeys([*fit_evidence_plan(theme), *fit_media(theme)]):
        slot = plan_slot(theme, day)
        for reason in evidence_plan_problems(theme_day(theme, day), slot or {}):
            path = f"{day}.{reason.split(' ')[2]}"
            if reason not in targets.get(path, []):
                targets.setdefault(path, []).append(reason)
    changed = repair_logic(theme)
    for day in changed:
        cond = theme_day(theme, day).get("condition") or {}
        targets.setdefault(f"{day}.clue", []).append(
            f"LOGIC_FIX {day} 정답 논리를 맞추려고 코드가 단서 조건을 바꿈({cond.get('kind')}, "
            f"허용 값 {cond.get('allowed')}): 단서 문장을 새 조건에 맞게"
        )
    return targets


async def fix_theme(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    """검사에 걸린 칸만 고쳐 쓴다. 받은 경로가 아닌 칸은 무시하고 결과는 check_theme이 다시
    본다."""
    ctx = runtime.context
    targets = state.get("fix_targets") or {}
    theme = copy.deepcopy(state["theme"])
    assert theme is not None
    # 배정과 다른 증거 종류는 코드가 배정대로 바꾸고 그날 글 칸만 그 종류에 맞게 고쳐 씀(#535)
    apply_evidence_plan(theme)
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
    finalize_texts(theme)
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
    finalize_texts(theme)
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
