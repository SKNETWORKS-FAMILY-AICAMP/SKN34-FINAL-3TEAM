"""retrieve(자리) → plan_theme(줄거리 생성, rulesOut은 코드가 표에서 채움) → check_theme(코드 검사).

실패하면 사유를 넣어 다시 만든다(상한·마감). 사유가 모두 칸 하나만 고치면 되는 것(글자 수·증거
발견 줄의 단서 값·후보 이름·배정과 다른 증거 종류)이면 줄거리 전체 대신 fix_theme이 그 칸만 고쳐
쓰고 다시 검사한다
(상한 theme_max_text_fix, 넘으면 줄거리 다시 생성). 줄거리를 새로 만들면 다른 칸이 새로 틀리고
한 번에 130~170초가 걸려서(실측 2026-11-11 repo-*-4).
"""

import asyncio
import copy

from langgraph.runtime import Runtime

from app.llm.base import LlmError, LlmUnavailable
from app.theme_draft.checks import (
    DAYS,
    apply_evidence_plan,
    apply_facts,
    check_theme,
    clue_template,
    day_step_text,
    evidence_plan_problems,
    fill_rules_out,
    finalize_texts,
    fit_evidence_plan,
    fit_media,
    fix_targets,
    is_story,
    normalize_sound_target,
    plan_slot,
    refit_ways,
    repair_hints,
    repair_logic,
    set_text_at,
    theme_day,
)
from app.theme_draft.families import story_type
from app.theme_draft.models import GeneratedFixes, GeneratedTheme
from app.theme_draft.nodes import DEADLINE_REASON, THEME_CALL_TYPE, ThemeContext, ThemeState
from app.theme_draft.nodes.dialogue import promise_redo


async def retrieve(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    """지식 검색 자리(#470). 기능 스위치가 꺼져 있으면 요청의 성취기준으로 지금 틀대로 동작한다."""
    if runtime.context.settings.theme_knowledge_enabled:
        # #470에서 주제 → 유형별 성취기준 후보·근거 조각 검색을 붙인다. 그 전에는 켜도 동작이 같다.
        pass
    return {}


# #782 설계 v9: 줄거리를 다시 만들 때 모델이 요일만 내고 위 칸을 비우면 REQUIRED로 끝남(6차 way4b
# 마지막 다시 생성 'REQUIRED title·world·styleNote·outfit·intro·outro'). 앞 판 값으로 채운다 —
# 시작·종료 이야기는 찾는 대상과 등장인물이 같을 때만(이야기 속 사람·대상이 맞아야 함)
KEEP_ALWAYS = ("title", "world", "styleNote", "outfit")
KEEP_SAME_CAST = ("intro", "outro", "bigQuestion")


def keep_filled(theme: dict, previous: dict | None) -> list[str]:
    """새 줄거리에서 빈 위 칸을 앞 판 값으로 채우고 채운 칸 이름을 돌려준다."""
    if not previous:
        return []

    def cast(t: dict) -> tuple:
        names = tuple(sorted(str(c.get("name") or "") for c in t.get("characters") or []))
        return str(t.get("target") or ""), names

    # 앞 판의 보는 시작·종료 이야기는 코드가 규칙 문장·단서 정리를 붙인 글이라 모델 몫(내부 칸)으로
    source = {"intro": "introStory", "outro": "outroStory"}
    keys = KEEP_ALWAYS + (KEEP_SAME_CAST if cast(theme) == cast(previous) else ())
    filled = []
    for k in keys:
        old = str(previous.get(source.get(k, k)) or previous.get(k) or "").strip()
        if not str(theme.get(k) or "").strip() and old:
            theme[k] = old
            filled.append(k)
    return filled


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
    keep_filled(theme, state.get("theme"))
    # 줄거리 종류(#634): 주제가 learning 씨앗이면 코드가 주제에서 읽은 값(모델이 다른 종류를
    # 고르지 못하게), 관리자 자유 글이면 모델 값. 검사·칸 고쳐 쓰기·그림이 이 값으로 규칙을 고름
    if seeded := ctx.prompt.body.seed_story_type(ctx.request):
        theme["storyType"] = seeded
    # 갈래(#782 기준안 — 확인 전): 주제 글에 갈래가 있으면 그 값(목록 밖이면 None), 소리 탐정은
    # 코드가 고른 후보 범주, 없으면 모델 값(덮어쓴 종류의 목록 밖이면 None)
    theme["branch"] = ctx.prompt.body.branch_for(ctx.request, theme)
    # #782 설계 v4: 소리 탐정 대상 글의 '밤마다'를 '밤에'로(관리자 자유 글·예전 씨앗)
    normalize_sound_target(theme)
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
    # #782 설계 v3: 요일 성취기준 코드와 국어 부탁 날 돕는 사람 호칭 후보·아이 답의 쓰임(내부 칸,
    # HELPER_SAME·USE_MISSING·그래프 성취기준 규칙이 봄)
    theme["dayFrames"] = ctx.prompt.body.day_frames_for(ctx.request)
    # 사실표 종류의 후보 4개·정답(내부 칸, 코드가 정함 — SAME_KIND가 봄, #634 ⑤ 소리 탐정에서
    # #782 사실표 종류 전부로)
    if plan := ctx.prompt.body.candidate_plan_for(ctx.request):
        theme["candidatePlan"] = plan
    # 미션 방식(#782 테마 짜임, 코드가 줄거리 전에 정해 plan_user로 알린 값을 내부 칸에 넣음)
    ways = ctx.prompt.body.mission_ways_for(ctx.request)
    for d in theme.get("days") or []:
        d["missionWay"] = ways.get(d.get("day") or "", "ASK")
    if tuple(d.get("day") for d in theme.get("days") or []) != DAYS:
        # 요일을 다 내지 않은 줄거리(#782 작은 생성: 조건을 맞출 수 없으면 모델이 빈 줄거리를 냄)는
        # 코드 수리가 없는 요일을 찾다 멈추므로 건너뛰고 check_theme(DAYS)이 다시 생성하게 함
        return {
            "theme": theme,
            "plan_attempts": state.get("plan_attempts", 0) + 1,
            "fix_attempts": 0,
        }
    targets = code_adjust(theme)
    if targets and ctx.can_regenerate():
        # 코드가 배정·조건을 고친 칸만 고쳐 씀(요일마다 LLM 1번, 바뀐 것이 있을 때만).
        # 결과는 check_theme이 봄
        apply_evidence_plan(theme)
        await fix_fields(ctx, theme, targets)
    finalize_texts(theme)
    return {
        "theme": theme,
        "plan_attempts": state.get("plan_attempts", 0) + 1,
        "fix_attempts": 0,
    }


async def fix_fields(ctx: ThemeContext, theme: dict, targets: dict[str, list[str]]) -> None:
    """칸 고쳐 쓰기(fix_user)를 요일마다 따로(동시에) 불러 받은 경로만 theme에 넣는다.

    #782 실측 r782-ways-rd4: 한 호출에 목요일 지문과 금요일 수사 연결 문장을 함께 고치다 금요일
    문장에 목요일 '삼각형 카드'가 섞임. 요일 밖 칸(제목·시작 이야기·콘티 등)은 한 묶음.
    """
    groups: dict[str, dict[str, list[str]]] = {}
    for path, reasons in targets.items():
        head = path.split(".")[0]
        groups.setdefault(head if head in DAYS else "THEME", {})[path] = reasons

    async def fix_group(part: dict[str, list[str]]) -> list[tuple[str, str]]:
        generated = await ctx.llm.generate(
            system=ctx.prompt.body.FIX_SYSTEM,
            user=ctx.prompt.body.fix_user(theme, part),
            output=GeneratedFixes,
            call_type=THEME_CALL_TYPE,
            prompt_version=ctx.prompt.version,
            max_tokens=ctx.settings.theme_dialogue_max_tokens,
            deadline=ctx.deadline,
            timeout=ctx.settings.theme_llm_timeout,
            max_retries=ctx.settings.theme_llm_retries,
        )
        return [(f.path, f.text.strip()) for f in generated.data.fixes if f.path in part]

    parts = list(groups.values())
    for done in await asyncio.gather(*(fix_group(part) for part in parts)):
        for path, text in done:
            set_text_at(theme, path, text)


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
    moved = fit_evidence_plan(theme)
    # #782 미션 방식: 옮긴 뒤 방식과 증거가 안 맞게 된 날은 부탁으로 바꾸고, 그날 할 일·지문도
    # 부탁(돕는 사람의 일)에 맞게 고쳐 씀(단서·증거 발견 줄은 아래 CLUE_EVIDENCE가 고침)
    for day in refit_ways(theme):
        for key in ("missionHook", "missionMaterial"):
            targets.setdefault(f"{day}.{key}", []).append(
                f"WAY_FIX {day} 증거 종류가 바뀌어 코드가 미션 방식을 부탁으로 바꿈: 돕는 사람의 "
                "부탁 한 줄·그 일의 자료로"
            )
    for day in dict.fromkeys([*moved, *fit_media(theme)]):
        slot = plan_slot(theme, day)
        for reason in evidence_plan_problems(theme_day(theme, day), slot or {}):
            path = f"{day}.{reason.split(' ')[2]}"
            if reason not in targets.get(path, []):
                targets.setdefault(path, []).append(reason)
    changed = repair_logic(theme)
    for day in changed:
        cond = theme_day(theme, day).get("condition") or {}
        targets.setdefault(f"{day}.clue", []).append(
            f"LOGIC_FIX {day} 정답 논리를 맞추려고 코드가 단서를 사건 단서로 바꿈: 단서 문장을 "
            "사건이 어떻게 벌어졌는지로(후보 이름·특징 값 없이)"
            if is_story(cond)
            else f"LOGIC_FIX {day} 정답 논리를 맞추려고 코드가 단서 조건을 바꿈("
            f"{cond.get('kind')}, 허용 값 {cond.get('allowed')}): 단서 문장을 새 조건에 맞게"
        )
    # 3. 정보 없는 힌트 단서(특징 값 전부)·앞 요일과 같은 힌트를 남은 후보 값으로 좁히거나 다른
    #    특징으로, 둘 다 안 되면 사건 단서로 바꾼다(#782 테마 짜임). 특징을 바꾼 기록 날은 매체도
    #    다시 맞춤
    hinted = repair_hints(theme)
    for day in hinted:
        cond = theme_day(theme, day).get("condition") or {}
        why = f"HINT_FIX {day} 힌트 단서가 새로 알려 주는 것이 없어(특징 값 전부이거나 앞 요일과 "
        targets.setdefault(f"{day}.clue", []).append(
            why + "같은 단서) 코드가 사건 단서로 바꿈: 단서 문장을 사건이 어떻게 벌어졌는지로"
            "(후보 이름·특징 값 없이, 앞 요일 단서를 되풀이하지 않음)"
            if is_story(cond)
            else why + "같은 단서) 코드가 조건을 바꿈(특징 "
            f"'{cond.get('feature')}', 허용 값 {cond.get('allowed')}): 단서 문장을 새 조건에 맞게"
            "(조건에 없는 값 낱말은 쓰지 않음)"
        )
    for day in fit_media(theme) if hinted else []:
        for reason in evidence_plan_problems(theme_day(theme, day), plan_slot(theme, day) or {}):
            path = f"{day}.{reason.split(' ')[2]}"
            if reason not in targets.get(path, []):
                targets.setdefault(path, []).append(reason)
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
    # #782 설계 v3(사용자 결정 2026-11-21): 부탁 날 단서의 출처·꼴(CLUE_SOURCE·CLUE_TEXT)이 한 번
    # 고쳐 쓴 뒤에도 걸리면 코드 틀 문장으로 바꾼다(같은 칸을 모델에게 세 번 맡기지 않음)
    if state.get("fix_attempts", 0) >= 1:
        for path in [p for p, rs in targets.items() if p.endswith(".clue")]:
            if any(
                r.startswith(("CLUE_SOURCE", "CLUE_TEXT", "KEPT_TRACE")) for r in targets[path]
            ) and (text := clue_template(theme, theme_day(theme, path.split(".")[0]))):
                set_text_at(theme, path, text)
                targets = {k: v for k, v in targets.items() if k != path}
        # #782 설계 v7: 오늘 온 까닭이 두 번째에도 걸리면(지어냄·자기 이름·단서 미리 등 어떤 사유든)
        # 코드 문장 — 코드 문장은 그 검사들을 모두 통과함(시험)
        for path in [p for p in targets if p.endswith(".dayStep")]:
            day = path.split(".")[0]
            index = [d.get("day") for d in theme.get("days") or []].index(day)
            set_text_at(theme, path, day_step_text(theme, index))
            targets = {k: v for k, v in targets.items() if k != path}
    await fix_fields(ctx, theme, targets)
    finalize_texts(theme)
    return {
        "theme": theme,
        "fix_attempts": state.get("fix_attempts", 0) + 1,
        "fix_targets": {},
    }


async def fix_clues(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    """글 검토 CLUE_LOGIC(처음 한 번): 지목된 요일 단서 문장만 고쳐 쓰고 코드 검사를 다시 한다.

    단서는 학생이 그날 미션을 마친 뒤 보는 글이라 미션·대화에 들어가지 않아, 단서만 바꿔도 미션·
    대화는 그대로 둔다(#782 설계 v12: 약속 감각이 바뀐 날의 약속이 틀리면 그 요일 대화만 다시,
    talk_seed). 고친 단서가 코드 검사에 걸리면 줄거리부터 다시 만든다.
    """
    ctx = runtime.context
    targets = state.get("fix_targets") or {}
    theme = copy.deepcopy(state["theme"])
    assert theme is not None
    await fix_fields(ctx, theme, targets)
    finalize_texts(theme)
    codes = {s.code for m in ctx.request.missions for s in m.standards}
    bad = check_theme(theme, ctx.grade, codes)
    # #782 설계 v4(B1): 고쳐 쓴 단서가 출처·꼴 검사(CLUE_SOURCE·CLUE_TEXT)에만 걸리면 코드 틀 문장
    # 으로 바꾸고 다시 본다(3차 측정 auto4b·new4b: 이 길에 틀 문장이 없어 줄거리를 다시 만들다 마감)
    if bad and all(r.startswith(("CLUE_SOURCE", "CLUE_TEXT", "KEPT_TRACE")) for r in bad):
        for day in dict.fromkeys(r.split(" ")[1] for r in bad):
            if text := clue_template(theme, theme_day(theme, day)):
                set_text_at(theme, f"{day}.clue", text)
        finalize_texts(theme)
        bad = check_theme(theme, ctx.grade, codes)
    out: ThemeState = {"fix_targets": {}, "clue_fixed": True}
    if bad:
        reasons = state.get("review_reasons") or []
        feedback = [*(state.get("plan_feedback") or []), ("REVIEW", reasons), ("THEME", bad)]
        return {**out, "plan_feedback": feedback, "plan_attempts": 0, "review_route": "PLAN"}
    # #782 설계 v10: 고친 단서로 그날 약속 감각이 바뀌면 그날 약속을 다시 봄. #782 설계 v12: 틀리면
    # 그 요일 대화만 LLM이 다시 씀(graph after_fix_clues → generate_dialogue → review_story)
    talk = promise_redo(ctx, state, theme)
    return {**out, "talk_seed": talk, "talk_keep": False, "theme": theme, "review_route": "REVIEW"}


async def fix_old_names(ctx: ThemeContext, fixed: dict, before: dict, days: list[str]) -> None:
    """돕는 사람을 바꾼 요일의 다음 날 오늘 온 까닭에 옛 호칭이 남으면 그 칸을 고쳐 씀(#782 설계 v10
    돕는 사람 검토 길에서 쓰던 것을 v13 fix_helpers에 다시 씀 — HELPER_SAME은 돕는 사람을 바꾸라고
    할 때만 다음 날 옛 호칭을 봄)."""
    order = [d.get("day") for d in fixed.get("days") or []]
    targets: dict[str, list[str]] = {}
    for day in days:
        old = str(theme_day(before, day).get("helper") or "").strip()
        new = str(theme_day(fixed, day).get("helper") or "").strip()
        if not old or old == new or day not in order or order.index(day) + 1 >= len(order):
            continue
        nxt = order[order.index(day) + 1]
        if old in str(theme_day(fixed, nxt).get("dayStep") or ""):
            targets[f"{nxt}.dayStep"] = [
                f"HELPER_SAME {nxt} dayStep에 바뀌기 전 돕는 사람('{old}'): 어제 돕는 사람은 "
                f"'{new}'로 바뀜 — 옛 호칭을 쓰지 않음"
            ]
    if targets and ctx.can_regenerate():
        await fix_fields(ctx, fixed, targets)


async def fix_helpers(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    """글 검토 HELPER_FIT(#782 설계 v13): 지목된 부탁 날의 돕는 사람·일 칸만 고쳐 쓰고 코드 검사를
    다시 한 뒤 그 요일 미션·대화부터 다시 만든다(줄거리 나머지는 그대로, days_todo·mission_seed는
    글 검토가 정함). 고친 칸이 칸 하나로 고칠 수 있는 검사에 걸리면 한 번 더 고쳐 쓰고, 그래도
    걸리면 줄거리부터 다시 만든다.

    10~13차 억지 36건 중 26건이 돕는 사람의 일이 그 장소와 동떨어짐. 미션만 다시 만들면 돕는
    사람·일(줄거리 칸)이 그대로라 못 고침."""
    ctx = runtime.context
    targets = state.get("fix_targets") or {}
    theme = copy.deepcopy(state["theme"])
    assert theme is not None
    try:
        await fix_fields(ctx, theme, targets)
        days = list(dict.fromkeys(str(p.split(".")[0]) for p in targets))
        await fix_old_names(ctx, theme, state["theme"] or {}, days)
    except (LlmError, LlmUnavailable):
        # #782 설계 v13: 고쳐 쓰기 응답이 형식 오류여도 테마 전체를 오류로 끝내지 않고 고치기만
        # 건너뛰어 글 검토로(16차 hand6b — 그 뒤 HELPER_FIT은 helper_fixed라 경고)
        return {"fix_targets": {}, "review_route": "REVIEW"}
    finalize_texts(theme)
    codes = {s.code for m in ctx.request.missions for s in m.standards}
    bad = check_theme(theme, ctx.grade, codes)
    if bad and (again := fix_targets(bad)) and ctx.can_regenerate():
        await fix_fields(ctx, theme, again)
        finalize_texts(theme)
        bad = check_theme(theme, ctx.grade, codes)
    out: ThemeState = {"fix_targets": {}}
    if bad:
        reasons = state.get("review_reasons") or []
        feedback = [*(state.get("plan_feedback") or []), ("REVIEW", reasons), ("THEME", bad)]
        return {**out, "plan_feedback": feedback, "plan_attempts": 0, "review_route": "PLAN"}
    # 돕는 사람 호칭이 바뀌면 다음 날 오늘 온 까닭의 옛 호칭도 고쳐짐(HELPER_SAME). 대화 첫 줄은
    # 대화를 만들 때 오늘 온 까닭으로 붙여 두므로 칸이 바뀐 요일은 모두 미션·대화부터 다시
    old = state["theme"] or {}
    changed = {d for d in DAYS if theme_day(theme, d) != theme_day(old, d)} | set(
        state.get("days_todo") or []
    )
    todo = [d for d in DAYS if d in changed]
    seed = {d: (state.get("mission_seed") or {}).get(d, []) for d in todo}
    return {**out, "theme": theme, "days_todo": todo, "mission_seed": seed, "review_route": "DAYS"}


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
