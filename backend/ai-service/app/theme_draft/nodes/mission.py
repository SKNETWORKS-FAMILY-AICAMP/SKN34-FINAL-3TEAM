"""generate_mission(요일마다 Send로 병렬) + review_missions.

요일 하나의 흐름: 미션 초안 재사용 생성 → 코드 검사(기존 ai 검사 + 테마 몫)
→ 통과하면 검토 모델이 미션 검토(예시 답 완결·성취기준·자료)
→ 실패하면 그 요일만 사유를 넣어 다시(상한 theme_max_regen, 마감 확인).
검토가 예시 답 미완성(EXAMPLE_COMPLETE)으로만 실패하면 질문은 그대로 두고 예시 답만 고쳐 쓴 뒤
코드 검사·검토를 다시 한다(상한 theme_max_text_fix). 미션 전체를 새로 만들면 질문이 바뀌어 또
어긋나서(실측 2026-11-11 repo-*-5, 시도 단위 21번).
review_missions를 같은 요일 노드 안에서 도는 것은 다시 만들고 다시 검토하는 루프가
요일마다 독립이기 때문이다(다른 요일을 기다리지 않음).
줄거리를 다시 만들거나 글 검토가 요일을 다시 보낼 때도 이 노드를 거친다.
"""

from typing import Any

from langgraph.runtime import Runtime

from app.mission_draft.models import Draft, MissionDraftRequest
from app.theme_draft.checks import (
    DAY_TYPE,
    MISSION_REVIEW_IDS,
    check_mission,
    check_review,
)
from app.theme_draft.models import GeneratedExampleFix, GeneratedMissionReview
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
    ctx: ThemeContext, day: str, request: MissionDraftRequest, draft: Draft, target: str | None
) -> tuple[list[str], list[str]]:
    """검토 모델의 미션 검토. (FAIL 사유, WARN 사유). 형식이 틀리면 FAIL로 본다."""
    knowledge = (ctx.knowledge or {}).get(day)
    generated = await ctx.review_llm.generate(
        system=ctx.prompt.body.MISSION_REVIEW_SYSTEM,
        user=ctx.prompt.body.mission_review_user(request, draft, ctx.grade, target, knowledge),
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
    return shape + [reason(x) for x in fails], [reason(x) for x in warns]


EXAMPLE_ONLY = "MISSION_REVIEW EXAMPLE_COMPLETE "


def only_example(bad: list[str]) -> bool:
    return bool(bad) and all(r.startswith(EXAMPLE_ONLY) for r in bad)


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
                bad, warns = await review_mission(ctx, day, request, draft, theme.get("target"))
            if not bad:
                return {
                    "drafts": {day: draft},
                    "mission_failures": {day: []},
                    "mission_warnings": {day: warns},
                }
            if (
                only_example(bad)
                and fixes < ctx.settings.theme_max_text_fix
                and ctx.can_regenerate()
            ):
                draft = await fix_example(ctx, request, draft, bad)
                fixes += 1
                continue
            break
        feedback = uniq([*feedback, *bad])
    return {
        "drafts": {day: draft},
        "mission_failures": {day: bad},
        "mission_warnings": {day: []},
    }
