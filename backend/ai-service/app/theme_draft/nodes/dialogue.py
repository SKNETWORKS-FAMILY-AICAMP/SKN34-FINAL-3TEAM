"""generate_dialogue(요일마다 Send로 병렬). 실패한 요일만 사유를 넣어 다시(상한·마감).

끝내 실패하면 그 요일 대화는 빼고 warnings(DIALOGUE)에 남긴다(#437 기준안).
대화는 모델이 쓴다(#782 테마 짜임, 사용자 결정 2026-11-19). 첫 줄(오늘 온 까닭)만 코드 문장을
주인공의 말로 앞에 붙인다(#782 설계 v3, 사용자 결정 2026-11-21). 오늘 온 까닭(dayStep)·
그날 찾은 증거(discovery)·증거의 어느 부분으로 활동할지(missionHook)는 재료로만 준다(단서는 미션 뒤
learning이 보여 줌).

#782 설계 v10: 남은 사유가 ASK_PROMISE뿐이면 대화를 빼지 않고 약속 줄을 코드 문장(ask_promise)
으로 바꿔 넣고 경고(PROMISE_FALLBACK, 측정에서 셈). 같은 주 같은 말을 다시 만들던
dedupe_dialogues는 뺌(v11, v9로).
#782 설계 v12(사용자 결정 2026-11-23 "다시 써도 계속 틀리는 대화는 코드로"): 약속이 틀리면 LLM이
다시 쓰고, 마지막 시도(상한·마감)에도 남은 사유가 약속뿐일 때만 코드 문장(v11의 시도마다 곧바로
대신 넣기는 뺌). 글 검토가 약속 줄만 틀렸다고 한 날·단서를 고쳐 약속 감각이 바뀐 날은 그 요일
대화만 다시 만든다(payload seed에 사유, 줄거리를 다시 만들지 않음).
"""

from typing import Any

from langgraph.runtime import Runtime

from app.mission_draft.models import Draft
from app.theme_draft.checks import (
    DAYS,
    check_dialogue,
    dialogue_lines,
    full_speakers,
    promise_sense,
    put_promise,
    split_long_lines,
    theme_day,
    with_first_line,
)
from app.theme_draft.models import GeneratedDialogue
from app.theme_draft.nodes import DEADLINE_REASON, THEME_CALL_TYPE, ThemeContext, ThemeState, uniq

FALLBACK = "PROMISE_FALLBACK"  # 약속 줄을 코드 문장으로 바꿔 넣음(#782 설계 v10, 경고 사유 앞말)


async def generate_dialogue(payload: dict[str, Any], runtime: Runtime[ThemeContext]) -> ThemeState:
    """payload: {day, theme, draft, seed?}. 그 요일의 dialogues·dialogue_omitted를 돌려준다.
    seed는 처음부터 넣을 사유(#782 설계 v12: 글 검토가 약속 줄만 틀렸다고 한 날)."""
    ctx = runtime.context
    day, theme, draft = payload["day"], payload["theme"], payload["draft"]
    feedback: list[str] = list(payload.get("seed") or [])
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
        # 줄여 쓴 등장인물·그날 돕는 사람 이름은 원래대로
        out = full_speakers(theme, generated.data.model_dump(), day)
        # #782 설계 v3(사용자 결정 2026-11-21): 첫 줄은 코드가 쓴 오늘 온 까닭을 주인공의 말로
        # 상한을 넘으면 모델의 앞쪽 줄부터 지우고, 예전 저장본은 그 자리에서 코드 문장(v4 B2·B4)
        # #782 설계 v8: 부탁+약속을 한 줄에 붙인 40자 넘는 줄은 문장 경계에서 나눔
        lines = split_long_lines(out.get("lines") or [], ctx.grade)
        out["lines"] = with_first_line(theme, day, lines, ctx.grade)
        bad = check_dialogue(
            theme, day, out, draft, ctx.grade, ctx.settings.followup_example_overlap_chars
        )
        if not bad:
            return {"dialogues": {day: dialogue_lines(out)}, "dialogue_omitted": {day: []}}
        # #782 설계 v12: 마지막 시도(상한·마감)에도 남은 사유가 약속뿐일 때만 코드 문장으로 대신
        last = attempt == ctx.settings.theme_max_regen or not ctx.can_regenerate()
        if last and (fixed := promise_fallback(ctx, day, theme, draft, out, bad)):
            return {"dialogues": {day: fixed[0]}, "dialogue_omitted": {day: fixed[1]}}
        feedback = uniq([*feedback, *bad])
    if keep := payload.get("keep"):  # #782 설계 v13: 같은 주 약속 다시 만들기는 원래 대화로
        return {"dialogues": {day: keep}, "dialogue_omitted": {day: []}}
    return {"dialogues": {day: None}, "dialogue_omitted": {day: bad}}


def promise_fallback(
    ctx: ThemeContext, day: str, theme: dict, draft: Draft, out: dict, bad: list[str]
) -> tuple[list[dict], list[str]] | None:
    """남은 사유(마감 빼고)가 ASK_PROMISE뿐이면 약속 줄을 코드 문장으로 바꿔 넣는다(#782 설계 v10
    ⑤ 7차 대화가 통째로 빠진 2건, v12부터 마지막 시도에만). 다른 사유가 같이 남거나 바꿔 넣은
    대화가 검사에 걸리면 None. (대화 줄, [PROMISE_FALLBACK 경고])."""
    reasons = [r for r in bad if r != DEADLINE_REASON]
    if not reasons or not all(r.startswith("ASK_PROMISE") for r in reasons):
        return None
    helper = str(theme_day(theme, day).get("helper") or "").strip()
    sentence = ctx.prompt.body.ask_promise(theme, theme_day(theme, day)) + "."
    lines = put_promise(dialogue_lines(out), helper, sentence, ctx.grade)
    if lines is None:
        return None
    fixed = {**out, "lines": lines}
    if check_dialogue(
        theme, day, fixed, draft, ctx.grade, ctx.settings.followup_example_overlap_chars
    ):
        return None
    return dialogue_lines(fixed), [f"{FALLBACK} {day} 약속 줄을 코드 문장으로 바꿈('{sentence}')"]


def promise_redo(ctx: ThemeContext, state: ThemeState, theme: dict) -> dict[str, list[str]]:
    """글 검토 뒤 단서를 고친 길(fix_clues): 고친 날의 약속 감각(promise_sense)이 바뀌어 그날 대화의
    약속이 틀리면 {요일: ASK_PROMISE 사유}(#782 설계 v10). #782 설계 v12: 코드 문장으로 바꿔 넣지
    않고 그 요일 대화를 LLM이 다시 쓴다(graph after_fix_clues → generate_dialogue)."""
    old = state["theme"]
    assert old is not None
    dialogues = state.get("dialogues") or {}
    overlap = ctx.settings.followup_example_overlap_chars
    todo: dict[str, list[str]] = {}
    for day in DAYS:
        lines = dialogues.get(day)
        if not lines or promise_sense(old, day) == promise_sense(theme, day):
            continue
        draft = state["drafts"][day]
        bad = check_dialogue(theme, day, {"lines": lines}, draft, ctx.grade, overlap)
        if promise := [r for r in bad if r.startswith("ASK_PROMISE")]:
            todo[day] = promise
    return todo
