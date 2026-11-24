"""review_story: 검토 모델(생성과 다른 모델)이 글 전체를 여섯 항목으로 본다.

- #971: 글 검토 NEXT_FIT(이어 가기 기준 FOLLOW_RULE)이 FAIL인 이어 가기 날은 지문·다음 행동·할 일
  칸을 고쳐 쓴 뒤 그 요일 미션·대화부터 다시(FOLLOW 길, 요일마다 한 번). #782 v13 가의 따로 부르던
  판정(돕는 사람 판정 → 이어 가기 판정)은 작은 확인 1~3차에서 거의 통과시키고 글 검토가 짚어 호출만
  늘려 뺐다 — 그 지시문(FOLLOW_JUDGE_SYSTEM)은 측정 판정이 그래프 밖에서 따로 씀. 부탁 날 약속 줄
  검사(같은 주 같은 약속 PROMISE_SAME·약속 줄만 틀린 요일 promiseDays TALK 길)는 약속 줄이 없어져 뺌

FAIL이면 해당 부분만 다시 만들고 다시 검토한다(재검토 상한 theme_review_max_rerun, 마감 확인).
- CLUE_LOGIC만(ANSWER_HINT·SAFETY 없이) 처음 나오면 → 지목된 요일 단서 문장만 고쳐 쓰고(fix_clues)
  다시 검토. 실측 2026-11-11 글 20건에서 줄거리를 다시 만든 8건 중 6건이 CLUE_LOGIC이고 그 절반은
  단서 문장이 조건을 덜 말한 것("따뜻한 곳" → "바닥이 따뜻한 곳")이었는데, 줄거리부터 다시 만들면
  미션·대화까지 약 5분이 더 들어 영상이 마감에 걸림. 이 재검토 1번은 상한에 넣지 않음
- CLUE_LOGIC(두 번째)·ANSWER_HINT·SAFETY → 이야기 틀·단서 문제라 줄거리부터
- STANDARD_FIT·GRADE_VOCAB → 그 요일 미션·대화(요일이 없으면 다섯 요일)
- NEXT_FIT(이어 가기 날 지문이 사건과 무관·답이 다음 행동을 정하지 않음·단서가 그곳에서 나오지
  않음) → 그 요일 지문·다음 행동·할 일·장면 칸을 고쳐 쓰고(fix_follow) 그 요일 미션·대화부터.
  부분 다시 생성·이어 가기 날이 없는 판정·이미 한 번 고친 요일은 경고로
형식만 틀리면 검토만 다시. 끝내 FAIL이면 failure REVIEW. 마지막 검토의 WARN은 warnings.
부분 다시 생성(#537)에서는 다시 만들 미션 요일만 다시 보낼 수 있고,
줄거리·단서·대상 밖 요일을 고치라는
판정이면 failure REVIEW로 끝낸다(사용자 결정 2026-11-17 "줄거리부터 다시면 CHECK_FAILED").
"""

from langgraph.runtime import Runtime

from app.theme_draft.checks import (
    DAYS,
    FOLLOW,
    REVIEW_IDS,
    check_review,
    helper_use_day,
    mission_way,
    theme_day,
)
from app.theme_draft.models import GeneratedStoryReview
from app.theme_draft.nodes import DEADLINE_REASON, THEME_CALL_TYPE, ThemeContext, ThemeState
from app.theme_draft.regen import OUTSIDE_REASON, outside_targets

PLAN_ROUTE = {"CLUE_LOGIC", "ANSWER_HINT", "SAFETY"}
DAY_ROUTE = {"STANDARD_FIT", "GRADE_VOCAB"}
# #971: NEXT_FIT이 FAIL인 이어 가기 날에서 고쳐 쓰는 줄거리 칸(그 요일 미션·대화는 다시). 아이
# 글이 가는 곳(helperUse)은 쓴 글을 읽을 사람 날만
FOLLOW_FIELDS = (
    "missionMaterial",
    "nextTarget",
    "missionHook",
    "sceneNote",
    "helper",
    "helperUse",
)


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
    # 이미 고친 요일·부분 다시 생성의 NEXT_FIT은 경고로
    fails, warns = settle_next_fit(state, fails, warns)
    out: ThemeState = {"review_runs": runs, "review_warnings": warns}
    if not fails and not shape:
        return {**out, "review_reasons": [], "review_route": "PASS"}
    reasons = shape or [review_reason(x) for x in fails]
    out["review_reasons"] = reasons
    # 단서만 고친 재검토는 상한에 넣지 않음(싼 길)
    spare = 1 if state.get("clue_fixed") else 0
    if runs > ctx.settings.theme_review_max_rerun + spare:
        return {**out, "failure": {"stage": "REVIEW", "reasons": reasons}, "review_route": "FAIL"}
    if not ctx.can_regenerate():
        return {
            **out,
            "failure": {"stage": "REVIEW", "reasons": [*reasons, DEADLINE_REASON]},
            "review_route": "FAIL",
        }
    if shape:  # 형식만 틀리면 검토만 다시
        return {**out, "review_route": "AGAIN"}
    result = route_fails(state, out, fails, reasons)
    if outside_targets(state, result["review_route"], result.get("days_todo") or []):
        # 부분 다시 생성(#537): 고르지 않은 줄거리·단서·요일은 바꾸지 않고 실패로 끝냄
        return {
            **out,
            "failure": {"stage": "REVIEW", "reasons": [*reasons, OUTSIDE_REASON]},
            "review_route": "FAIL",
        }
    return result


def follow_days(state: ThemeState, days: list[str] | None) -> list[str]:
    """days(비면 다섯 요일) 중 이어 가기 날."""
    theme = state.get("theme") or {}
    follow = {d.get("day") for d in theme.get("days") or [] if mission_way(d) == FOLLOW}
    return [d for d in DAYS if d in follow and (not days or d in days)]


def settle_next_fit(
    state: ThemeState, fails: list[dict], warns: list[dict]
) -> tuple[list[dict], list[dict]]:
    """NEXT_FIT FAIL 중 고칠 이어 가기 날이 없는 것(수사 날만 짚음), 부분 다시 생성(줄거리를 바꾸지
    않음, #537), 이미 한 번 고친 요일(follow_fixed_days)의 것은 경고로 남긴다(#782 설계 v13
    HELPER_FIT과 같은 방식, #971 작은 확인 3차부터 요일마다 한 번 — 월요일을 고친 뒤 처음 짚힌
    금요일이 경고로만 남았음). 같은 요일 두 번째 FAIL을 실패로 두면 재검토 상한에 걸려 실패함."""
    fixed = set(state.get("follow_fixed_days") or [])
    keep: list[dict] = []
    for x in fails:
        if x["id"] != "NEXT_FIT":
            keep.append(x)
            continue
        todo = [] if state.get("partial") else follow_days(state, x.get("days"))
        open_days = [d for d in todo if d not in fixed]
        if open_days:
            keep.append({**x, "days": open_days})
        if not open_days or len(open_days) < len(todo):
            warns = [*warns, x]
    return keep, warns


def route_fails(
    state: ThemeState, out: ThemeState, fails: list[dict], reasons: list[str]
) -> ThemeState:
    """FAIL 항목 → 다시 만들 곳(CLUE 단서만·PLAN 줄거리부터·FOLLOW 지문·다음 행동 칸부터·DAYS 그
    요일)."""
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
    # #971: 이어 가기 날 지문이 사건과 무관하거나 답이 다음 행동을 정하지 않으면 그 요일 지문·다음
    # 행동 칸을 고쳐 쓰고(fix_follow) 그 요일 미션·대화부터 다시(미션만 다시 만들면 못 고침)
    follow = [x for x in fails if x["id"] == "NEXT_FIT"]
    fixed = list(state.get("follow_fixed_days") or [])
    follow_day = [
        d
        for d in dict.fromkeys(d for x in follow for d in follow_days(state, x.get("days")))
        if d not in fixed
    ]
    route_ids = DAY_ROUTE | {"NEXT_FIT"}
    days = {d for x in fails if x["id"] in DAY_ROUTE for d in (x.get("days") or DAYS)}
    todo = [d for d in DAYS if d in days or d in follow_day]
    seed = {
        d: [
            review_reason(x)
            for x in fails
            if x["id"] in route_ids and (not x.get("days") or d in x["days"])
        ]
        for d in todo
    }
    if follow_day:
        targets = {
            f"{d}.{k}": [review_reason(x) for x in follow if not x.get("days") or d in x["days"]]
            for d in DAYS
            if d in follow_day
            for k in FOLLOW_FIELDS
            if k != "helperUse" or helper_use_day(state["theme"], theme_day(state["theme"], d))
        }
        return {
            **out,
            "fix_targets": targets,
            "follow_fixed_days": [*fixed, *follow_day],
            "days_todo": todo,
            "mission_seed": seed,
            "review_route": "FOLLOW",
        }
    return {**out, "days_todo": todo, "mission_seed": seed, "review_route": "DAYS"}
