"""review_story: 검토 모델(생성과 다른 모델)이 글 전체를 다섯 항목으로 본다.

FAIL이면 해당 부분만 다시 만들고 다시 검토한다(재검토 상한 theme_review_max_rerun, 마감 확인).
- CLUE_LOGIC만(ANSWER_HINT·SAFETY 없이) 처음 나오면 → 지목된 요일 단서 문장만 고쳐 쓰고(fix_clues)
  다시 검토. 실측 2026-11-11 글 20건에서 줄거리를 다시 만든 8건 중 6건이 CLUE_LOGIC이고 그 절반은
  단서 문장이 조건을 덜 말한 것("따뜻한 곳" → "바닥이 따뜻한 곳")이었는데, 줄거리부터 다시 만들면
  미션·대화까지 약 5분이 더 들어 영상이 마감에 걸림. 이 재검토 1번은 상한에 넣지 않음
- CLUE_LOGIC(두 번째)·ANSWER_HINT·SAFETY → 이야기 틀·단서 문제라 줄거리부터
- STANDARD_FIT·GRADE_VOCAB → 그 요일 미션·대화(요일이 없으면 다섯 요일)
형식만 틀리면 검토만 다시. 끝내 FAIL이면 failure REVIEW. 마지막 검토의 WARN은 warnings.
"""

from langgraph.runtime import Runtime

from app.theme_draft.checks import DAYS, REVIEW_IDS, check_review
from app.theme_draft.models import GeneratedStoryReview
from app.theme_draft.nodes import DEADLINE_REASON, THEME_CALL_TYPE, ThemeContext, ThemeState

PLAN_ROUTE = {"CLUE_LOGIC", "ANSWER_HINT", "SAFETY"}
DAY_ROUTE = {"STANDARD_FIT", "GRADE_VOCAB"}


def review_reason(item: dict) -> str:
    return f"{item['id']} {item.get('days')} {item.get('reason')}"


async def review_story(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    ctx = runtime.context
    dialogues = {d: lines for d, lines in (state.get("dialogues") or {}).items() if lines}
    generated = await ctx.review_llm.generate(
        system=ctx.prompt.body.REVIEW_SYSTEM,
        user=ctx.prompt.body.review_user(ctx.request, state["theme"], state["drafts"], dialogues),
        output=GeneratedStoryReview,
        call_type=THEME_CALL_TYPE,
        prompt_version=ctx.prompt.version,
        max_tokens=ctx.settings.theme_review_max_tokens,
        deadline=ctx.deadline,
        timeout=ctx.settings.theme_llm_timeout,
        max_retries=ctx.settings.theme_llm_retries,
    )
    runs = state.get("review_runs", 0) + 1
    fails, warns, shape = check_review(generated.data.model_dump(), REVIEW_IDS)
    out: ThemeState = {"review_runs": runs, "review_warnings": warns}
    if not fails and not shape:
        return {**out, "review_reasons": [], "review_route": "PASS"}
    reasons = shape or [review_reason(x) for x in fails]
    out["review_reasons"] = reasons
    if runs > ctx.settings.theme_review_max_rerun + (1 if state.get("clue_fixed") else 0):
        return {**out, "failure": {"stage": "REVIEW", "reasons": reasons}, "review_route": "FAIL"}
    if not ctx.can_regenerate():
        return {
            **out,
            "failure": {"stage": "REVIEW", "reasons": [*reasons, DEADLINE_REASON]},
            "review_route": "FAIL",
        }
    if shape:  # 형식만 틀리면 검토만 다시
        return {**out, "review_route": "AGAIN"}
    clue = [x for x in fails if x["id"] == "CLUE_LOGIC"]
    if (
        clue
        and not state.get("clue_fixed")
        and not any(x["id"] in PLAN_ROUTE - {"CLUE_LOGIC"} for x in fails)
    ):
        days = [d for d in DAYS if any(not x.get("days") or d in x["days"] for x in clue)]
        targets = {
            f"{d}.clue": [review_reason(x) for x in clue if not x.get("days") or d in x["days"]]
            for d in days
        }
        return {**out, "fix_targets": targets, "review_route": "CLUE"}
    if any(x["id"] in PLAN_ROUTE for x in fails):
        feedback = [*(state.get("plan_feedback") or []), ("REVIEW", reasons)]
        return {**out, "plan_feedback": feedback, "plan_attempts": 0, "review_route": "PLAN"}
    days = {d for x in fails if x["id"] in DAY_ROUTE for d in (x.get("days") or DAYS)}
    todo = [d for d in DAYS if d in days]
    seed = {
        d: [
            review_reason(x)
            for x in fails
            if x["id"] in DAY_ROUTE and (not x.get("days") or d in x["days"])
        ]
        for d in todo
    }
    return {**out, "days_todo": todo, "mission_seed": seed, "review_route": "DAYS"}
