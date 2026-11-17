"""generate_mission(요일마다 Send로 병렬) + review_missions.

요일 하나의 흐름: 미션 초안 재사용 생성 → 코드 검사(기존 ai 검사 + 테마 몫)
→ 통과하면 검토 모델이 미션 검토(예시 답 완결·성취기준·자료·이야기 소재 STORY_LINK,
  STORY_LINK는 경고만)
→ 통과하면 그 요일 수사 연결 문장을 문제 소재에 맞게 고쳐 씀(fix_hook, #535 닫기, 결과는
  hook_fixes로 돌려주고 missions_done이 테마에 넣음)
→ 실패하면 그 요일만 사유를 넣어 다시(상한 theme_max_regen, 마감 확인).
검토가 예시 답 미완성(EXAMPLE_COMPLETE)으로만 실패하면 질문은 그대로 두고 예시 답만 고쳐 쓴 뒤
코드 검사·검토를 다시 한다(상한 theme_max_text_fix). 미션 전체를 새로 만들면 질문이 바뀌어 또
어긋나서(실측 2026-11-11 repo-*-5, 시도 단위 21번).
review_missions를 같은 요일 노드 안에서 도는 것은 다시 만들고 다시 검토하는 루프가
요일마다 독립이기 때문이다(다른 요일을 기다리지 않음).
줄거리를 다시 만들거나 글 검토가 요일을 다시 보낼 때도 이 노드를 거친다.
"""

import copy
from typing import Any

from langgraph.runtime import Runtime

from app.mission_draft.models import Draft, MissionDraftRequest
from app.theme_draft.checks import (
    DAY_TYPE,
    MISSION_REVIEW_IDS,
    check_mission,
    check_review,
    check_theme,
    hook_problems,
    set_text_at,
)
from app.theme_draft.models import GeneratedExampleFix, GeneratedHookFixes, GeneratedMissionReview
from app.theme_draft.nodes import (
    DEADLINE_REASON,
    THEME_CALL_TYPE,
    ThemeContext,
    ThemeState,
    split_mission_feedback,
    uniq,
)


def mission_request(ctx: ThemeContext, day: str, previous: list[Any]) -> MissionDraftRequest:
    m = ctx.request.mission_for(DAY_TYPE[day])  # type: ignore[arg-type]
    return MissionDraftRequest(
        standards=m.standards,
        thinking_type=m.thinking_type,
        element_codes=m.element_codes,
        grade_min=ctx.request.grade_min,
        grade_max=ctx.request.grade_max,
        input_type=m.input_type,
        previous_failures=previous,
    )


async def review_mission(
    ctx: ThemeContext, day: str, request: MissionDraftRequest, draft: Draft, theme: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """검토 모델의 미션 검토. (FAIL 사유, WARN 사유). 형식이 틀리면 FAIL로 본다.

    그날 장소·증거 발견 줄·수사 연결 문장을 함께 줘 문제 소재가 이야기와 이어지는지(STORY_LINK)도
    본다(#535). 정답·단서는 넣지 않는다. STORY_LINK는 FAIL이어도 미션을 다시 만들지 않고 경고로만
    남긴다(사용자 결정 2026-11-15: 관리자가 채택 화면 경고를 보고 사람이 확인)."""
    knowledge = (ctx.knowledge or {}).get(day)
    body = ctx.prompt.body
    generated = await ctx.review_llm.generate(
        system=body.MISSION_REVIEW_SYSTEM,
        user=body.mission_review_user(
            request,
            draft,
            ctx.grade,
            body.mission_target(theme),  # 시간 탐정은 대상이 '때'라 주지 않음(#634 ④)
            knowledge,
            body.story_brief(theme, day),
            in_hand=body.target_in_hand(theme),
        ),
        output=GeneratedMissionReview,
        call_type=THEME_CALL_TYPE,
        prompt_version=ctx.prompt.version,
        max_tokens=ctx.settings.theme_review_max_tokens,
        deadline=ctx.deadline,
        timeout=ctx.settings.theme_llm_timeout,
        max_retries=ctx.settings.theme_llm_retries,
    )
    fails, warns, shape = check_review(generated.data.model_dump(), MISSION_REVIEW_IDS)
    reason = lambda x: f"MISSION_REVIEW {x['id']} {x['reason']}"  # noqa: E731
    # 글 실측(2026-11-13)에서 STORY_LINK FAIL로 미션을 다시 만들면 시간이 평균 +78초, 다른 항목
    # 실패도 늘어서
    # 경고만 남김(사용자 결정 2026-11-15). 응답 warnings(MISSION, 요일)에 그대로 실림
    advisory = [x for x in fails if x["id"] in WARN_ONLY_IDS]
    fails = [x for x in fails if x["id"] not in WARN_ONLY_IDS]
    return shape + [reason(x) for x in fails], [reason(x) for x in [*advisory, *warns]]


EXAMPLE_ONLY = "MISSION_REVIEW EXAMPLE_COMPLETE "
# FAIL이어도 다시 만들지 않고 경고로만 남기는 미션 검토 항목(사용자 결정 2026-11-15)
WARN_ONLY_IDS = ("STORY_LINK",)


# 예시 답 고쳐 쓰기는 서술·논술·풀이만(고르기·순서·분류는 정답 키라 고쳐 쓰기로 못 고침, 점검 C16)
EXAMPLE_FIX_TYPES = ("NARRATIVE", "ESSAY", "SOLUTION_STEPS")


def only_example(bad: list[str], input_type: str = "NARRATIVE") -> bool:
    return (
        input_type in EXAMPLE_FIX_TYPES
        and bool(bad)
        and all(r.startswith(EXAMPLE_ONLY) for r in bad)
    )


async def fix_example(
    ctx: ThemeContext, request: MissionDraftRequest, draft: Draft, reasons: list[str]
) -> Draft:
    """질문·생각 열기 질문은 두고 예시 답(풀이면 최종 답도)만 고쳐 쓴다."""
    generated = await ctx.llm.generate(
        system=ctx.prompt.body.EXAMPLE_FIX_SYSTEM,
        user=ctx.prompt.body.example_fix_user(request, draft, ctx.grade, reasons),
        output=GeneratedExampleFix,
        call_type=THEME_CALL_TYPE,
        prompt_version=ctx.prompt.version,
        max_tokens=ctx.settings.theme_dialogue_max_tokens,
        deadline=ctx.deadline,
        timeout=ctx.settings.theme_llm_timeout,
        max_retries=ctx.settings.theme_llm_retries,
    )
    update: dict[str, Any] = {"example_answer": generated.data.exampleAnswer.strip()}
    final = (generated.data.finalAnswer or "").strip()
    if request.input_type == "SOLUTION_STEPS" and final and draft.answer_key is not None:
        update["answer_key"] = draft.answer_key.model_copy(update={"final_answer": final})
    return draft.model_copy(update=update)


async def generate_mission(payload: dict[str, Any], runtime: Runtime[ThemeContext]) -> ThemeState:
    """payload: {day, theme, seed}. 그 요일의 drafts·mission_failures·mission_warnings를 돌려준다.

    금요일 안내(guide)도 LLM이 만든 그대로 둔다(단서는 학생이 그날 미션을 마친 뒤 learning이
    보여 주므로 코드가 단서 목록을 넣지 않음, 사용자 결정 2026-11-11).
    """
    ctx = runtime.context
    day, theme = payload["day"], payload["theme"]
    feedback: list[str] = list(payload.get("seed") or [])
    bad: list[str] = []
    for attempt in range(ctx.settings.theme_max_regen + 1):
        if attempt and not ctx.can_regenerate():
            bad = [*bad, DEADLINE_REASON]
            break
        existing, theme_feedback = split_mission_feedback(feedback)
        request = mission_request(ctx, day, existing)
        response = await ctx.missions.generate(
            request,
            extra_user=ctx.prompt.body.mission_extra(
                theme, day, ctx.grade, theme_feedback, (ctx.knowledge or {}).get(day)
            ),
            call_type=THEME_CALL_TYPE,
            deadline=ctx.deadline,
            timeout=ctx.settings.theme_llm_timeout,
            question_max_chars=ctx.settings.theme_question_max_chars,
        )
        draft = response.draft
        fixes = 0
        # 같은 질문에서 앞서 고쳐 쓰게 한 예시 답 사유도 함께 넘김(실측 2026-11-15 닫기 2차:
        # 고쳐 쓴 뒤 검토가 같은 결함을 다시 짚어 같은 미션이 3번 실패)
        example_reasons: list[str] = []
        while True:
            bad = check_mission(
                theme,
                request,
                draft,
                ctx.grade,
                ctx.settings.theme_question_max_chars,
                ctx.settings.followup_example_overlap_chars,
            )
            warns: list[str] = []
            if not bad:
                bad, warns = await review_mission(ctx, day, request, draft, theme)
            if not bad:
                hook, warns = await fix_hook(ctx, day, theme, request, draft, warns)
                return {
                    "drafts": {day: draft},
                    "mission_failures": {day: []},
                    "mission_warnings": {day: warns},
                    "hook_fixes": {day: hook},
                }
            if (
                only_example(bad, request.input_type)
                and fixes < ctx.settings.theme_max_text_fix
                and ctx.can_regenerate()
            ):
                example_reasons = uniq([*example_reasons, *bad])
                draft = await fix_example(ctx, request, draft, example_reasons)
                fixes += 1
                continue
            break
        feedback = uniq([*feedback, *bad])
    return {
        "drafts": {day: draft},
        "mission_failures": {day: bad},
        "mission_warnings": {day: []},
        "hook_fixes": {day: ""},
    }


STORY_LINK_WARN = "MISSION_REVIEW STORY_LINK "


async def fix_hook(
    ctx: ThemeContext,
    day: str,
    theme: dict[str, Any],
    request: MissionDraftRequest,
    draft: Draft,
    warns: list[str],
) -> tuple[str, list[str]]:
    """미션이 통과한 직후 그 요일 수사 연결 문장을 그날 문제 소재 낱말이 들어가게 고쳐 쓴다(#535
    닫기). (고친 문장, 미션 경고). 고치지 않으면 빈 문자열.

    미션은 다시 만들지 않는다. 수사 연결 문장은 줄거리 단계에서 미션보다 먼저 정해져 문제 소재와
    어긋날 수 있어서(실측 2026-11-13·15: 경고 없는 요일에서도 '발자국 자리'↔'포장 끈' 등).
    요일 노드 안에서 하므로 다른 요일 미션을 기다리지 않는다(닫기 2차는 모든 요일 미션 뒤 LLM 1번과
    다시 확인을 차례로 해 글 실측 평균이 284 → 460초로 늘었음, 닫기 3차).

    고친 문장이 줄거리 코드 검사(글자 수·후보 이름 등)에 걸리거나 그날 문제의 답·예시 답·단서
    결론을 미리 말하면(hook_problems) 원래 문장을 둔다. STORY_LINK 경고가 났던 요일은 고친 문장으로
    미션 검토를 다시 해 경고를 바꾸고, 다시 확인해도 남으면 경고로 남긴다(사용자 결정 2026-11-15
    경고만). 마감이 가까우면 건너뛴다.
    """
    if not ctx.can_regenerate():
        return "", warns
    flagged = [w for w in warns if w.startswith(STORY_LINK_WARN)]
    body = ctx.prompt.body
    generated = await ctx.llm.generate(
        system=body.FIX_SYSTEM,
        user=body.hook_fix_user(theme, {day: (draft.question, flagged)}),
        output=GeneratedHookFixes,
        call_type=THEME_CALL_TYPE,
        prompt_version=ctx.prompt.version,
        max_tokens=ctx.settings.theme_dialogue_max_tokens,
        deadline=ctx.deadline,
        timeout=ctx.settings.theme_llm_timeout,
        max_retries=ctx.settings.theme_llm_retries,
    )
    path = f"{day}.missionHook"
    text = next((f.text.strip() for f in generated.data.fixes if f.path == path), "")
    if not text or text == theme_day_text(theme, path):
        return "", warns
    fixed = copy.deepcopy(theme)
    set_text_at(fixed, path, text)
    codes = {s.code for m in ctx.request.missions for s in m.standards}
    overlap = ctx.settings.followup_example_overlap_chars
    if check_theme(fixed, ctx.grade, codes) or hook_problems(fixed, day, text, draft, overlap):
        return "", warns
    if flagged:  # 경고가 났던 요일만 다시 확인
        _, again = await review_mission(ctx, day, request, draft, fixed)
        kept = [w for w in warns if not w.startswith(STORY_LINK_WARN)]
        warns = uniq([*kept, *[w for w in again if w.startswith(STORY_LINK_WARN)]])
    return text, warns


def apply_hooks(theme: dict[str, Any], hooks: dict[str, str], days: list[str]) -> dict[str, Any]:
    """요일 노드가 고쳐 쓴 수사 연결 문장을 테마에 넣는다(이번에 만든 요일만, 빈 값은 그대로)."""
    todo = {d: hooks[d] for d in days if hooks.get(d)}
    if not todo:
        return theme
    fixed = copy.deepcopy(theme)
    for day, text in todo.items():
        set_text_at(fixed, f"{day}.missionHook", text)
    return fixed


def theme_day_text(theme: dict[str, Any], path: str) -> str:
    day, _, key = path.partition(".")
    return str(next(d for d in theme["days"] if d["day"] == day).get(key) or "")
