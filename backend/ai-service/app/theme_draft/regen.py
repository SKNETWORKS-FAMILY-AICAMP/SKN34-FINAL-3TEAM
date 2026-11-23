"""부분 다시 생성(#537, 사용자 결정 2026-11-17).

- 대상 → 다시 만들 범위(plan_of). 고르지 않은 것은 원래 결과 값을 그대로 돌려준다.
  · VIDEO:X → X 영상과 X 움직임
  · IMAGE:요일 → 그 미션 그림과 그 장면 움직임
  · IMAGE:INTRO|OUTRO → 컷 첫 그림 4장과 그 영상·움직임(컷 그림이 영상 첫 장면이라)
  · MISSION:요일 → 그 요일 미션·수사 연결 문장·대화 → 글 검토 → 그 요일 그림 → 움직임
- 원래 결과는 learning이 저장한 output(regenerate.base)이고, ai 전용 재료는 그 안의 regen 묶음이다.
  글 재료(줄거리 내부 칸 전체·컷 길이)는 regen에, 그림 재료(테마 옷 뭉치·인물 기준·컷 첫 그림)는
  S3 키로 regen.assets에 있다.
- 응답 regen.targets는 그 결과에서 다시 만들 수 있는 대상이다. learning은 이 목록 밖 요청을 409로
  거절한다(202 뒤 ai가 거부하면 learning이 3번 다시 불러 FAILED가 돼서).
"""

import asyncio
import logging
from dataclasses import dataclass, field

from langgraph.runtime import Runtime

from app.theme_draft.checks import DAYS
from app.theme_draft.models import REGEN_VERSION, ThemeWarning
from app.theme_draft.nodes import ThemeContext, ThemeState

logger = logging.getLogger(__name__)

CUT_SCENES = ("INTRO", "OUTRO")
CUTS = (1, 2, 3, 4)
SCENE_ORDER = ("INTRO", *DAYS, "OUTRO")
TARGET_ORDER = (
    *(f"VIDEO:{s}" for s in CUT_SCENES),
    *(f"IMAGE:{s}" for s in SCENE_ORDER),
    *(f"MISSION:{d}" for d in DAYS),
)
OUTSIDE_REASON = "PARTIAL 글 검토가 다시 만들 대상 밖을 고치라고 해서 멈춤"


def cut_keys(scene: str) -> list[str]:
    return [f"{scene}{i}" for i in CUTS]


@dataclass
class Plan:
    mission_days: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)  # MON~FRI, INTRO1~4·OUTRO1~4
    videos: list[str] = field(default_factory=list)
    motions: list[str] = field(default_factory=list)


def plan_of(targets: list[str]) -> Plan:
    days: set[str] = set()
    images: set[str] = set()
    videos: set[str] = set()
    motions: set[str] = set()
    for target in targets:
        kind, scene = target.split(":")
        motions.add(scene)
        if kind == "MISSION":
            days.add(scene)
            images.add(scene)
        elif kind == "IMAGE" and scene in DAYS:
            images.add(scene)
        elif kind == "IMAGE":
            images.update(cut_keys(scene))
            videos.add(scene)
        else:  # VIDEO
            videos.add(scene)
    image_order = [*DAYS, *(k for s in CUT_SCENES for k in cut_keys(s))]
    return Plan(
        mission_days=[d for d in DAYS if d in days],
        images=[k for k in image_order if k in images],
        videos=[s for s in CUT_SCENES if s in videos],
        motions=[s for s in SCENE_ORDER if s in motions],
    )


def keep_warnings(warnings: list[ThemeWarning], plan: Plan) -> list[dict]:
    """원래 경고 중 다시 만들지 않는 항목 것만 남긴다(다시 만든 항목은 새 경고로 바뀜)."""
    redrawn_scenes = {k for k in plan.images if k in DAYS} | {
        s for s in CUT_SCENES if f"{s}4" in plan.images
    }

    def redone(w: ThemeWarning) -> bool:
        item = w.item
        if w.stage in ("MISSION", "DIALOGUE"):
            return item in plan.mission_days
        if w.stage == "REVIEW":
            return bool(plan.mission_days)  # 글 검토를 다시 함
        if w.stage == "IMAGE":
            return item in plan.images or item in redrawn_scenes or (item == "ALL" and plan.images)
        if w.stage == "VIDEO":
            if item == "ALL":
                return bool(plan.videos)
            return any(item.startswith(s) for s in plan.videos)
        if w.stage == "MOTION":
            return item in plan.motions
        return False

    return [w.model_dump() for w in warnings if not redone(w)]


def needed_assets(plan: Plan, assets: dict[str, str]) -> dict[str, str]:
    """S3에서 읽을 재료: 이름 → 키. 다시 그리면 옷 뭉치·인물 기준, 영상만 다시면 그 장면 컷 그림."""
    need: list[str] = []
    if plan.images and "OUTFIT" in assets:
        need += ["OUTFIT", *(["PERSON"] if "PERSON" in assets else [])]
    for scene in plan.videos:
        if f"{scene}1" not in plan.images:  # 영상만 다시: 원래 컷 첫 그림으로 다시 찍음
            need += cut_keys(scene)
    return {name: assets[name] for name in dict.fromkeys(need)}


async def restore(state: ThemeState, runtime: Runtime[ThemeContext]) -> ThemeState:
    """원래 결과로 상태를 채우고 다시 만들 범위와 S3 재료 그림을 준비한다."""
    ctx = runtime.context
    regenerate = ctx.request.regenerate
    assert regenerate is not None
    base, regen = regenerate.base, regenerate.base.regen
    plan = plan_of(list(regenerate.targets))
    assets = dict(regen.get("assets") or {})
    out: ThemeState = {
        "partial": True,
        "redo_targets": list(regenerate.targets),
        "theme": regen["theme"],
        "drafts": {m.day: m.draft for m in base.missions},
        "dialogues": {d.day: [line.model_dump() for line in d.lines] for d in base.dialogues},
        "image_keys": dict(base.images),
        "video_keys": dict(base.videos),
        "video_durations": dict(regen.get("videoDurations") or {}),
        "motions": dict(base.motions),
        "assets": assets,
        "redo_images": plan.images,
        "redo_videos": plan.videos,
        "redo_motions": plan.motions,
        "days_todo": plan.mission_days,
        "base_warnings": keep_warnings(base.warnings, plan),
        "person_image": None,
    }
    need = needed_assets(plan, assets)
    if not need:
        return out
    if ctx.storage is None:
        return {**out, "failure": {"stage": "IMAGE", "reasons": ["BASE_ASSET 저장소 설정 없음"]}}
    storage = ctx.storage

    async def one(name: str, key: str) -> tuple[str, bytes | None, str | None]:
        try:
            return name, await storage.get(key), None
        except Exception as exc:  # boto3·botocore 예외가 여러 종류라 넓게 받음
            logger.exception("theme regen asset read failed name=%s", name)
            return name, None, f"BASE_ASSET {name} {type(exc).__name__}"

    results = await asyncio.gather(*(one(n, k) for n, k in need.items()))
    errors = [e for _, _, e in results if e]
    if errors:
        return {**out, "failure": {"stage": "IMAGE", "reasons": errors}}
    loaded = {n: b for n, b, _ in results if b is not None}
    out["person_image"] = loaded.pop("PERSON", None)
    if "OUTFIT" in loaded:
        out["outfit_image"] = loaded.pop("OUTFIT")
    out["scene_images"] = loaded  # 영상만 다시 만들 장면의 컷 첫 그림
    return out


def outside_targets(state: ThemeState, route: str, todo: list[str] | None = None) -> bool:
    """부분 다시 생성에서 글 검토가 대상 밖을 고치려 하는지(줄거리·단서는 늘 대상 밖). 대화만 다시
    (TALK, #782 설계 v12)는 미션 대상 요일이면 그 요일 미션과 함께 다시 만드는 대화라 대상 안."""
    if not state.get("partial"):
        return False
    if route in ("PLAN", "CLUE", "HELPER"):  # HELPER: 줄거리 칸(돕는 사람·일)을 고침(#782 설계 v13)
        return True
    days = {t.split(":")[1] for t in state.get("redo_targets") or [] if t.startswith("MISSION:")}
    return route in ("DAYS", "TALK") and not set(todo or []) <= days


def regenerable(state: ThemeState) -> list[str]:
    """이 결과에서 다시 만들 수 있는 대상(재료가 있는 것만)."""
    drafts = state.get("drafts") or {}
    if not all(d in drafts for d in DAYS):
        return []
    assets = state.get("assets") or {}
    images_made = bool(state.get("image_keys"))
    out: list[str] = []
    if "OUTFIT" in assets or not images_made:  # 미션을 다시 만들면 그 요일 그림도 다시 그림
        out += [f"MISSION:{d}" for d in DAYS]
    if "OUTFIT" in assets:
        out += [f"IMAGE:{s}" for s in SCENE_ORDER]
        out += [f"VIDEO:{s}" for s in CUT_SCENES if all(k in assets for k in cut_keys(s))]
    return [t for t in TARGET_ORDER if t in out]


def bundle(state: ThemeState) -> dict | None:
    """응답 regen 묶음. 글 단계(줄거리·미션·검토)를 마치지 못한 결과는 None."""
    theme = state.get("theme")
    failure = state.get("failure")
    if theme is None or (failure and failure.get("stage") != "IMAGE"):
        return None
    return {
        "version": REGEN_VERSION,
        "targets": regenerable(state),
        "theme": theme,
        "assets": state.get("assets") or {},
        "videoDurations": state.get("video_durations") or {},
    }
