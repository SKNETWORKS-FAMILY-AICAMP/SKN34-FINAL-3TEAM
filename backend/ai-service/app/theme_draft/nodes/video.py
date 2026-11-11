"""generate_videos: 시작·종료 영상(각 4컷)을 만들고 컷마다 검토한 뒤 녹아드는 전환으로 잇는다.

사용자 결정 2026-11-11:
- 컷 길이 4·6·8·6초(theme_video_cut_seconds), 첫 그림(컷 첫 그림)만 고정. 끝 그림까지 고정하면
  비슷한 두 그림 사이를 억지로 이어 움직임이 흐물거리고 배경이 같아짐(실측)
- 컷은 동시에 만들고, 검토 모델이 2초마다 뽑은 장면을 보고 판정(MORPH·ANSWER_HINT·TEXT·SAFETY).
  실패한 컷만 사유를 넣어 다시(상한 theme_max_regen, 마감 확인). 끝내 실패한 컷이 있으면 그 장면
  영상만 빼고 warnings(VIDEO)
- 0.5초 겹쳐 녹아드는 전환(ffmpeg xfade)으로 이어 S3 .mp4
- 영상 클라이언트가 없거나(THEME_VIDEO_ENABLED=false) 마감까지 theme_video_timeout + 60초가 안
  남으면 건너뛰고 경고. THEME_VIDEO 사용량은 core enum 전이라 이벤트 없이 로그만
"""

import asyncio
import logging
import subprocess

from langgraph.runtime import Runtime

from app.llm.base import LlmUnavailable
from app.llm.media import freeze_spans, join_xfade, trim_clip, video_frames
from app.theme_draft.checks import VIDEO_REVIEW_IDS, Theme, check_review
from app.theme_draft.models import GeneratedVideoReview
from app.theme_draft.nodes import DEADLINE_REASON, THEME_CALL_TYPE, ThemeContext, ThemeState, uniq
from app.theme_draft.nodes.images import CUT_SCENES, CUTS_KEY, warning
from app.theme_draft.storage import upload

logger = logging.getLogger(__name__)

VIDEO_OFF = "영상 설정 꺼짐"
VIDEO_DEADLINE = "마감까지 남은 시간이 부족해 영상을 건너뜀"
FRAME_EVERY = 1.0  # 검토 장면 간격(초). 2초 간격 4장으로는 사이의 사라짐·변형을 놓쳤음(실측)
FRAME_COUNT = 8  # 8초 컷이면 0~7초
FREEZE_FAIL = 0.5  # 컷 중간에 이보다 오래 멈추면 그 컷을 다시 만듦(초, 기준안)
MIN_KEEP = 0.6  # 앞뒤 정지 화면을 잘라도 요청 길이의 이 비율은 남아야 함
DEADLINE_MARGIN = 60.0  # 이어 붙이기·올리기·움직임 몫


def cut_freezes(clip: bytes, seconds: float) -> tuple[bytes, float, list[str]]:
    """(앞뒤 정지 화면을 잘라 낸 컷, 실제 길이, 실패 사유). 중간 멈춤이 FREEZE_FAIL초를 넘거나
    잘라 낸 뒤 너무 짧으면 FREEZE 사유(그 컷을 다시 만듦)."""
    duration, spans = freeze_spans(clip)
    duration = duration or float(seconds)
    start, end = 0.0, duration
    middle = []
    for s, e in spans:
        if s <= 0.05:
            start = max(start, e)
        elif e >= duration - 0.05:
            end = min(end, s)
        elif e - s >= FREEZE_FAIL:
            middle.append((s, e))
    if middle:
        return (
            clip,
            duration,
            ["FREEZE " + ", ".join(f"{s:.1f}~{e:.1f}초에 화면이 멈춤" for s, e in middle)],
        )
    if end - start < MIN_KEEP * seconds:
        return clip, duration, [f"FREEZE 움직이는 부분이 {end - start:.1f}초뿐"]
    if start > 0 or end < duration:
        return trim_clip(clip, start, end), round(end - start, 3), []
    return clip, duration, []


async def film(
    ctx: ThemeContext, theme: Theme, scene: str, index: int, first: bytes, seconds: int
) -> tuple[bytes | None, list[str], list[str], float]:
    """컷 1개: 생성 → 멈춤 확인(앞뒤 정지 화면 잘라 냄) → 장면 뽑기 → 검토 → FAIL이면 사유를 넣어
    다시(상한·마감).

    (영상, 끝내 실패한 사유, 통과한 검토의 WARN 사유, 실제 길이).
    """
    assert ctx.video is not None
    body = ctx.prompt.body
    cut = theme[CUTS_KEY[scene]][index - 1]
    shows_target = body.cut_shows_target(scene, index)
    feedback: list[str] = []
    bad: list[str] = []
    for attempt in range(ctx.settings.theme_max_regen + 1):
        if attempt and not ctx.can_regenerate():
            bad = [*bad, DEADLINE_REASON]
            break
        try:
            clip = await ctx.video.generate(
                body.video_prompt(theme, scene, index, cut, feedback),
                first,
                seconds=seconds,
                deadline=ctx.deadline,
                negative=body.VIDEO_NEGATIVE,
            )
            clip, length, frozen = await asyncio.to_thread(cut_freezes, clip, seconds)
            if frozen:
                bad = frozen
                feedback = uniq([*feedback, *bad])
                continue
            frames = await asyncio.to_thread(video_frames, clip, FRAME_EVERY, FRAME_COUNT)
            review = await ctx.review_llm.generate(
                system=body.VIDEO_REVIEW_SYSTEM,
                user=body.video_review_user(
                    theme,
                    cut,
                    shows_target,
                    body.cut_has_mungchi(scene, index),
                    body.cut_reveals_answer(scene),
                ),
                output=GeneratedVideoReview,
                call_type=THEME_CALL_TYPE,
                prompt_version=ctx.prompt.version,
                max_tokens=ctx.settings.theme_review_max_tokens,
                deadline=ctx.deadline,
                timeout=ctx.settings.theme_llm_timeout,
                max_retries=ctx.settings.theme_llm_retries,
                images=[first, *frames],
            )
        except LlmUnavailable as exc:
            bad = [f"VIDEO_CALL {exc.code}"]
            if exc.code == "LLM_DEADLINE_EXCEEDED":
                break
            feedback = uniq([*feedback, *bad])
            continue
        except (RuntimeError, subprocess.SubprocessError) as exc:  # 장면 뽑기(ffmpeg) 실패
            bad = [f"VIDEO_FRAMES {type(exc).__name__}"]
            continue
        fails, warns, shape = check_review(review.data.model_dump(), VIDEO_REVIEW_IDS)
        bad = shape + [f"{x['id']} {x['reason']}" for x in fails]
        if not bad:
            return clip, [], [f"{x['id']} {x['reason']}" for x in warns], length
        feedback = uniq([*feedback, *bad])
    return None, bad, [], 0.0


async def join_and_put(
    ctx: ThemeContext, scene: str, clips: list[bytes], durations: list[float]
) -> tuple[str | None, str | None]:
    """(S3 키, 실패 사유)."""
    assert ctx.storage is not None
    try:
        joined = await asyncio.to_thread(join_xfade, clips, durations)
    except (RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        logger.exception("theme video join failed scene=%s", scene)
        return None, f"JOIN {type(exc).__name__}"
    try:
        return await upload(ctx.storage, ctx.run_id, scene, "mp4", joined), None
    except Exception as exc:  # boto3·botocore 예외가 여러 종류라 넓게 받음
        logger.exception("theme video upload failed scene=%s", scene)
        return None, f"UPLOAD {type(exc).__name__}"


async def generate_videos(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    ctx = runtime.context
    if ctx.video is None:
        return {"media_warnings": [warning("VIDEO", "ALL", VIDEO_OFF)]}
    if ctx.deadline - ctx.clock() < ctx.settings.theme_video_timeout + DEADLINE_MARGIN:
        return {"media_warnings": [warning("VIDEO", "ALL", VIDEO_DEADLINE)]}
    theme = state["theme"]
    assert theme is not None
    durations = list(ctx.settings.theme_video_cut_seconds)
    images = state.get("scene_images") or {}
    warnings: list[dict] = []
    scenes = []
    for scene in CUT_SCENES:
        if scene in (state.get("video_skip") or []):
            continue  # 컷 그림 실패 경고는 generate_images가 남김
        if len(theme[CUTS_KEY[scene]]) != len(durations):
            warnings.append(warning("VIDEO", scene, "컷 수와 THEME_VIDEO_CUT_SECONDS 길이가 다름"))
            continue
        scenes.append(scene)
    jobs = [(scene, i) for scene in scenes for i in range(1, len(durations) + 1)]
    results = await asyncio.gather(
        *(film(ctx, theme, scene, i, images[f"{scene}{i}"], durations[i - 1]) for scene, i in jobs)
    )
    filmed = dict(zip(jobs, results, strict=True))
    keys: dict[str, str] = {}
    lengths: dict[str, list[float]] = {}
    for scene in scenes:
        cuts = [filmed[(scene, i)] for i in range(1, len(durations) + 1)]
        for i, (_, _, warns, _) in enumerate(cuts, 1):
            warnings += [warning("VIDEO", f"{scene}{i}", w) for w in warns]
        failed = [
            (i, r)
            for i, (clip, bad, _, _) in enumerate(cuts, 1)
            if clip is None
            for r in bad or ["?"]
        ]
        if failed:
            warnings += [warning("VIDEO", scene, f"{scene}{i} 영상 {r}") for i, r in failed]
            continue
        actual = [length for _, _, _, length in cuts]
        key, error = await join_and_put(ctx, scene, [c for c, _, _, _ in cuts if c], actual)
        if key:
            keys[scene] = key
            lengths[scene] = actual
            logger.info("theme video %s %.1fs model=%s", scene, sum(actual), ctx.video.model)
        else:
            warnings.append(warning("VIDEO", scene, error or "JOIN"))
    return {"video_keys": keys, "video_durations": lengths, "media_warnings": warnings}
