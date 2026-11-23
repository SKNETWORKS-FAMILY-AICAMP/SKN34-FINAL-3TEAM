"""review_story: 검토 모델(생성과 다른 모델)이 글 전체를 여섯 항목으로 본다.

- #782 설계 v13: 검토 호출 전에 같은 주 같은 약속 줄을 코드가 세어 뒤 요일 대화만 한 번 다시 만든다
  (TALK 길, 테마마다 한 번)

FAIL이면 해당 부분만 다시 만들고 다시 검토한다(재검토 상한 theme_review_max_rerun, 마감 확인).
- CLUE_LOGIC만(ANSWER_HINT·SAFETY 없이) 처음 나오면 → 지목된 요일 단서 문장만 고쳐 쓰고(fix_clues)
  다시 검토. 실측 2026-11-11 글 20건에서 줄거리를 다시 만든 8건 중 6건이 CLUE_LOGIC이고 그 절반은
  단서 문장이 조건을 덜 말한 것("따뜻한 곳" → "바닥이 따뜻한 곳")이었는데, 줄거리부터 다시 만들면
  미션·대화까지 약 5분이 더 들어 영상이 마감에 걸림. 이 재검토 1번은 상한에 넣지 않음
- #782 설계 v12: FAIL이 CLUE_LOGIC뿐이고 그 요일이 모두 약속 줄만 틀린 요일(promiseDays)이면 → 그
  요일 대화만 다시 만들고(generate_dialogue, 검토 사유를 처음부터 넣음) 다시 검토. 첫 번 재검토는
  상한에 넣지 않음(talk_fixed). 9차 측정 글 검토 실패 50 중 27이 약속 줄이었는데 단서를 고치고
  두 번째에 줄거리를 다시 만들어 시간·호출이 늘었음
- CLUE_LOGIC(두 번째)·ANSWER_HINT·SAFETY → 이야기 틀·단서 문제라 줄거리부터
- STANDARD_FIT·GRADE_VOCAB → 그 요일 미션·대화(요일이 없으면 다섯 요일)
- #782 설계 v13: HELPER_FIT(부탁 날 돕는 사람의 일이 그 장소와 동떨어지거나 아이 답이 안 쓰임) →
  그 요일 돕는 사람·일 칸을 고쳐 쓰고(fix_helpers) 그 요일 미션·대화부터. 부분 다시 생성과 부탁 날이
  없는 판정은 경고로
형식만 틀리면 검토만 다시. 끝내 FAIL이면 failure REVIEW. 마지막 검토의 WARN은 warnings.
부분 다시 생성(#537)에서는 다시 만들 미션 요일만 다시 보낼 수 있고,
줄거리·단서·대상 밖 요일을 고치라는
판정이면 failure REVIEW로 끝낸다(사용자 결정 2026-11-17 "줄거리부터 다시면 CHECK_FAILED").
"""

from langgraph.runtime import Runtime

from app.llm.base import LlmError, LlmUnavailable
from app.theme_draft.checks import (
    ASK,
    DAYS,
    REVIEW_IDS,
    check_review,
    helper_use_day,
    mission_way,
    same_week_promises,
    theme_day,
)
from app.theme_draft.models import GeneratedHelperJudge, GeneratedStoryReview
from app.theme_draft.nodes import DEADLINE_REASON, THEME_CALL_TYPE, ThemeContext, ThemeState
from app.theme_draft.regen import OUTSIDE_REASON, outside_targets

PLAN_ROUTE = {"CLUE_LOGIC", "ANSWER_HINT", "SAFETY"}
DAY_ROUTE = {"STANDARD_FIT", "GRADE_VOCAB"}
# #782 설계 v13: HELPER_FIT이 FAIL인 부탁 날에서 고쳐 쓰는 줄거리 칸(그 요일 미션·대화는 다시)
HELPER_FIELDS = ("helper", "helperUse", "missionHook", "missionMaterial", "sceneNote")


def review_reason(item: dict) -> str:
    return f"{item['id']} {item.get('days')} {item.get('reason')}"


async def review_story(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    ctx = runtime.context
    dialogues = {d: lines for d, lines in (state.get("dialogues") or {}).items() if lines}
    # #782 설계 v13: 같은 주 같은 약속 줄은 검토 호출 전에 코드가 세어 뒤 요일 대화만 한 번 다시
    # (요일 대화를 따로 동시에 만들어 서로 못 봄, 11·12·13차 매번 1~2건)
    if (
        not state.get("promise_deduped")
        and (same := same_week_promises(state["theme"], dialogues))
        and not outside_targets(state, "TALK", list(same))
        and ctx.can_regenerate()
    ):
        return {
            "talk_seed": same,
            "talk_keep": True,
            "promise_deduped": True,
            "review_route": "TALK",
        }
    # #782 설계 v13 가: 돕는 사람 판정(측정 판정과 같은 말, 테마마다 한 번). 억지 요일은 돕는
    # 사람·일 칸을 고쳐 쓰고 그 요일 미션·대화부터 다시(검토 호출은 그 뒤에)
    judged: ThemeState = {}
    if not state.get("helper_fixed") and not state.get("partial") and ctx.can_regenerate():
        judged = await judge_helpers(ctx, state, dialogues)
        if judged.get("review_route"):  # 억지 요일이 있으면 HELPER 길(글 검토는 그 뒤에)
            return judged
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
    # 판정을 이번에 했으면(억지 없음) 글 검토 HELPER_FIT은 경고로
    fails, warns = settle_helper_fit({**state, **judged}, fails, warns)
    out: ThemeState = {"review_runs": runs, "review_warnings": warns, **judged}
    if not fails and not shape:
        return {**out, "review_reasons": [], "review_route": "PASS"}
    reasons = shape or [review_reason(x) for x in fails]
    out["review_reasons"] = reasons
    # 단서만 고친 재검토·대화만 다시 만든 첫 재검토(#782 설계 v12)는 상한에 넣지 않음(싼 길)
    spare = (1 if state.get("clue_fixed") else 0) + (1 if state.get("talk_fixed") else 0)
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
    todo = result.get("days_todo") or list(result.get("talk_seed") or {})
    if outside_targets(state, result["review_route"], todo):
        # 부분 다시 생성(#537): 고르지 않은 줄거리·단서·요일은 바꾸지 않고 실패로 끝냄
        return {
            **out,
            "failure": {"stage": "REVIEW", "reasons": [*reasons, OUTSIDE_REASON]},
            "review_route": "FAIL",
        }
    return result


async def judge_helpers(
    ctx: ThemeContext, state: ThemeState, dialogues: dict[str, list[dict]]
) -> ThemeState:
    """부탁 날을 측정 판정과 같은 말로 판정해 억지 요일이 있으면 HELPER 길(review_route 있음),
    없으면 {"helper_fixed": True}만(호출한 쪽이 글 검토를 이어 함). 어느 쪽이든 helper_fixed를 세워
    테마마다 한 번만 부름(그 뒤 글 검토 HELPER_FIT은 경고). 판정 호출이 실패하면 건너뜀."""
    days = ask_days(state, None)
    if not days:
        return {"helper_fixed": True}
    try:
        generated = await ctx.review_llm.generate(
            system=ctx.prompt.body.HELPER_JUDGE_SYSTEM,
            user=ctx.prompt.body.helper_judge_user(
                state["theme"], state.get("drafts") or {}, dialogues, days
            ),
            output=GeneratedHelperJudge,
            call_type=THEME_CALL_TYPE,
            prompt_version=ctx.prompt.version,
            max_tokens=ctx.settings.theme_review_max_tokens,
            deadline=ctx.deadline,
            timeout=ctx.settings.theme_llm_timeout,
            max_retries=ctx.settings.theme_llm_retries,
        )
    except (LlmError, LlmUnavailable):
        return {"helper_fixed": True}
    forced = [x for x in generated.data.items if x.flow == "FORCED" and x.day in days]
    if not forced:
        return {"helper_fixed": True}
    fails = [
        {"id": "HELPER_FIT", "verdict": "FAIL", "days": [x.day], "reason": x.reason} for x in forced
    ]
    return route_fails(state, {}, fails, [review_reason(x) for x in fails])


def ask_days(state: ThemeState, days: list[str] | None) -> list[str]:
    """days(비면 다섯 요일) 중 부탁 날."""
    theme = state.get("theme") or {}
    ask = {d.get("day") for d in theme.get("days") or [] if mission_way(d) == ASK}
    return [d for d in DAYS if d in ask and (not days or d in days)]


def settle_helper_fit(
    state: ThemeState, fails: list[dict], warns: list[dict]
) -> tuple[list[dict], list[dict]]:
    """HELPER_FIT FAIL 중 고칠 부탁 날이 없는 것(수사 날만 짚음), 부분 다시 생성(줄거리를 바꾸지
    않음, #537), 이미 한 번 고친 뒤(helper_fixed)의 것은 경고로 남긴다(#782 설계 v13). 두 번째
    FAIL을 실패로 두면 v13 전에는 통과하던 테마가 재검토 상한에 걸려 실패함."""
    keep: list[dict] = []
    for x in fails:
        if x["id"] == "HELPER_FIT" and (
            state.get("partial") or state.get("helper_fixed") or not ask_days(state, x.get("days"))
        ):
            warns = [*warns, x]
        else:
            keep.append(x)
    return keep, warns


def promise_only_days(fails: list[dict]) -> list[str]:
    """FAIL이 CLUE_LOGIC 하나뿐이고 그 요일이 모두 약속 줄만 틀린 요일(promiseDays)이면 그 요일들
    (#782 설계 v12). 아니면 빈 목록."""
    if len(fails) != 1 or fails[0]["id"] != "CLUE_LOGIC":
        return []
    days, promise = fails[0].get("days") or [], fails[0].get("promiseDays") or []
    return [d for d in DAYS if d in days] if days and set(days) <= set(promise) else []


def route_fails(
    state: ThemeState, out: ThemeState, fails: list[dict], reasons: list[str]
) -> ThemeState:
    """FAIL 항목 → 다시 만들 곳(TALK 그 요일 대화만·CLUE 단서만·PLAN 줄거리부터·DAYS 그 요일)."""
    # #782 설계 v12: 약속 줄만 틀리면 단서·줄거리가 아니라 그 요일 대화만 다시(9차 글 검토 실패
    # 50 중 27이 약속 줄인데 단서를 고치고 두 번째에 줄거리를 다시 만들어 시간·호출이 늚)
    if talk := promise_only_days(fails):
        seed = {d: [review_reason(fails[0])] for d in talk}
        return {
            **out,
            "talk_seed": seed,
            "talk_fixed": True,
            "talk_keep": False,
            "review_route": "TALK",
        }
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
    # #782 설계 v13: 돕는 사람의 일이 그 장소와 동떨어지거나 아이 답이 안 쓰이면 그 요일 돕는 사람·
    # 일 칸을 고쳐 쓰고(fix_helpers) 그 요일 미션·대화부터 다시(미션만 다시 만들면 못 고침)
    helper = [x for x in fails if x["id"] == "HELPER_FIT"]
    helper_days = list(dict.fromkeys(d for x in helper for d in ask_days(state, x.get("days"))))
    route_ids = DAY_ROUTE | {"HELPER_FIT"}
    days = {d for x in fails if x["id"] in DAY_ROUTE for d in (x.get("days") or DAYS)}
    todo = [d for d in DAYS if d in days or d in helper_days]
    seed = {
        d: [
            review_reason(x)
            for x in fails
            if x["id"] in route_ids and (not x.get("days") or d in x["days"])
        ]
        for d in todo
    }
    if helper_days:
        targets = {
            f"{d}.{k}": [review_reason(x) for x in helper if not x.get("days") or d in x["days"]]
            for d in DAYS
            if d in helper_days
            for k in HELPER_FIELDS
            # 아이 답의 쓰임은 국어 부탁 날만 쓰는 칸(그 밖의 날은 빈 문자열)
            if k != "helperUse" or helper_use_day(state["theme"], theme_day(state["theme"], d))
        }
        return {
            **out,
            "fix_targets": targets,
            "helper_fixed": True,
            "days_todo": todo,
            "mission_seed": seed,
            "review_route": "HELPER",
        }
    return {**out, "days_todo": todo, "mission_seed": seed, "review_route": "DAYS"}
