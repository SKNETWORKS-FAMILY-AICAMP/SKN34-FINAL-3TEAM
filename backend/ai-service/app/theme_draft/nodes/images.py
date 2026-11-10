"""generate_images: 미션 그림 5장과 시작·종료 영상 컷 첫 그림 8장을 만들고 그림마다 검토한다.

순서(사용자 결정 2026-11-11):
1. 테마 옷 뭉치 = 기본 뭉치 그림(assets)을 고쳐 테마 옷만 더한 1장. 이후 모든 그림의 첫 참조
2. 시작 1컷 첫 그림(뭉치·인물 참조 없이 글로만) → 인물 기준 그림
3. 나머지(미션 5 + 컷 7)를 [테마 옷 뭉치, 인물 기준 그림] 참조로 동시에(asyncio.gather).
   시작 1·2컷은 뭉치 참조 없음, 시작 3컷은 인물 참조 없음(뭉치 혼자 출동)

review_images는 별도 노드가 아니라 그림마다 그린 직후 돈다(review_missions와 같은 이유: 그림마다
다시 그리기 루프가 독립). 검토 모델이 [그림, 테마 옷 뭉치]를 보고 FAIL이면 그 그림만 사유를 넣어
다시(상한 theme_max_regen, 마감 확인). 미션 그림이 끝내 실패하면 failure IMAGE, 컷 첫 그림이
끝내 실패하면 그 장면 영상만 빼고 warnings(VIDEO). 응답 images의 INTRO·OUTRO는 4번째 컷 첫
그림, MON~FRI는 미션 그림이고 S3에 .png로 올린 키를 담는다.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from langgraph.runtime import Runtime

from app.llm.base import LlmUnavailable
from app.mission_draft.models import Draft
from app.theme_draft.checks import (
    DAYS,
    IMAGE_REVIEW_IDS,
    MISSION_IMAGE_REVIEW_IDS,
    Theme,
    check_review,
)
from app.theme_draft.models import GeneratedImageReview
from app.theme_draft.nodes import DEADLINE_REASON, THEME_CALL_TYPE, ThemeContext, ThemeState, uniq
from app.theme_draft.storage import upload

logger = logging.getLogger(__name__)

CUT_SCENES = ("INTRO", "OUTRO")
CUTS_KEY = {"INTRO": "introCuts", "OUTRO": "outroCuts"}
SCENE_IMAGE = {"INTRO": "INTRO4", "OUTRO": "OUTRO4"}  # 응답 INTRO·OUTRO = 4번째 컷 첫 그림
NO_SETUP = "그림 설정 없음"


def warning(stage: str, item: str, reason: str) -> dict:
    return {"stage": stage, "item": item, "reason": reason}


def image_of(scene: str) -> str:
    """응답 장면(MON·INTRO…) → scene_images 키(MON·INTRO4…)."""
    return SCENE_IMAGE.get(scene, scene)


@dataclass
class Shot:
    """그림 1장 일감."""

    key: str  # MON~FRI, INTRO1~4, OUTRO1~4
    scene_text: str  # 검토 모델에 주는 장면 글
    prompt: Callable[[list[str]], str]  # 사유 목록 → 지시문
    refs: list[bytes]
    ids: tuple[str, ...]
    has_mungchi: bool
    shows_target: bool
    question: str | None = None
    hints: list[str] | None = None
    discovery: str | None = None  # 미션 그림만: 그날 증거 발견 줄


@dataclass
class Drawn:
    image: bytes | None
    bad: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)


async def draw(ctx: ThemeContext, theme: Theme, shot: Shot, outfit: bytes) -> Drawn:
    """그리기 → 검토 → FAIL이면 사유를 넣어 다시(상한·마감). 그림 호출 실패도 사유로 다시."""
    assert ctx.image is not None
    body = ctx.prompt.body
    feedback: list[str] = []
    bad: list[str] = []
    for attempt in range(ctx.settings.theme_max_regen + 1):
        if attempt and not ctx.can_regenerate():
            bad = [*bad, DEADLINE_REASON]
            break
        try:
            image = await ctx.image.edit(
                shot.prompt(feedback),
                shot.refs,
                prompt_version=ctx.prompt.version,
                deadline=ctx.deadline,
            )
            review = await ctx.review_llm.generate(
                system=body.IMAGE_REVIEW_SYSTEM,
                user=body.image_review_user(
                    theme,
                    shot.scene_text,
                    ids=shot.ids,
                    has_mungchi=shot.has_mungchi,
                    shows_target=shot.shows_target,
                    question=shot.question,
                    hints=shot.hints,
                    discovery=shot.discovery,
                ),
                output=GeneratedImageReview,
                call_type=THEME_CALL_TYPE,
                prompt_version=ctx.prompt.version,
                max_tokens=ctx.settings.theme_review_max_tokens,
                deadline=ctx.deadline,
                timeout=ctx.settings.theme_llm_timeout,
                max_retries=ctx.settings.theme_llm_retries,
                images=[image, outfit],
            )
        except LlmUnavailable as exc:  # 안전 정책 거절(400) 등. 사유를 넣어 다시
            bad = [f"IMAGE_CALL {exc.code}"]
            if exc.code == "LLM_DEADLINE_EXCEEDED":
                break
            feedback = uniq([*feedback, *bad])
            continue
        fails, warns, shape = check_review(review.data.model_dump(), shot.ids)
        bad = shape + [f"{x['id']} {x['reason']}" for x in fails]
        if not bad:
            return Drawn(image, [], [f"{x['id']} {x['reason']}" for x in warns])
        feedback = uniq([*feedback, *bad])
    return Drawn(None, bad)


async def dress_mungchi(ctx: ThemeContext, theme: Theme) -> tuple[bytes | None, list[str]]:
    """기본 뭉치 그림 → 테마 옷 뭉치(호출 실패만 다시, 검토 없음)."""
    assert ctx.image is not None
    bad: list[str] = []
    for attempt in range(ctx.settings.theme_max_regen + 1):
        if attempt and not ctx.can_regenerate():
            return None, [*bad, DEADLINE_REASON]
        try:
            image = await ctx.image.edit(
                ctx.prompt.body.outfit_prompt(theme),
                [ctx.mungchi],
                prompt_version=ctx.prompt.version,
                deadline=ctx.deadline,
            )
            return image, []
        except LlmUnavailable as exc:
            bad = [f"IMAGE_CALL {exc.code}"]
            if exc.code == "LLM_DEADLINE_EXCEEDED":
                break
    return None, bad


def cut_shot(
    ctx: ThemeContext, theme: Theme, scene: str, index: int, outfit: bytes, person: bytes | None
) -> Shot:
    body = ctx.prompt.body
    cut = theme[CUTS_KEY[scene]][index - 1]
    has_mungchi = body.cut_has_mungchi(scene, index)
    refs = [outfit] if has_mungchi else []
    if person is not None and body.cut_has_characters(scene, index):
        refs.append(person)
    return Shot(
        key=f"{scene}{index}",
        scene_text=cut["scene"],
        prompt=lambda fb: body.cut_image_prompt(theme, scene, index, cut, fb),
        refs=refs,
        ids=IMAGE_REVIEW_IDS,
        has_mungchi=has_mungchi,
        shows_target=body.cut_shows_target(scene, index),
    )


def mission_shot(
    ctx: ThemeContext, theme: Theme, day: str, draft: Draft, outfit: bytes, person: bytes | None
) -> Shot:
    body = ctx.prompt.body
    d = next(x for x in theme["days"] if x["day"] == day)
    return Shot(
        key=day,
        scene_text=f"{d['place']}. {d['sceneNote']}",
        prompt=lambda fb: body.mission_image_prompt(theme, day, draft, fb),
        refs=[outfit] + ([person] if person is not None else []),
        ids=MISSION_IMAGE_REVIEW_IDS,
        has_mungchi=True,
        shows_target=False,
        question=draft.question,
        hints=[h for h in draft.hints if h.strip()],
        discovery=d.get("discovery"),
    )


async def put_images(
    ctx: ThemeContext, images: dict[str, bytes]
) -> tuple[dict[str, str], dict[str, str]]:
    """장면 그림을 S3에 올림. (장면 → 키, 장면 → 실패 사유)."""
    assert ctx.storage is not None
    storage = ctx.storage

    async def one(scene: str) -> tuple[str, str | None, str | None]:
        try:
            return scene, await upload(storage, ctx.run_id, scene, "png", images[scene]), None
        except Exception as exc:  # boto3·botocore 예외가 여러 종류라 넓게 받음
            logger.exception("theme image upload failed scene=%s", scene)
            return scene, None, f"UPLOAD {type(exc).__name__}"

    keys, errors = {}, {}
    for scene, key, error in await asyncio.gather(*(one(s) for s in images)):
        if key:
            keys[scene] = key
        else:
            errors[scene] = error or "UPLOAD"
    return keys, errors


async def generate_images(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    ctx = runtime.context
    if ctx.image is None or ctx.storage is None:
        return {"media_warnings": [warning("IMAGE", "ALL", NO_SETUP)]}
    theme = state["theme"]
    assert theme is not None
    outfit, bad = await dress_mungchi(ctx, theme)
    if outfit is None:
        return {"failure": {"stage": "IMAGE", "reasons": [f"OUTFIT {r}" for r in bad]}}

    first = await draw(ctx, theme, cut_shot(ctx, theme, "INTRO", 1, outfit, None), outfit)
    person = first.image  # 인물 기준 그림(시작 1컷이 끝내 실패하면 인물 참조 없이)
    shots = [mission_shot(ctx, theme, d, state["drafts"][d], outfit, person) for d in DAYS]
    shots += [
        cut_shot(ctx, theme, scene, i, outfit, person)
        for scene in CUT_SCENES
        for i in range(1, len(theme[CUTS_KEY[scene]]) + 1)
        if (scene, i) != ("INTRO", 1)
    ]
    drawn = dict(
        zip(
            [s.key for s in shots],
            await asyncio.gather(*(draw(ctx, theme, s, outfit) for s in shots)),
            strict=True,
        )
    )
    drawn["INTRO1"] = first

    warnings: list[dict] = []
    failures: list[str] = []
    video_skip: list[str] = []
    for key, result in drawn.items():
        warnings += [warning("IMAGE", key, w) for w in result.warns]
        if result.image is not None:
            continue
        if key in DAYS:
            failures += [f"{key} {r}" for r in result.bad]
        else:
            scene = key[:-1]
            if scene not in video_skip:
                video_skip.append(scene)
            warnings += [warning("VIDEO", scene, f"{key} 그림 {r}") for r in result.bad]

    scene_images = {k: r.image for k, r in drawn.items() if r.image is not None}
    to_upload = {
        scene: scene_images[image_of(scene)]
        for scene in ("INTRO", *DAYS, "OUTRO")
        if image_of(scene) in scene_images
    }
    keys, errors = await put_images(ctx, to_upload)
    for scene, error in errors.items():
        if scene in DAYS:
            failures.append(f"{scene} {error}")
        else:
            warnings.append(warning("IMAGE", scene, error))
    out: ThemeState = {
        "outfit_image": outfit,
        "scene_images": scene_images,
        "image_keys": keys,
        "video_skip": video_skip,
        "media_warnings": warnings,
    }
    if failures:
        out["failure"] = {"stage": "IMAGE", "reasons": failures}
    return out
