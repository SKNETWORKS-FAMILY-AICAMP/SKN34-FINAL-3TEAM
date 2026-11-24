"""generate_dialogue(요일마다 Send로 병렬). 실패한 요일만 사유를 넣어 다시(상한·마감).

끝내 실패하면 그 요일 대화는 빼고 warnings(DIALOGUE)에 남긴다(#437 기준안).
대화는 모델이 쓴다(#782 테마 짜임, 사용자 결정 2026-11-19). 첫 줄(오늘 온 까닭)만 코드 문장을
주인공의 말로 앞에 붙인다(#782 설계 v3, 사용자 결정 2026-11-21). 오늘 온 까닭(dayStep)·
그날 찾은 증거(discovery, 수사 날)·지문을 같이 읽자는 말(missionHook)은 재료로만 준다(단서는 미션
뒤 learning이 보여 줌).

#971: 부탁 날 약속 줄(ASK_PROMISE)과 그 코드 대신 문장(PROMISE_FALLBACK)·약속만 다시 만들기(글
검토 promiseDays·같은 주 약속 PROMISE_SAME)는 뺐다. 이어 가기 날은 보답 약속 없이 단서가 다음
행동으로 간 곳에서 나온다.
"""

from typing import Any

from langgraph.runtime import Runtime

from app.theme_draft.checks import (
    check_dialogue,
    dialogue_lines,
    full_speakers,
    split_long_lines,
    with_first_line,
)
from app.theme_draft.models import GeneratedDialogue
from app.theme_draft.nodes import DEADLINE_REASON, THEME_CALL_TYPE, ThemeContext, ThemeState, uniq


async def generate_dialogue(payload: dict[str, Any], runtime: Runtime[ThemeContext]) -> ThemeState:
    """payload: {day, theme, draft}. 그 요일의 dialogues·dialogue_omitted를 돌려준다."""
    ctx = runtime.context
    day, theme, draft = payload["day"], payload["theme"], payload["draft"]
    feedback: list[str] = []
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
        # 줄여 쓴 등장인물·그날 장소 사람 이름은 원래대로
        out = full_speakers(theme, generated.data.model_dump(), day)
        # #782 설계 v3(사용자 결정 2026-11-21): 첫 줄은 코드가 쓴 오늘 온 까닭을 주인공의 말로
        # 상한을 넘으면 모델의 앞쪽 줄부터 지우고, 예전 저장본은 그 자리에서 코드 문장(v4 B2·B4)
        # #782 설계 v8: 두 말을 한 줄에 붙인 40자 넘는 줄은 문장 경계에서 나눔
        lines = split_long_lines(out.get("lines") or [], ctx.grade)
        out["lines"] = with_first_line(theme, day, lines, ctx.grade)
        bad = check_dialogue(
            theme, day, out, draft, ctx.grade, ctx.settings.followup_example_overlap_chars
        )
        if not bad:
            return {"dialogues": {day: dialogue_lines(out)}, "dialogue_omitted": {day: []}}
        feedback = uniq([*feedback, *bad])
    return {"dialogues": {day: None}, "dialogue_omitted": {day: bad}}
