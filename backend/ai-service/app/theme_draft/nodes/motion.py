"""generate_motion: 그림이 있는 장면마다 생성 모델이 그림을 보고 움직임 값을 정한다.

- speakers는 그 요일 대화 화자(뭉치·등장인물, 찾는 대상 제외)만. 시작·종료는 대화가 없어 비움
- 시작·종료 captions는 영상이 있을 때만(컷 문구, 녹아드는 전환 경계 기준 시각)
- 상한 밖 숫자는 checks.motion이 맞추고 맞춘 항목마다 warnings(MOTION)
- 움직임 LLM이 실패하면 그 장면 움직임만 빼고 경고
"""

import asyncio

from langgraph.runtime import Runtime
from pydantic import ValidationError

from app.llm.base import LlmUnavailable
from app.llm.media import xfade_caption_times
from app.theme_draft.checks import DAYS, Theme, dialogue_speakers, motion
from app.theme_draft.models import GeneratedMotion, ThemeMotion
from app.theme_draft.nodes import THEME_CALL_TYPE, ThemeContext, ThemeState
from app.theme_draft.nodes.images import CUTS_KEY, image_of, warning
from app.theme_draft.storage import SCENES


def scene_text(theme: Theme, scene: str) -> str:
    if scene in DAYS:
        d = next(x for x in theme["days"] if x["day"] == scene)
        return f"{d['place']}. {d['sceneNote']}"
    return theme[CUTS_KEY[scene]][-1]["scene"]


def captions_of(ctx: ThemeContext, theme: Theme, scene: str, has_video: bool) -> list[dict]:
    if scene in DAYS or not has_video:
        return []
    cuts = theme[CUTS_KEY[scene]]
    times = xfade_caption_times(ctx.settings.theme_video_cut_seconds)
    return [
        {"start": s, "end": e, "text": c["caption"]} for (s, e), c in zip(times, cuts, strict=False)
    ]


async def scene_motion(
    ctx: ThemeContext, state: ThemeState, scene: str
) -> tuple[dict | None, list[dict]]:
    theme = state["theme"]
    assert theme is not None
    lines = (state.get("dialogues") or {}).get(scene) if scene in DAYS else None
    speakers = dialogue_speakers(theme, lines)
    image = (state.get("scene_images") or {})[image_of(scene)]
    try:
        generated = await ctx.llm.generate(
            system=ctx.prompt.body.MOTION_SYSTEM,
            user=ctx.prompt.body.motion_user(theme, scene, scene_text(theme, scene), speakers),
            output=GeneratedMotion,
            call_type=THEME_CALL_TYPE,
            prompt_version=ctx.prompt.version,
            max_tokens=ctx.settings.theme_motion_max_tokens,
            deadline=ctx.deadline,
            timeout=ctx.settings.theme_llm_timeout,
            max_retries=ctx.settings.theme_llm_retries,
            images=[image],
        )
    except LlmUnavailable as exc:
        return None, [warning("MOTION", scene, f"MOTION_CALL {exc.code}")]
    captions = captions_of(ctx, theme, scene, scene in (state.get("video_keys") or {}))
    value, notes = motion(generated.data.model_dump(), speakers, captions)
    warnings = [warning("MOTION", scene, n) for n in notes]
    try:
        ThemeMotion.model_validate(value)
    except ValidationError as exc:  # 맞춘 뒤에도 형식 밖이면 그 장면만 뺌
        return None, [*warnings, warning("MOTION", scene, f"MOTION_SHAPE {exc.error_count()}개")]
    return value, warnings


async def generate_motion(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    ctx = runtime.context
    scenes = [s for s in SCENES if s in (state.get("image_keys") or {})]
    results = await asyncio.gather(*(scene_motion(ctx, state, s) for s in scenes))
    motions = {s: value for s, (value, _) in zip(scenes, results, strict=True) if value}
    return {"motions": motions, "media_warnings": [w for _, ws in results for w in ws]}
