"""generate_images: 미션 그림 5장과 시작·종료 영상 컷 첫 그림 8장을 만들고 그림마다 검토한다.

순서(사용자 결정 2026-11-11, #779에서 2를 바꿈):
1. 테마 옷 뭉치 = 기본 뭉치 그림(assets)을 고쳐 테마 옷만 더한 1장. 뭉치가 나오는 그림의 첫 참조이고
   모든 그림 검토의 비교 그림
2. 인물 기준 그림 = 등장인물만 민무늬 배경에 그린 1장(#779, 호출 실패만 다시, 검토 없음). 예전에는
   시작 1컷 장면을 인물 기준으로 써서 그림 모델이 배경·구도까지 따라 그려 컷마다 같은 장면이 됐음.
   끝내 못 그리면 예전처럼 시작 1컷을 먼저 그려 인물 기준으로 씀
3. 미션 5 + 컷 8을 [테마 옷 뭉치, 인물 기준 그림] 참조로 동시에(asyncio.gather).
   시작 1·2컷은 뭉치 참조 없음, 시작 3컷은 인물 참조 없음(뭉치 혼자 출동).
   #779 6컷(B안): 앞 컷을 잇는 컷(시작 2·3·6 ← 1, 종료 5 ← 3, 6 ← 5)은 그 앞 컷이 끝난 뒤 그
   그림을 마지막 참고 그림으로 받아 장소·가구·물건 상태를 잇고, 검토도 그 그림을 보며 FLOW를 더함

그림 대역(IMAGE_PROVIDER=fake)이면 검토를 부르지 않고 통과로 보며 warnings에 IMAGE ALL 한 줄(#716).

review_images는 별도 노드가 아니라 그림마다 그린 직후 돈다(review_missions와 같은 이유: 그림마다
다시 그리기 루프가 독립). 검토 모델이 [그림, 테마 옷 뭉치]를 보고 FAIL이면 그 그림만 사유를 넣어
다시(상한 theme_max_regen, 마감 확인). 미션 그림이 끝내 실패하면 failure IMAGE, 컷 첫 그림이
끝내 실패하면 그 장면 영상만 빼고 warnings(VIDEO). 응답 images의 INTRO·OUTRO는 4번째 컷 첫
그림, MON~FRI는 미션 그림이고 S3에 .png로 올린 키를 담는다.

부분 다시 생성 재료(#537): 테마 옷 뭉치(OUTFIT)와 컷 첫 그림 8장(INTRO1~4·OUTRO1~4)도 같은 실행
폴더에 올리고 키를 assets에 둔다(인물 기준 PERSON = 인물만 그린 그림 CHARS, 없으면 예전처럼 처음
생성의 INTRO1). 부분 다시 생성은
redo_images만 다시 그리고 나머지는 원래 키를 그대로 둔다. 시작·종료 컷 그림이 하나라도 끝내 실패하면
그 장면은 원래 그림·영상·움직임을 그대로 두고 warnings(IMAGE)(장면 단위로 바꿈). 미션 그림이 끝내
실패하면 처음 생성처럼 failure IMAGE.
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
    FLOW_IMAGE_REVIEW_IDS,
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
NO_SETUP = "그림 설정 없음"
# 그림 대역(IMAGE_PROVIDER=fake)은 시험·측정용 단색 그림이라 검토 모델에 보내지 않는다(#716).
# 보내면 결함이 아닌 대역 모양("단색이라 뭉치가 안 보임") 때문에 실패·다시 그리기가 생겨
# 비용·시간·결과가 왜곡됨
FAKE_REVIEW_SKIPPED = "그림 대역이라 검토를 건너뜀"
KEPT_NOTE = "원래 그림·영상 유지"  # 부분 다시 생성에서 컷 그림이 끝내 실패한 장면(#537)
ASSET_NOTE = "부분 다시 생성 재료"  # 재료 그림 업로드 실패(그 대상만 다시 만들 수 없게 됨)


def warning(stage: str, item: str, reason: str) -> dict:
    return {"stage": stage, "item": item, "reason": reason}


def image_of(scene: str, theme: Theme) -> str:
    """응답 장면(MON·INTRO…) → scene_images 키. INTRO·OUTRO는 마지막 컷 첫 그림(예전 4컷 INTRO4,
    #779 6컷 INTRO6)."""
    if scene not in CUTS_KEY:
        return scene
    return f"{scene}{len(theme.get(CUTS_KEY[scene]) or []) or 4}"


@dataclass
class Shot:
    """그림 1장 일감."""

    key: str  # MON~FRI, INTRO1~n, OUTRO1~n(#779 새 테마 6컷)
    scene_text: str  # 검토 모델에 주는 장면 글
    prompt: Callable[[list[str]], str]  # 사유 목록 → 지시문
    refs: list[bytes]
    ids: tuple[str, ...]
    has_mungchi: bool
    shows_target: bool
    question: str | None = None
    hints: list[str] | None = None
    discovery: str | None = None  # 미션 그림만: 그날 증거 발견 줄
    evidence: str | None = None  # 미션 그림만: 그날 증거 종류(TRACE·SIGHTING·RECORD)
    answer_allowed: bool = False  # 종료 콘티 컷만 정답(장소·동물) 공개 허용
    # 잇는 앞 컷(#779 B안): 그 컷 키(INTRO1 등)·장면 글·앞 컷 그림을 받을 때의 지시문
    follows: str | None = None
    follow_scene: str | None = None
    follow_prompt: Callable[[list[str]], str] | None = None


@dataclass
class Drawn:
    image: bytes | None
    bad: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)


async def draw(
    ctx: ThemeContext,
    theme: Theme,
    shot: Shot,
    outfit: bytes,
    seed: list[str] | None = None,
    prev: bytes | None = None,
) -> Drawn:
    """그리기 → 검토 → FAIL이면 사유를 넣어 다시(상한·마감). 그림 호출 실패도 사유로 다시.

    prev(잇는 앞 컷 그림, #779 B안)가 있으면 마지막 참고 그림으로 넣고 검토도 세 번째 그림으로
    보며 FLOW 항목을 더한다. 앞 컷 그림이 없으면(끝내 실패) 예전처럼 따로 그린다.
    """
    assert ctx.image is not None
    body = ctx.prompt.body
    follow = prev is not None and shot.follow_prompt is not None
    prompt = shot.follow_prompt if follow and shot.follow_prompt else shot.prompt
    refs = [*shot.refs, prev] if follow and prev is not None else shot.refs
    ids = FLOW_IMAGE_REVIEW_IDS if follow else shot.ids
    review_images = [outfit, prev] if follow and prev is not None else [outfit]
    feedback: list[str] = list(seed or [])  # 요청 previousFailures의 IMAGE 사유(처음부터)
    bad: list[str] = []
    for attempt in range(ctx.settings.theme_max_regen + 1):
        if attempt and not ctx.can_regenerate():
            bad = [*bad, DEADLINE_REASON]
            break
        try:
            image = await ctx.image.edit(
                prompt(feedback),
                refs,
                prompt_version=ctx.prompt.version,
                deadline=ctx.deadline,
            )
            if ctx.settings.image_provider == "fake":
                return Drawn(image)  # 대역 그림은 검토하지 않음(#716)
            review = await ctx.review_llm.generate(
                system=body.IMAGE_REVIEW_SYSTEM,
                user=body.image_review_user(
                    theme,
                    shot.scene_text,
                    ids=ids,
                    has_mungchi=shot.has_mungchi,
                    shows_target=shot.shows_target,
                    question=shot.question,
                    hints=shot.hints,
                    discovery=shot.discovery,
                    evidence=shot.evidence,
                    answer_allowed=shot.answer_allowed,
                    previous_scene=shot.follow_scene if follow else None,
                ),
                output=GeneratedImageReview,
                call_type=THEME_CALL_TYPE,
                prompt_version=ctx.prompt.version,
                max_tokens=ctx.settings.theme_review_max_tokens,
                deadline=ctx.deadline,
                timeout=ctx.settings.theme_llm_timeout,
                max_retries=ctx.settings.theme_llm_retries,
                images=[image, *review_images],
            )
        except LlmUnavailable as exc:  # 안전 정책 거절(400) 등. 사유를 넣어 다시
            bad = [f"IMAGE_CALL {exc.code}"]
            if exc.code == "LLM_DEADLINE_EXCEEDED":
                break
            feedback = uniq([*feedback, *bad])
            continue
        fails, warns, shape = check_review(review.data.model_dump(), ids)
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


async def draw_characters(ctx: ThemeContext, theme: Theme) -> bytes | None:
    """인물 기준 그림(#779): 등장인물만 민무늬 배경에(호출 실패만 다시, 검토 없음).

    못 그리면 None(예전처럼 시작 1컷을 인물 기준으로).
    """
    assert ctx.image is not None
    for attempt in range(ctx.settings.theme_max_regen + 1):
        if attempt and not ctx.can_regenerate():
            return None
        try:
            return await ctx.image.edit(
                ctx.prompt.body.characters_prompt(theme),
                [],
                prompt_version=ctx.prompt.version,
                deadline=ctx.deadline,
            )
        except LlmUnavailable as exc:
            logger.warning("theme characters image failed %s", exc.code)
            if exc.code == "LLM_DEADLINE_EXCEEDED":
                break
    return None


def cut_shot(
    ctx: ThemeContext, theme: Theme, scene: str, index: int, outfit: bytes, person: bytes | None
) -> Shot:
    body = ctx.prompt.body
    cut = theme[CUTS_KEY[scene]][index - 1]
    n = len(theme[CUTS_KEY[scene]])
    has_mungchi = body.cut_has_mungchi(scene, index, n)
    refs = [outfit] if has_mungchi else []
    if person is not None and body.cut_has_characters(scene, index, n):
        refs.append(person)
    k = body.cut_follows(scene, index, n)
    prev_scene = theme[CUTS_KEY[scene]][k - 1]["scene"] if k else None
    return Shot(
        key=f"{scene}{index}",
        scene_text=cut["scene"],
        prompt=lambda fb: body.cut_image_prompt(theme, scene, index, cut, fb),
        refs=refs,
        ids=IMAGE_REVIEW_IDS,
        has_mungchi=has_mungchi,
        shows_target=body.cut_shows_target(theme, scene, index),
        answer_allowed=body.cut_reveals_answer(scene),
        follows=f"{scene}{k}" if k else None,
        follow_scene=prev_scene,
        follow_prompt=(
            (lambda fb: body.cut_image_prompt(theme, scene, index, cut, fb, prev_scene))
            if prev_scene is not None
            else None
        ),
    )


async def draw_all(
    ctx: ThemeContext,
    theme: Theme,
    shots: list[Shot],
    outfit: bytes,
    seed_of: Callable[[str], list[str]],
    ready: dict[str, bytes] | None = None,
) -> dict[str, Drawn]:
    """그림 일감을 동시에 그린다. 앞 컷을 잇는 컷(#779 B안)은 그 컷 일감이 끝날 때까지 기다려 그
    그림을 참고 그림으로 받는다(일감에 없으면 ready의 그림). 앞 컷이 끝내 실패하면 따로 그린다."""
    tasks: dict[str, asyncio.Task[Drawn]] = {}
    have = ready or {}

    async def one(shot: Shot) -> Drawn:
        prev: bytes | None = None
        if shot.follows in tasks:
            prev = (await tasks[shot.follows]).image
        elif shot.follows:
            prev = have.get(shot.follows)
        return await draw(ctx, theme, shot, outfit, seed_of(shot.key), prev)

    for shot in shots:  # 일감을 모두 만든 뒤에 돌기 시작해 잇는 컷이 앞 컷 일감을 찾음
        tasks[shot.key] = asyncio.create_task(one(shot))
    results = await asyncio.gather(*tasks.values())
    return dict(zip(tasks, results, strict=True))


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
        # 손에 든 것(대상이 늘 보이는 종류)·시간 탐정은 참, 그 밖은 거짓(#634, 그림 지시와 같게)
        shows_target=body.mission_shows_target(theme),
        question=draft.question,
        hints=[h for h in draft.hints if h.strip()],
        discovery=d.get("discovery"),
        evidence=body.evidence_kind(d),
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
    partial = bool(state.get("partial"))
    redo = set(state.get("redo_images") or [])
    if partial and not redo:
        return {}  # 영상만 다시 만듦: 그림은 원래 그대로(#537)
    theme = state["theme"]
    assert theme is not None
    outfit = state.get("outfit_image") if partial else None
    new_assets: dict[str, bytes] = {}
    if outfit is None:  # 처음 생성, 또는 원래 결과에 그림이 없던 부분 다시 생성
        outfit, bad = await dress_mungchi(ctx, theme)
        if outfit is None:
            return {"failure": {"stage": "IMAGE", "reasons": [f"OUTFIT {r}" for r in bad]}}
        new_assets["OUTFIT"] = outfit

    image_seed = state.get("image_seed") or {}

    def seed_of(key: str) -> list[str]:
        return [*image_seed.get(key, []), *image_seed.get("*", [])]

    def cut_range(scene: str) -> range:
        return range(1, len(theme[CUTS_KEY[scene]]) + 1)

    if partial:
        # 인물 기준은 처음 생성의 것 그대로(다른 장면과 인물 모습을 맞춤). 인물만 그린 그림(CHARS,
        # #779)이면 시작 1컷도 그 그림을 참조, 예전 결과(인물 기준 = 시작 1컷)면 시작 1컷은 처음
        # 생성처럼 참조 없이 글로만 그림
        person = state.get("person_image")
        chars_person = "CHARS" in (state.get("assets") or {})
        shots = [
            mission_shot(ctx, theme, d, state["drafts"][d], outfit, person)
            for d in DAYS
            if d in redo
        ]
        shots += [
            cut_shot(
                ctx,
                theme,
                scene,
                i,
                outfit,
                None if (scene, i) == ("INTRO", 1) and not chars_person else person,
            )
            for scene in CUT_SCENES
            for i in cut_range(scene)
            if f"{scene}{i}" in redo
        ]
        drawn = await draw_all(ctx, theme, shots, outfit, seed_of, state.get("scene_images") or {})
    else:
        chars = await draw_characters(ctx, theme)
        first: Drawn | None = None
        if chars is not None:
            new_assets["CHARS"] = chars
            person: bytes | None = chars
        else:  # 예전 방식: 시작 1컷(글로만)을 먼저 그려 인물 기준으로
            first = await draw(
                ctx,
                theme,
                cut_shot(ctx, theme, "INTRO", 1, outfit, None),
                outfit,
                seed_of("INTRO1"),
            )
            person = first.image  # 시작 1컷이 끝내 실패하면 인물 참조 없이
        shots = [mission_shot(ctx, theme, d, state["drafts"][d], outfit, person) for d in DAYS]
        shots += [
            cut_shot(ctx, theme, scene, i, outfit, person)
            for scene in CUT_SCENES
            for i in cut_range(scene)
            if first is None or (scene, i) != ("INTRO", 1)
        ]
        drawn = await draw_all(
            ctx,
            theme,
            shots,
            outfit,
            seed_of,
            {"INTRO1": first.image} if first is not None and first.image is not None else None,
        )
        if first is not None:
            drawn["INTRO1"] = first

    warnings: list[dict] = (
        [warning("IMAGE", "ALL", FAKE_REVIEW_SKIPPED)]
        if ctx.settings.image_provider == "fake"
        else []
    )
    failures: list[str] = []
    video_skip: list[str] = []  # 처음 생성: 컷 그림이 끝내 실패한 장면은 영상을 빼고 경고
    kept: list[
        str
    ] = []  # 부분 다시 생성: 컷 그림이 하나라도 실패한 장면은 원래 그림·영상을 그대로 둠
    for key, result in drawn.items():
        warnings += [warning("IMAGE", key, w) for w in result.warns]
        if result.image is not None:
            continue
        if key in DAYS:
            failures += [f"{key} {r}" for r in result.bad]
            continue
        scene = key[:-1]
        if partial:
            kept += [] if scene in kept else [scene]
            warnings += [warning("IMAGE", key, f"그림 {r}, {KEPT_NOTE}") for r in result.bad]
        else:
            video_skip += [] if scene in video_skip else [scene]
            warnings += [warning("VIDEO", scene, f"{key} 그림 {r}") for r in result.bad]

    new_images = {
        k: r.image for k, r in drawn.items() if r.image is not None and k[:-1] not in kept
    }
    scene_images = {**(state.get("scene_images") or {}), **new_images}
    to_upload = {
        scene: new_images[image_of(scene, theme)]
        for scene in ("INTRO", *DAYS, "OUTRO")
        if image_of(scene, theme) in new_images
    }
    # 부분 다시 생성 재료(#537): 새로 만든 테마 옷 뭉치와 컷 첫 그림
    to_upload |= {k: v for k, v in new_images.items() if k not in DAYS} | new_assets
    keys, errors = await put_images(ctx, to_upload)
    for name, error in errors.items():
        if name in DAYS:
            failures.append(f"{name} {error}")
        elif name in ("INTRO", "OUTRO"):
            warnings.append(warning("IMAGE", name, error))
        else:
            warnings.append(warning("IMAGE", name, f"{error} ({ASSET_NOTE})"))
    scene_keys = {k: v for k, v in keys.items() if k in ("INTRO", *DAYS, "OUTRO")}
    assets = {
        **(state.get("assets") or {}),
        **{k: v for k, v in keys.items() if k not in scene_keys},
    }
    if not partial and "CHARS" in assets:  # #779 인물만 그린 그림
        assets["PERSON"] = assets["CHARS"]
    elif not partial and "INTRO1" in assets:
        assets["PERSON"] = assets["INTRO1"]
    out: ThemeState = {
        "outfit_image": outfit,
        "scene_images": scene_images,
        "image_keys": {**(state.get("image_keys") or {}), **scene_keys},
        "assets": assets,
        "video_skip": video_skip,
        "media_warnings": warnings,
    }
    if partial and kept:
        out["redo_videos"] = [s for s in state.get("redo_videos") or [] if s not in kept]
        out["redo_motions"] = [s for s in state.get("redo_motions") or [] if s not in kept]
    if failures:
        out["failure"] = {"stage": "IMAGE", "reasons": failures}
    return out
