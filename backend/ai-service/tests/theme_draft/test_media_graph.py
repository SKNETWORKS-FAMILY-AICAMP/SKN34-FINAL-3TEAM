"""테마 그래프 그림·영상·움직임 단계 시험.

실제 OpenAI·Google·S3는 부르지 않는다. 그림·영상은 가짜 클라이언트(app/llm/media.py), 저장은
MemoryThemeStorage, LLM은 test_graph의 ScriptedLlm에 그림 수를 기록하는 하위 클래스를 쓴다.
"""

import asyncio
import json
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.config import get_settings
from app.llm.base import LlmError, LlmRequest, ProviderResponse, T
from app.llm.media import FakeImageClient, FakeVideoClient, tiny_png
from app.mission_draft.models import Draft
from app.mission_draft.prompts import GeneratedDraft
from app.prompt_versions.registry import ActiveVersions
from app.theme_draft.checks import DAY_TYPE, DAYS, VIDEO_REVIEW_IDS, motion, spots
from app.theme_draft.models import (
    GeneratedDialogue,
    GeneratedImageReview,
    GeneratedMissionReview,
    GeneratedMotion,
    GeneratedStoryReview,
    GeneratedTheme,
    GeneratedVideoReview,
    ImageReviewItem,
    MotionSpot,
    ThemeDraftRequest,
    ThemeDraftResponse,
    ThemeMotion,
    VideoReviewItem,
)
from app.theme_draft.prompts import VIDEO_NEGATIVE
from app.theme_draft.service import ThemeDraftGraphRunner
from app.theme_draft.storage import MemoryThemeStorage
from tests.theme_draft.fixtures import (
    DISCOVERY,
    INTRO_CUTS,
    OUTRO_CUTS,
    dialogue,
    generated_theme,
    mission_draft,
    mission_review,
    story_review,
    valid_theme,
)
from tests.theme_draft.helpers import request_body
from tests.theme_draft.test_graph import ScriptedLlm

SCENES = ("INTRO", "MON", "TUE", "WED", "THU", "FRI", "OUTRO")
KEY = re.compile(r"theme-drafts/[0-9a-f]{32}/(INTRO|MON|TUE|WED|THU|FRI|OUTRO)\.(png|mp4)")
ImageVerdicts = Callable[[dict], dict[str, str]]  # 검토 user JSON → {항목: 판정}


class MediaLlm(ScriptedLlm):
    """요청마다 함께 보낸 그림 수를 (출력 형식, 그림 수)로 남긴다."""

    def __init__(self, model: str, handlers: dict[type, Any]) -> None:
        super().__init__(model, handlers)
        self.image_counts: list[tuple[str, int]] = []

    async def _request(self, request: LlmRequest[T]) -> ProviderResponse[T]:
        self.image_counts.append((request.output.__name__, len(request.images)))
        return await super()._request(request)

    def last_user(self) -> dict:
        return json.loads(self.calls[-1][2])


# 살펴보기: 증거 물건 1개 + 미션 물건 1개(월요일 단서 값 '젖음'·후보 이름 없음)
GOOD_SPOTS = [
    {"label": "발자국", "line": "여기 발자국을 찾았어!", "evidence": True, "x": 30, "y": 70},
    {"label": "마을 지도", "line": "지도로 길을 따라가 볼까?", "evidence": False, "x": 60, "y": 40},
]


def good_motion(speakers: list[str], **overrides: Any) -> GeneratedMotion:
    body: dict[str, Any] = {
        "transition": "fade",
        "transitionSeconds": 0.6,
        "cameraFrom": {"x": 40, "y": 50, "zoom": 1.0},
        "cameraTo": {"x": 55, "y": 45, "zoom": 1.2},
        "cameraSeconds": 12,
        "speakers": [{"name": s, "x": 30 + 20 * i, "y": 60} for i, s in enumerate(speakers)],
        "effects": [
            {
                "shape": "leaf",
                "color": "#88AA44",
                "count": 8,
                "size": 2,
                "direction": 10,
                "speed": 5,
                "opacity": 0.5,
            }
        ],
        "spots": [],
    }
    body.update(overrides)
    return GeneratedMotion.model_validate(body)


def gen_llm(motion_reply: Callable[[dict], Any] | None = None) -> MediaLlm:
    llm = MediaLlm(
        "gen-model",
        {
            GeneratedTheme: lambda n, d: generated_theme(),
            GeneratedDraft: lambda n, d: mission_draft(DAY_TYPE[d]),
            GeneratedDialogue: lambda n, d: dialogue(),
        },
    )
    reply = motion_reply or (
        lambda user: good_motion(user["speakers"], spots=GOOD_SPOTS if "dayInfo" in user else [])
    )
    llm.handlers[GeneratedMotion] = lambda n, d: reply(llm.last_user())
    return llm


def review_llm(
    image: ImageVerdicts | None = None, video: Callable[[dict], dict[str, str]] | None = None
) -> MediaLlm:
    llm = MediaLlm(
        "review-model",
        {
            GeneratedStoryReview: lambda n, d: story_review(),
            GeneratedMissionReview: lambda n, d: mission_review(),
        },
    )

    def image_review(n: int, d: str | None) -> GeneratedImageReview:
        user = llm.last_user()
        verdicts = (image or (lambda u: {}))(user)
        return GeneratedImageReview(
            items=[
                ImageReviewItem(id=i, verdict=verdicts.get(i, "PASS"), reason=f"{i} 사유")
                for i in user["items"]
            ]
        )

    def video_review(n: int, d: str | None) -> GeneratedVideoReview:
        verdicts = (video or (lambda u: {}))(llm.last_user())
        return GeneratedVideoReview(
            items=[
                VideoReviewItem(id=i, verdict=verdicts.get(i, "PASS"), reason=f"{i} 사유")  # type: ignore[arg-type]
                for i in VIDEO_REVIEW_IDS
            ]
        )

    llm.handlers[GeneratedImageReview] = image_review
    llm.handlers[GeneratedVideoReview] = video_review
    return llm


def run(
    gen: MediaLlm,
    review: MediaLlm,
    *,
    image: FakeImageClient | None = None,
    video: FakeVideoClient | None = None,
    storage: MemoryThemeStorage | None = None,
    deadline_in: float = 900,
    **body: Any,
) -> ThemeDraftResponse:
    request = ThemeDraftRequest.model_validate(request_body(**body))
    runner = ThemeDraftGraphRunner(
        gen,
        review,
        get_settings(),
        ActiveVersions(),
        image=image,
        video=video,
        storage=storage,
        mungchi=tiny_png(99),
    )
    return asyncio.run(runner.run(request, time.monotonic() + deadline_in))


def scene_is(user: dict, text: str) -> bool:
    return text in user["scene"]


def prompts_with(image: FakeImageClient, text: str) -> list[tuple[str, int]]:
    return [c for c in image.calls if text in c[0]]


def mp4_seconds(data: bytes) -> float:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "v.mp4"
        path.write_bytes(data)
        out = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)],
            capture_output=True,
            text=True,
            check=False,
        ).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out).groups()  # type: ignore[union-attr]
    return int(h) * 3600 + int(m) * 60 + float(s)


# --- 설정 없음 ------------------------------------------------------------------------


@pytest.mark.parametrize("with_image", [False, True])
def test_no_image_setup_skips_media_with_one_warning(with_image: bool) -> None:
    image = FakeImageClient() if with_image else None  # 그림만 있고 저장소가 없어도 건너뜀
    response = run(gen_llm(), review_llm(), image=image)
    assert response.failure is None and len(response.missions) == 5  # 글 단계 결과는 그대로
    assert [(w.stage, w.item, w.reason) for w in response.warnings] == [
        ("IMAGE", "ALL", "그림 설정 없음")
    ]
    assert response.images == response.videos == response.motions == {}
    assert image is None or image.calls == []


# --- 그림 ---------------------------------------------------------------------------


def test_images_motion_and_video_off_warning() -> None:
    image, storage = FakeImageClient(), MemoryThemeStorage()
    gen, review = gen_llm(), review_llm()
    response = run(gen, review, image=image, storage=storage)
    assert response.failure is None
    assert set(response.images) == set(SCENES)
    assert all(KEY.fullmatch(k) and k.endswith(f"/{s}.png") for s, k in response.images.items())
    assert {k for k in storage.objects} == set(response.images.values())
    assert {ct for _, ct in storage.objects.values()} == {"image/png"}
    # 테마 옷 뭉치(기본 그림 1장 참조) → 시작 1컷(참조 없음) → 나머지 12장
    assert (
        image.calls[0][1] == 1
        and "Only add the theme outfit: 구조대 주황 조끼" in image.calls[0][0]
    )
    assert image.calls[1][1] == 0 and INTRO_CUTS[0]["scene"] in image.calls[1][0]
    assert len(image.calls) == 14
    refs = {c[0].split("Scene (Korean): ")[1].split("\n")[0]: c[1] for c in image.calls[1:]}
    assert refs[INTRO_CUTS[1]["scene"]] == 1  # 시작 2컷: 뭉치 없이 인물 기준 그림만
    assert refs[INTRO_CUTS[2]["scene"]] == 1  # 시작 3컷: 테마 옷 뭉치만(뭉치 혼자)
    assert refs[OUTRO_CUTS[0]["scene"]] == 2
    mon = prompts_with(image, "장소 마을 mon 길")
    assert len(mon) == 1 and mon[0][1] == 2  # [테마 옷 뭉치, 인물 기준 그림]
    assert "Do not draw 강아지 보리" in mon[0][0]
    assert mission_draft("ANALYZE").question in mon[0][0]  # 미션 질문 한국어 그대로
    assert "무엇을 보았는지 떠올려 볼까?" in mon[0][0]  # 생각 열기 질문
    assert DISCOVERY["MON"] in mon[0][0]  # 그날 증거 발견 줄(증거 물건이 보이게)
    intro3 = prompts_with(image, INTRO_CUTS[2]["scene"])[0][0]
    assert "a closed straight-line mouth" in intro3  # determined → 입 모양
    assert "expression" not in image.calls[1][0]  # 시작 1컷은 뭉치 없음(none)
    intro2 = prompts_with(image, INTRO_CUTS[1]["scene"])[0][0]
    assert "Mungchi does not appear" in intro2 and "Do not draw 강아지 보리" in intro2
    assert "may appear" in image.calls[1][0]  # 시작 1컷은 찾는 대상 허용
    assert "may appear" in prompts_with(image, OUTRO_CUTS[2]["scene"])[0][0]
    # 검토는 [그림, 테마 옷 뭉치], 움직임은 그 장면 그림 1장
    assert {c for c in review.image_counts if c[0] == "GeneratedImageReview"} == {
        ("GeneratedImageReview", 2)
    }
    assert review.count("GeneratedImageReview") == 13
    mon_review = [json.loads(u) for u in review.users("GeneratedImageReview")]
    assert {tuple(u["items"]) for u in mon_review if "missionQuestion" in u} == {
        ("MUNGCHI", "ANSWER_HINT", "TEXT", "SAFETY", "SCENE_FIT", "MISSION_FIT")
    }
    assert {u["discovery"] for u in mon_review if "missionQuestion" in u} == set(DISCOVERY.values())
    assert {c for c in gen.image_counts if c[0] == "GeneratedMotion"} == {("GeneratedMotion", 1)}
    # 영상 클라이언트가 없으면 영상만 건너뜀
    assert response.videos == {}
    assert [(w.stage, w.item, w.reason) for w in response.warnings] == [
        ("VIDEO", "ALL", "영상 설정 꺼짐")
    ]
    # 움직임: 장면 7개, 요일은 대화 화자, 시작·종료는 영상이 없어 문구 없음
    assert set(response.motions) == set(SCENES)
    assert all(isinstance(m, ThemeMotion) and m.version == 1 for m in response.motions.values())
    assert set(response.motions["MON"].speakers) == {"뭉치", "지호"}
    assert response.motions["INTRO"].speakers == {} and response.motions["INTRO"].captions == []
    dumped = response.model_dump(by_alias=True)["motions"]["MON"]
    assert set(dumped) == {
        "version",
        "transition",
        "camera",
        "speakers",
        "effects",
        "captions",
        "spots",
    }
    # 살펴보기: 요일 장면만, 움직임 user에 그날 증거 발견 줄·미션 질문·생각 열기 질문(단서 없음)
    assert [s["label"] for s in dumped["spots"]] == ["발자국", "마을 지도"]
    assert [s["evidence"] for s in dumped["spots"]] == [True, False]
    assert response.motions["INTRO"].spots == []
    motion_users = [json.loads(u) for u in gen.users("GeneratedMotion")]
    mon_user = next(u for u in motion_users if u["scene"] == "MON")
    assert mon_user["dayInfo"]["discovery"] == DISCOVERY["MON"]
    assert mon_user["dayInfo"]["missionQuestion"] == mission_draft("ANALYZE").question
    # 증거 종류와 피할 낱말(그날 단서 값·후보 이름·미션 금지어)을 함께 줌(점검 C3·C11·C20)
    assert set(mon_user["dayInfo"]) == {
        "discovery",
        "evidenceKind",
        "missionQuestion",
        "hints",
        "avoidWords",
    }
    assert mon_user["dayInfo"]["evidenceKind"] == "TRACE"
    assert "젖음" in mon_user["dayInfo"]["avoidWords"]
    assert all(c in mon_user["dayInfo"]["avoidWords"] for c in valid_theme()["candidates"])
    assert "dayInfo" not in next(u for u in motion_users if u["scene"] == "INTRO")
    assert set(dumped["camera"]) == {"from", "to", "seconds"}  # 계약 ThemeMotion 형식


def first_time(match: Callable[[dict], bool], verdicts: dict[str, str]) -> Callable:
    """match에 맞는 첫 검토만 verdicts, 그 뒤는 모두 PASS."""
    seen: list[dict] = []

    def reply(user: dict) -> dict[str, str]:
        if not match(user):
            return {}
        seen.append(user)
        return verdicts if len(seen) == 1 else {}

    return reply


def test_image_review_fail_redraws_only_that_image_with_reason() -> None:
    verdicts = first_time(lambda u: scene_is(u, "마을 tue 길"), {"SCENE_FIT": "FAIL"})
    image = FakeImageClient()
    response = run(gen_llm(), review_llm(image=verdicts), image=image, storage=MemoryThemeStorage())
    assert response.failure is None and "TUE" in response.images
    tue = prompts_with(image, "장소 마을 tue 길")
    assert len(tue) == 2 and "SCENE_FIT SCENE_FIT 사유" in tue[1][0]
    assert len(prompts_with(image, "장소 마을 wed 길")) == 1


def test_request_image_failures_seed_image_prompts() -> None:
    """요청 previousFailures의 IMAGE 사유: 그림 이름이 붙으면 그 그림, 없으면 모든 그림의 첫
    그리기부터 들어감(테마 옷 뭉치는 제외)."""
    failures = [{"stage": "IMAGE", "reasons": ["TUE MISSION_FIT 녹음기 안 보임", "TEXT 글자 있음"]}]
    image = FakeImageClient()
    response = run(
        gen_llm(),
        review_llm(),
        image=image,
        storage=MemoryThemeStorage(),
        previousFailures=failures,
    )
    assert response.failure is None
    assert "MISSION_FIT 녹음기 안 보임" not in image.calls[0][0]  # 테마 옷 뭉치
    assert "TEXT 글자 있음" not in image.calls[0][0]
    tue = prompts_with(image, "장소 마을 tue 길")
    assert len(tue) == 1 and "MISSION_FIT 녹음기 안 보임" in tue[0][0]
    assert "TUE MISSION_FIT" not in tue[0][0]  # 그림 이름은 떼고 넣음
    assert "MISSION_FIT 녹음기 안 보임" not in prompts_with(image, "장소 마을 wed 길")[0][0]
    assert all("TEXT 글자 있음" in c[0] for c in image.calls[1:])


def test_mission_image_failure_is_image_failure_with_text() -> None:
    def verdicts(user: dict) -> dict[str, str]:
        return {"MISSION_FIT": "FAIL"} if scene_is(user, "마을 mon 길") else {}

    image, gen = FakeImageClient(), gen_llm()
    response = run(gen, review_llm(image=verdicts), image=image, storage=MemoryThemeStorage())
    assert response.failure is not None and response.failure.stage == "IMAGE"
    assert response.failure.reasons == ["MON MISSION_FIT MISSION_FIT 사유"]
    assert len(prompts_with(image, "장소 마을 mon 길")) == get_settings().theme_max_regen + 1
    assert response.theme is not None and len(response.missions) == 5  # 글은 함께 반환
    assert "MON" not in response.images and "TUE" in response.images
    assert response.videos == response.motions == {} and gen.count("GeneratedMotion") == 0


# --- 영상 ---------------------------------------------------------------------------


def test_video_success_joins_cuts_with_captions() -> None:
    video_verdicts = first_time(
        lambda u: u["scene"] == INTRO_CUTS[1]["scene"], {"MORPH": "FAIL"}
    )  # 시작 2컷 처음 한 번만 FAIL
    image, video, storage = FakeImageClient(), FakeVideoClient(), MemoryThemeStorage()
    response = run(
        gen_llm(), review_llm(video=video_verdicts), image=image, video=video, storage=storage
    )
    assert response.failure is None and response.warnings == []
    assert set(response.videos) == {"INTRO", "OUTRO"}
    for scene, key in response.videos.items():
        assert KEY.fullmatch(key) and key.endswith(f"/{scene}.mp4")
        body, content_type = storage.objects[key]
        assert content_type == "video/mp4"
        assert mp4_seconds(body) == pytest.approx(4 + 6 + 8 + 6 - 3 * 0.5, abs=0.15)
    assert len(video.calls) == 9  # 8컷 + 다시 만든 1컷
    assert {c[2] for c in video.calls} == {None}  # 첫 그림만 고정
    assert set(video.negatives) == {VIDEO_NEGATIVE}
    assert sorted(c[3] for c in video.calls) == sorted([4, 6, 8, 6] * 2 + [6])
    smile = [c[0] for c in video.calls if OUTRO_CUTS[3]["action"] in c[0]]
    # 종료 4컷은 대상을 보여 줘도 되는 컷이라 숨기라는 문구가 없음(점검 C5)
    assert "a small smiling mouth" in smile[0] and "Do not show" not in smile[0]
    first = [c[0] for c in video.calls if INTRO_CUTS[0]["action"] in c[0]][0]
    assert "may be held or used, but do not show where it is put" in first
    assert "Mungchi does not appear in this clip." in first  # 시작 1컷은 뭉치 없음(점검 C6)
    run_cut = [c[0] for c in video.calls if INTRO_CUTS[2]["action"] in c[0]][0]
    assert "Only Mungchi is in this clip" in run_cut and "Do not show 강아지 보리." in run_cut
    again = [c[0] for c in video.calls if INTRO_CUTS[1]["action"] in c[0]]
    assert len(again) == 2 and "MORPH MORPH 사유" in again[1]
    intro = response.motions["INTRO"]
    assert [(c.start, c.end, c.text) for c in intro.captions] == [
        (0.0, 3.75, INTRO_CUTS[0]["caption"]),
        (3.75, 9.25, INTRO_CUTS[1]["caption"]),
        (9.25, 16.75, INTRO_CUTS[2]["caption"]),
        (16.75, 22.5, INTRO_CUTS[3]["caption"]),
    ]
    assert response.motions["MON"].captions == []


def test_cut_image_failure_omits_only_that_video() -> None:
    def verdicts(user: dict) -> dict[str, str]:
        return {"TEXT": "FAIL"} if user["scene"] == OUTRO_CUTS[1]["scene"] else {}

    video = FakeVideoClient()
    response = run(
        gen_llm(),
        review_llm(image=verdicts),
        image=FakeImageClient(),
        video=video,
        storage=MemoryThemeStorage(),
    )
    assert response.failure is None
    assert set(response.videos) == {"INTRO"} and len(video.calls) == 4
    assert {(w.stage, w.item) for w in response.warnings} == {("VIDEO", "OUTRO")}
    assert all(w.reason.startswith("OUTRO2 그림 TEXT") for w in response.warnings)
    assert "OUTRO" in response.images  # 4번째 컷 그림은 통과
    assert response.motions["OUTRO"].captions == []  # 영상이 없으면 문구 없음


def test_video_skipped_near_deadline() -> None:
    video = FakeVideoClient()
    response = run(
        gen_llm(),
        review_llm(),
        image=FakeImageClient(),
        video=video,
        storage=MemoryThemeStorage(),
        deadline_in=400,  # theme_video_timeout(400) + 60초 미만
    )
    assert response.failure is None and video.calls == [] and response.videos == {}
    assert [(w.stage, w.item) for w in response.warnings] == [("VIDEO", "ALL")]
    assert "마감" in response.warnings[0].reason
    assert len(response.motions) == 7


# --- 움직임 ---------------------------------------------------------------------------


def test_motion_out_of_range_is_fitted_with_warnings() -> None:
    def wild(user: dict) -> GeneratedMotion:
        effect = {
            "shape": "snow",
            "color": "#FFFFFF",
            "count": 50,
            "size": 9,
            "direction": 400,
            "speed": 1,
            "opacity": 0.9,
        }
        return good_motion(
            [*user["speakers"], "강아지 보리"],
            transitionSeconds=3,
            cameraFrom={"x": -5, "y": 50, "zoom": 2},
            cameraSeconds=30,
            effects=[effect, {**effect, "color": "white"}, effect],
        )

    response = run(
        gen_llm(motion_reply=wild),
        review_llm(),
        image=FakeImageClient(),
        storage=MemoryThemeStorage(),
    )
    mon = response.motions["MON"]
    assert mon.transition.seconds == 1.2 and mon.camera is not None
    assert (mon.camera.from_.x, mon.camera.from_.zoom, mon.camera.seconds) == (0, 1.4, 20)
    assert set(mon.speakers) == {"뭉치", "지호"}  # 찾는 대상은 뺌
    assert len(mon.effects) == 1  # 색이 틀린 층은 빼고 2층까지
    e = mon.effects[0]
    assert (e.count, e.size, e.direction, e.speed, e.opacity) == (20, 6, 40, 2, 0.8)
    reasons = [w.reason for w in response.warnings if (w.stage, w.item) == ("MOTION", "MON")]
    assert any("camera.seconds 30.0→20.0" in r for r in reasons)
    assert any("강아지 보리" in r for r in reasons)
    assert any("#RRGGBB" in r for r in reasons)
    assert {w.stage for w in response.warnings} == {"MOTION", "VIDEO"}


def test_motion_llm_failure_omits_that_scene() -> None:
    def reply(user: dict) -> Any:
        if user["scene"] == "WED":
            return LlmError("LLM_INVALID_OUTPUT", retryable=False)
        return good_motion(user["speakers"])

    response = run(
        gen_llm(motion_reply=reply),
        review_llm(),
        image=FakeImageClient(),
        storage=MemoryThemeStorage(),
    )
    assert response.failure is None and set(response.motions) == set(SCENES) - {"WED"}
    assert ("MOTION", "WED", "MOTION_CALL LLM_INVALID_OUTPUT") in {
        (w.stage, w.item, w.reason) for w in response.warnings
    }


def test_motion_check_unit() -> None:
    generated = good_motion(["뭉치"]).model_dump()
    value, notes = motion(generated, ["뭉치"], [{"start": 0, "end": 3.75, "text": "가" * 40}])
    assert notes == []
    parsed = ThemeMotion.model_validate(value)
    assert parsed.speakers["뭉치"].zoom == 1.2 and len(parsed.captions[0].text) == 30
    generated["cameraTo"] = {"x": 140, "y": -1, "zoom": 0.5}
    value, notes = motion(generated, [], [])
    assert value["camera"]["to"] == {"x": 100.0, "y": 0.0, "zoom": 1.0}
    assert value["speakers"] == {} and len(notes) == 4  # x·y·zoom + 화자 아닌 뭉치


def test_image_prompts_and_review_follow_drawing_rules() -> None:
    """그림 규칙과 검토가 맞음(점검 C1·C2·C4·C8): 옷 그림 글자 금지, 증거 종류별로 그릴 것, 찾는
    대상은 증거가 아님, 검토는 글자·개수를 보지 않음, 종료 콘티만 정답 장소 공개 허용."""
    from app.theme_draft import prompts

    theme = valid_theme()
    assert "No letters, numbers, badges or emblems" in prompts.outfit_prompt(theme)
    mon = prompts.mission_image_prompt(theme, "MON", mission_draft("ANALYZE"), [])
    assert "the place or object where the trace was left" in mon
    assert "itself is not the evidence; do not draw it" in mon
    assert "적힌 내용·정확한 개수" in prompts.IMAGE_REVIEW_SYSTEM
    assert "장면 글에 없는 등장인물이 함께 있는 것은 결함이 아니다" in prompts.IMAGE_REVIEW_SYSTEM
    user = json.loads(
        prompts.image_review_user(
            theme,
            "s",
            ids=("ANSWER_HINT",),
            has_mungchi=True,
            shows_target=False,
            question="q",
            hints=[],
            discovery="d",
            evidence="SIGHTING",
        )
    )
    assert user["evidenceKind"] == "SIGHTING" and user["answerPlaceAllowed"] is False
    assert prompts.cut_reveals_answer("OUTRO") and not prompts.cut_reveals_answer("INTRO")


def test_spots_leak_mission_answer() -> None:
    """살펴보기 한마디가 미션 금지어를 말하면 그 물건을 뺌(대화와 같은 유출 검사, 점검 C20)."""
    draft = Draft.model_validate(mission_draft("ANALYZE").model_dump())
    word = (draft.forbidden_terms or ["비밀낱말"])[0]
    if not draft.forbidden_terms:
        draft = draft.model_copy(update={"forbidden_terms": [word]})
    out, notes = spots(
        [EV, OTHER, spot("의자", f"{word} 이야기를 해 볼까?", False, 85, 75)],
        valid_theme(),
        "MON",
        draft,
    )
    assert [s["label"] for s in out] == ["발자국", "마을 지도"]
    assert any("LEAK" in n for n in notes)


def spot(label: str, line: str, evidence: bool = False, x: float = 50, y: float = 50) -> dict:
    return {"label": label, "line": line, "evidence": evidence, "x": x, "y": y}


EV = spot("발자국", "여기 발자국을 찾았어!", True, 20, 70)
OTHER = spot("마을 지도", "지도로 길을 따라가 볼까?", False, 60, 40)


@pytest.mark.parametrize(
    ("name", "given", "labels", "codes"),
    [
        ("good", [EV, OTHER], ["발자국", "마을 지도"], []),
        # 한마디가 그날 단서 값('젖음')을 미리 말하면 그 물건만 빼고, 2개 미만이면 비움
        (
            "clue early",
            [EV, spot("웅덩이", "바닥에 젖음 자국이 있어")],
            [],
            ["MOTION_SPOT", "MOTION_SPOT"],
        ),
        (
            "candidate name",
            [EV, OTHER, spot("창고 문", "문이 열려 있네")],
            ["발자국", "마을 지도"],
            ["MOTION_SPOT"],
        ),
        ("no evidence", [OTHER, spot("나무", "나무 아래를 볼까?")], [], ["MOTION_SPOT"]),
        (
            "two evidence",
            [EV, spot("털", "털을 찾았어!", True, 80, 30)],
            ["발자국", "털"],
            ["MOTION_SPOT"],
        ),
        (
            "too many keeps evidence",
            [
                OTHER,
                spot("나무", "나무 아래를 볼까?", False, 85, 20),
                spot("의자", "의자를 볼까?", False, 85, 80),
                EV,
            ],
            ["발자국", "마을 지도", "나무"],
            ["MOTION_SPOT"],
        ),
        ("long line", [EV, OTHER, spot("돌", "가" * 31)], ["발자국", "마을 지도"], ["MOTION_SPOT"]),
        # 한 물건의 부분처럼 서로 가까운 위치는 하나만 남김(증거 우선, 실측 화요일)
        (
            "too close",
            [spot("화면 속 길", "길을 볼까?", False, 22, 72), EV, OTHER],
            ["발자국", "마을 지도"],
            ["MOTION_SPOT"],
        ),
        (
            "coords fitted",
            [spot("발자국", "찾았어!", True, 120, -3), OTHER],
            ["발자국", "마을 지도"],
            ["MOTION_RANGE"],
        ),
    ],
)
def test_spots_check(name: str, given: list[dict], labels: list[str], codes: list[str]) -> None:
    out, notes = spots(given, valid_theme(), "MON")
    assert [s["label"] for s in out] == labels
    assert sorted(n.split()[0] for n in notes) == sorted(codes)
    assert all(0 <= s["x"] <= 100 and 0 <= s["y"] <= 100 for s in out)
    assert sum(s["evidence"] for s in out) == (1 if out else 0)
    for s in out:
        MotionSpot.model_validate(s)


def test_spots_only_for_day_scenes() -> None:
    assert spots([EV, OTHER], valid_theme(), None) == (
        [],
        ["MOTION_SPOT 시작·종료 장면은 살펴보기 없음"],
    )
    assert spots([], valid_theme(), None) == ([], [])


# --- 연결 ---------------------------------------------------------------------------


def test_route_uses_media_clients_from_app_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")  # 클라이언트 생성만, 호출은 가짜
    get_settings.cache_clear()
    gen, review, storage = gen_llm(), review_llm(), MemoryThemeStorage()
    try:
        app = create_app()
        with TestClient(app) as client:
            assert app.state.theme_image is None and app.state.theme_storage is None  # 버킷 없음
            app.state.theme_llm, app.state.theme_review_llm = gen, review
            app.state.theme_image, app.state.theme_storage = FakeImageClient(), storage
            response = client.post(
                "/internal/theme-drafts",
                json=request_body(),
                headers={"X-Internal-Token": "test-token"},
            )
    finally:
        get_settings.cache_clear()
    body = response.json()
    assert response.status_code == 200 and body["failure"] is None
    assert set(body["images"]) == set(SCENES) and len(storage.objects) == 7
    assert set(body["motions"]["MON"]["camera"]) == {"from", "to", "seconds"}
    assert DAYS[0] in body["motions"]


def test_cut_freezes_trims_ends_and_fails_middle() -> None:
    """앞뒤 정지 화면은 잘라 내고 실제 길이를 돌려줌, 중간에 0.5초 넘게 멈추면 FREEZE(그 컷을
    다시 만듦). 실측에서 컷 안 0.4~0.9초 멈춤이 재생 중 끊김으로 보였음."""
    from app.llm.media import color_clip, concat_mp4
    from app.theme_draft.nodes.video import cut_freezes

    ends = concat_mp4(
        [color_clip(1, 1, still=True), color_clip(2, 3), color_clip(3, 1, still=True)]
    )
    trimmed, length, bad = cut_freezes(ends, 5)
    assert bad == [] and length == pytest.approx(3, abs=0.4) and trimmed != ends
    middle = concat_mp4([color_clip(4, 2), color_clip(5, 1, still=True), color_clip(6, 2)])
    _, _, bad = cut_freezes(middle, 5)
    assert len(bad) == 1 and bad[0].startswith("FREEZE ")
    _, _, bad = cut_freezes(color_clip(7, 4, still=True), 4)
    assert len(bad) == 1 and bad[0].startswith("FREEZE ")


def test_video_prompt_and_review_keep_everyone_and_outfit() -> None:
    """영상 지시문·금지 조건·검토가 인물 유지·뭉치 모양·옷 유지를 다룸(실측: 인물이 사라지고 팔이
    생기고 옷이 바뀜). 검토는 첫 장면 + 1초마다 장면, 항목 CONTINUITY."""
    from app.theme_draft import prompts

    theme = valid_theme()
    text = prompts.video_prompt(theme, "OUTRO", 4, OUTRO_CUTS[3], [])
    assert "nobody walks out, disappears, appears or merges" in text
    assert (
        "no arms, wings or stretched limbs" in text and "stay exactly as in the first frame" in text
    )
    assert "never zoom in so close" in text
    for word in ("character leaving the frame", "wings", "outfit change", "freeze frame"):
        assert word in VIDEO_NEGATIVE
    assert "CONTINUITY" in VIDEO_REVIEW_IDS and "CONTINUITY:" in prompts.VIDEO_REVIEW_SYSTEM
    assert (
        "한눈에 알아보게" in prompts.PLAN_SYSTEM and "화면 밖으로 나가거나" in prompts.PLAN_SYSTEM
    )
