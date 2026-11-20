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
from app.llm.media import (
    FakeImageClient,
    FakeVideoClient,
    color_clip,
    still_clip,
    tiny_png,
    two_face_clip,
)
from app.mission_draft.models import Draft
from app.mission_draft.prompts import GeneratedDraft
from app.prompt_versions.registry import ActiveVersions
from app.theme_draft.checks import DAY_TYPE, DAYS, VIDEO_REVIEW_IDS, motion, spots
from app.theme_draft.models import (
    GeneratedDialogue,
    GeneratedHookFixes,
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
from app.theme_draft.nodes import images as image_node
from app.theme_draft.nodes import video as video_node
from app.theme_draft.nodes.video import STILL_NOTE
from app.theme_draft.prompts import VIDEO_NEGATIVE, video_negative
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
            GeneratedHookFixes: lambda n, d: GeneratedHookFixes(fixes=[]),
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
    settings: dict[str, Any] | None = None,
    **body: Any,
) -> ThemeDraftResponse:
    """settings: 설정 덮어쓰기(예: 그림·영상 대역 {"image_provider": "fake"}, #716). 영상 후보는
    기본 1개(호출 수를 세는 시험이 컷마다 1번을 전제, 후보 여러 개는 test_video_quality, #779)."""
    request = ThemeDraftRequest.model_validate(request_body(**body))
    runner = ThemeDraftGraphRunner(
        gen,
        review,
        get_settings().model_copy(update={"theme_video_candidates": 1, **(settings or {})}),
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
    # 장면 그림 7장 + 부분 다시 생성 재료(테마 옷 뭉치·인물 그림·컷 첫 그림·끝 표정 그림, #537·#779)
    assert response.regen is not None
    assert set(storage.objects) == set(response.images.values()) | set(
        response.regen["assets"].values()
    )
    # 장면 7 + 재료 17(테마 옷 뭉치·인물 그림·컷 12·끝 표정 그림 3, #779 6컷·표정 그림 두 장)
    assert len(storage.objects) == 24
    assert {ct for _, ct in storage.objects.values()} == {"image/png"}
    # 테마 옷 뭉치(기본 그림 1장 참조) → 인물만 그린 기준 그림(참조 없음, #779) → 17장 동시에
    assert (
        image.calls[0][1] == 1
        and "Only add the theme outfit: 구조대 주황 조끼" in image.calls[0][0]
    )
    assert image.calls[1][1] == 0 and "Draw only these people" in image.calls[1][0]
    # 테마 옷 뭉치 + 인물 그림 + 미션 5 + 컷 12 + 끝 표정 그림 3(#779 6컷·표정 그림 두 장)
    assert len(image.calls) == 22
    refs = {
        c[0].split("Scene (Korean): ")[1].split("\n")[0]: c[1]
        for c in image.calls[2:]
        if "Scene (Korean): " in c[0]
    }
    # 표정 그림 두 장 컷의 끝 그림(#779 A안): 그 컷 첫 그림 한 장만 참고해 입만 바꿈
    faces = [c for c in image.calls if "Change only Mungchi's mouth" in c[0]]
    assert len(faces) == 3 and all(c[1] == 1 for c in faces)
    assert refs[INTRO_CUTS[0]["scene"]] == 1  # 시작 1컷: 인물 그림만(#779, 예전엔 참조 없음)
    # 앞 컷을 잇는 컷(#779 B안: 시작 2·3·6 ← 1, 종료 5·6 ← 3)은 앞 컷 그림을 마지막 참고로
    assert refs[INTRO_CUTS[1]["scene"]] == 2  # 시작 2컷: 인물 기준 그림 + 시작 1컷 그림
    assert refs[INTRO_CUTS[2]["scene"]] == 2  # 시작 3컷: 사람 리액션 + 시작 1컷 그림
    assert refs[INTRO_CUTS[3]["scene"]] == 1  # 시작 4컷: 테마 옷 뭉치만(뭉치 혼자 달림)
    assert refs[INTRO_CUTS[4]["scene"]] == 1  # 시작 5컷: 뭉치 혼자 클로즈업(잇지 않음)
    assert refs[INTRO_CUTS[5]["scene"]] == 3  # 시작 6컷: 함께 + 시작 1컷 그림
    assert refs[OUTRO_CUTS[0]["scene"]] == 1  # 종료 1컷: 뭉치 혼자 클로즈업
    assert refs[OUTRO_CUTS[2]["scene"]] == 1  # 종료 3컷: 정답 공개(잇는 기준 컷)
    assert refs[OUTRO_CUTS[4]["scene"]] == 2  # 종료 5컷: 인물 기준 그림 + 종료 3컷 그림
    assert refs[OUTRO_CUTS[5]["scene"]] == 3  # 종료 6컷: 테마 옷 뭉치, 인물 기준 그림 + 종료 3컷
    outro6 = prompts_with(image, OUTRO_CUTS[5]["scene"])[0][0]
    assert f"its scene, in Korean: {OUTRO_CUTS[2]['scene']}" in outro6  # 종료 6컷 ← 3컷(#779)
    assert "something covered stays covered" in outro6
    assert "Use the reference pictures only" not in outro6  # 잇는 컷은 장소도 앞 컷을 따름
    assert "earlier cut" not in prompts_with(image, OUTRO_CUTS[2]["scene"])[0][0]
    # 앞 컷 그림이 다 그려진 뒤에 잇는 컷을 그림(종료 3 → 5·6, 시작 1 → 2·3·6, 두 단)
    order = [
        c[0].split("Scene (Korean): ")[1].split("\n")[0]
        for c in image.calls[2:]
        if "Scene (Korean): " in c[0]
    ]
    at = order.index
    # 끝 표정 그림은 그 컷 첫 그림 뒤에(#779 A안)
    names = [c[0] for c in image.calls]
    first_close = next(i for i, c in enumerate(names) if INTRO_CUTS[4]["scene"] in c)
    assert all(i > first_close for i, c in enumerate(names) if "Change only Mungchi's mouth" in c)
    assert at(OUTRO_CUTS[2]["scene"]) < min(at(OUTRO_CUTS[4]["scene"]), at(OUTRO_CUTS[5]["scene"]))
    assert all(at(INTRO_CUTS[0]["scene"]) < at(INTRO_CUTS[i]["scene"]) for i in (1, 2, 5))
    mon = prompts_with(image, "장소 마을 mon 길")
    assert len(mon) == 1 and mon[0][1] == 2  # [테마 옷 뭉치, 인물 기준 그림]
    assert "Do not draw 강아지 보리" in mon[0][0]
    assert mission_draft("ANALYZE").question in mon[0][0]  # 미션 질문 한국어 그대로
    assert "무엇을 보았는지 떠올려 볼까?" in mon[0][0]  # 생각 열기 질문
    assert DISCOVERY["MON"] in mon[0][0]  # 그날 증거 발견 줄(증거 물건이 보이게)
    intro4 = prompts_with(image, INTRO_CUTS[3]["scene"])[0][0]  # 뭉치 혼자 달림(#779 6컷)
    assert "a closed straight-line mouth" in intro4  # determined → 입 모양
    intro3 = prompts_with(image, INTRO_CUTS[2]["scene"])[0][0]  # 사람 리액션: 수수께끼 빛
    assert "Mungchi does not appear" in intro3 and "A touch of mystery" in intro3
    intro1 = prompts_with(image, INTRO_CUTS[0]["scene"])[0][0]
    assert "expression" not in intro1  # 시작 1컷은 뭉치 없음(none)
    intro2 = prompts_with(image, INTRO_CUTS[1]["scene"])[0][0]
    assert "Mungchi does not appear" in intro2 and "Do not draw 강아지 보리" in intro2
    assert "may appear" in intro1  # 시작 1컷은 찾는 대상 허용
    assert "may appear" in prompts_with(image, OUTRO_CUTS[2]["scene"])[0][0]
    # 검토는 [그림, 테마 옷 뭉치](잇는 컷 5장은 앞 컷 그림을 더해 3장), 움직임은 그 장면 그림 1장
    counts = [c[1] for c in review.image_counts if c[0] == "GeneratedImageReview"]
    # #779 설계 C표: 사람이 나오는 그림은 인물 기준 그림도 봄(PEOPLE). 뭉치 혼자 5장 = 2, 미션 5·
    # 시작 1·종료 3 = 3(+인물), 잇는 사람 컷 5장 = 4(+인물·앞 컷), 끝 표정 그림 3장 = 3(+그 컷
    # 첫 그림, #779 A안)
    assert sorted(counts) == [2] * 5 + [3] * 10 + [4] * 5
    assert review.count("GeneratedImageReview") == 20
    mon_review = [json.loads(u) for u in review.users("GeneratedImageReview")]
    flow = [u for u in mon_review if "FLOW" in u["items"]]
    assert {u["scene"]: u["previousScene"] for u in flow} == {
        INTRO_CUTS[1]["scene"]: INTRO_CUTS[0]["scene"],
        INTRO_CUTS[2]["scene"]: INTRO_CUTS[0]["scene"],
        INTRO_CUTS[5]["scene"]: INTRO_CUTS[0]["scene"],
        OUTRO_CUTS[4]["scene"]: OUTRO_CUTS[2]["scene"],
        OUTRO_CUTS[5]["scene"]: OUTRO_CUTS[2]["scene"],
        # 끝 표정 그림은 같은 컷 첫 그림을 이음
        INTRO_CUTS[4]["scene"]: INTRO_CUTS[4]["scene"],
        OUTRO_CUTS[0]["scene"]: OUTRO_CUTS[0]["scene"],
        OUTRO_CUTS[3]["scene"]: OUTRO_CUTS[3]["scene"],
    }
    ends = [u for u in flow if u["scene"] == u["previousScene"]]
    assert all(tuple(u["items"]) == ("MUNGCHI", "TEXT", "SAFETY", "FLOW") for u in ends)
    assert all("previousScene" not in u for u in mon_review if "FLOW" not in u["items"])
    assert {tuple(u["items"]) for u in mon_review if "missionQuestion" in u} == {
        ("MUNGCHI", "ANSWER_HINT", "TEXT", "SAFETY", "SCENE_FIT", "MISSION_FIT", "PEOPLE")
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


def reviewed(llm: MediaLlm, output: type) -> int:
    """검토 LLM이 그 출력 형식으로 불린 횟수."""
    return sum(1 for name, _ in llm.image_counts if name == output.__name__)


def test_fake_image_provider_skips_image_review_with_one_warning() -> None:
    """#716: 그림 대역(IMAGE_PROVIDER=fake)이면 검토 모델에 대역 그림을 보내지 않고 통과,
    경고 한 줄.

    검토가 불리면 모든 그림을 FAIL로 돌려주게 해 두어도 다시 그리기·IMAGE 실패가 없어야 한다.
    """
    image = FakeImageClient()
    review = review_llm(image=lambda u: {i: "FAIL" for i in u["items"]})
    response = run(
        gen_llm(),
        review,
        image=image,
        storage=MemoryThemeStorage(),
        settings={"image_provider": "fake"},
    )
    assert response.failure is None
    assert set(response.images) == set(SCENES)
    assert len(image.calls) == 22  # 테마 옷 뭉치 + 인물 그림 + 20장, 다시 그리기 없음
    assert reviewed(review, GeneratedImageReview) == 0
    assert reviewed(review, GeneratedStoryReview) == 1  # 글 검토는 그대로
    fake = [w for w in response.warnings if w.reason == image_node.FAKE_REVIEW_SKIPPED]
    assert [(w.stage, w.item) for w in fake] == [("IMAGE", "ALL")]


def test_real_image_provider_still_reviews_every_image() -> None:
    """#716: 실제 그림 설정(기본 openai)이면 지금처럼 그림마다 검토하고 대역 경고가 없다."""
    review = review_llm()
    response = run(gen_llm(), review, image=FakeImageClient(), storage=MemoryThemeStorage())
    assert response.failure is None
    assert reviewed(review, GeneratedImageReview) == 20  # 미션 5 + 컷 12 + 끝 표정 그림 3
    assert all(w.reason != image_node.FAKE_REVIEW_SKIPPED for w in response.warnings)


def test_request_image_failures_seed_image_prompts() -> None:
    """요청 previousFailures의 IMAGE 사유: 그림 이름이 붙으면 그 그림, 없으면 모든 그림의 첫
    그리기부터 들어감(테마 옷 뭉치·인물만 그린 기준 그림은 제외)."""
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
    assert "TEXT 글자 있음" not in image.calls[1][0]  # 인물만 그린 기준 그림(#779)
    assert all("TEXT 글자 있음" in c[0] for c in image.calls[2:])


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
        assert mp4_seconds(body) == pytest.approx(6 * 4 - 5 * 0.5, abs=0.15)  # #779 6컷 × 4초
    # Veo 9컷(표정 그림 두 장 컷 시작 5, 종료 1·4는 Veo 없음, #779 A안) + 다시 만든 1컷
    assert len(video.calls) == 10
    assert {c[2] for c in video.calls} == {None}  # 첫 그림만 고정
    # #779 설계 C표: 공통 + 공중 손짓·한 줄 서기(잃어버린 것은 돌보는 사람이 안아도 돼 만지기 없음)
    assert set(video.negatives) == {video_negative(valid_theme())}
    assert "waving, clapping" in video_negative(valid_theme())
    assert "touching the animal" not in video_negative(valid_theme())
    assert sorted(c[3] for c in video.calls) == [4] * 10  # #779 Veo 9컷 + 다시 1컷, 4초씩
    smile = [c[0] for c in video.calls if OUTRO_CUTS[5]["action"] in c[0]]
    # 종료 6컷은 대상을 보여 줘도 되는 컷이라 숨기라는 문구가 없음(점검 C5). 6컷 뭉치 표정은 컷 표
    # 움직임(motion)이 말하고 콘티 mungchiMood 줄은 넣지 않음(재검토 2026-11-20)
    assert "smiles shyly" in smile[0] and "Do not show" not in smile[0]
    assert "Mungchi's expression:" not in smile[0]
    first = [c[0] for c in video.calls if INTRO_CUTS[0]["action"] in c[0]][0]
    assert "may be held or used, but do not show where it is put" in first
    assert "Mungchi does not appear in this clip." in first  # 시작 1컷은 뭉치 없음(점검 C6)
    run_cut = [c[0] for c in video.calls if INTRO_CUTS[3]["action"] in c[0]][0]
    assert "Only Mungchi is in this clip" in run_cut and "Do not show 강아지 보리" in run_cut
    again = [c[0] for c in video.calls if INTRO_CUTS[1]["action"] in c[0]]
    assert len(again) == 2 and "MORPH MORPH 사유" in again[1]
    intro = response.motions["INTRO"]
    # #779 자막은 자막 있는 컷(시작 1·2·4·6)만, 시각은 6컷 × 4초 녹아드는 전환 경계
    assert [(c.start, c.end, c.text) for c in intro.captions] == [
        (0.0, 3.75, INTRO_CUTS[0]["caption"]),
        (3.75, 7.25, INTRO_CUTS[1]["caption"]),
        (10.75, 14.25, INTRO_CUTS[3]["caption"]),
        (17.75, 21.5, INTRO_CUTS[5]["caption"]),
    ]
    assert response.motions["MON"].captions == []


def test_fake_video_provider_skips_video_review_with_one_warning() -> None:
    """#716: 영상 대역(VIDEO_PROVIDER=fake)이면 컷 검토 없이 통과(멈춤 확인은 그대로),
    경고 한 줄."""
    video = FakeVideoClient()
    review = review_llm(video=lambda u: {"MORPH": "FAIL"})  # 불리면 모든 컷 FAIL
    response = run(
        gen_llm(),
        review,
        image=FakeImageClient(),
        video=video,
        storage=MemoryThemeStorage(),
        settings={"video_provider": "fake"},
    )
    assert response.failure is None
    assert set(response.videos) == {"INTRO", "OUTRO"}
    assert len(video.calls) == 9  # Veo 9컷(표정 그림 두 장 컷 3개는 Veo 없음), 다시 없음
    assert reviewed(review, GeneratedVideoReview) == 0
    assert reviewed(review, GeneratedImageReview) == 20  # 그림은 실제 설정이라 그대로 검토
    assert all(STILL_NOTE not in w.reason for w in response.warnings)  # 대신한 컷 없음
    fake = [w for w in response.warnings if w.reason == video_node.FAKE_REVIEW_SKIPPED]
    assert [(w.stage, w.item) for w in fake] == [("VIDEO", "ALL")]


def test_fake_video_provider_still_checks_freezes() -> None:
    """#716: 영상 대역이어도 멈춤 확인(ffmpeg, 모델 아님)은 그대로 해서 멈춘 컷은 다시 만든다."""

    class StillOnce(FakeVideoClient):
        stilled = False

        async def generate(
            self, prompt: str, first: bytes, last: bytes | None = None, **kw: Any
        ) -> bytes:
            clip = await super().generate(prompt, first, last, **kw)
            if (
                not self.stilled and INTRO_CUTS[0]["action"] in prompt
            ):  # 시작 1컷 처음 한 번만 정지 화면
                self.stilled = True
                return await asyncio.to_thread(color_clip, 1, kw["seconds"], True)
            return clip

    video = StillOnce()
    response = run(
        gen_llm(),
        review_llm(),
        image=FakeImageClient(),
        video=video,
        storage=MemoryThemeStorage(),
        settings={"video_provider": "fake"},
    )
    assert response.failure is None and set(response.videos) == {"INTRO", "OUTRO"}
    assert len(video.calls) == 10  # Veo 9컷 + 멈춘 1컷을 다시 만듦


def test_failed_video_cut_becomes_still_cut() -> None:
    """끝내 검토를 못 넘은 컷은 첫 그림을 천천히 확대하는 움직이는 그림 컷으로 대신하고 장면 영상은
    남김(2026-11-11: 뭉치 컷은 영상 모델이 작은 손을 팔로 키워 거의 다 실패). 다시 만들기는 1번,
    그다음 안전한 버전 1번(#779)까지 실패할 때만."""

    def verdicts(user: dict) -> dict[str, str]:
        return {"CONTINUITY": "FAIL"} if user["scene"] == INTRO_CUTS[1]["scene"] else {}

    video, storage = FakeVideoClient(), MemoryThemeStorage()
    response = run(
        gen_llm(), review_llm(video=verdicts), image=FakeImageClient(), video=video, storage=storage
    )
    assert response.failure is None and set(response.videos) == {"INTRO", "OUTRO"}
    assert len(video.calls) == 9 + 1 + 1  # 그 컷만 다시 1번(max_regen 1) + 안전한 버전 1번
    safe = video.calls[-1][0]  # 안전한 버전: 사건 클로즈업은 다가가지 않고 그대로(#779)
    assert "stays close and steady" in safe and "push-in" not in safe
    assert [(w.stage, w.item) for w in response.warnings] == [("VIDEO", "INTRO")]
    assert response.warnings[0].reason == "INTRO2 영상 CONTINUITY CONTINUITY 사유, " + STILL_NOTE
    body, _ = storage.objects[response.videos["INTRO"]]
    assert mp4_seconds(body) == pytest.approx(6 * 4 - 5 * 0.5, abs=0.15)
    outro = response.motions["OUTRO"]
    assert [c.end for c in outro.captions][-1] == pytest.approx(21.5)


def test_still_clip_length_and_size() -> None:
    clip = still_clip(tiny_png(3), 4, (64, 36))
    assert mp4_seconds(clip) == pytest.approx(4, abs=0.1)


def test_two_face_clip_length() -> None:
    """표정 그림 두 장 컷(#779 A안): 두 그림을 녹아드는 전환으로 이어 요청 길이 그대로."""
    clip = two_face_clip(tiny_png(3), tiny_png(4), 4, (64, 36))
    assert mp4_seconds(clip) == pytest.approx(4, abs=0.1)


def test_close_up_cuts_skip_veo_and_join_two_faces() -> None:
    """뭉치 혼자 클로즈업(시작 5, 종료 1·4)은 Veo를 부르지 않고 첫 그림 + 끝 표정 그림을 이어 붙임
    (#779 사용자 결정 2026-11-20 A안: Veo는 구도와 상관없이 팔을 만들어 0/3·0/3, 그림 두 장 3/3).
    영상 길이·자막 시각은 그대로(6컷 × 4초)."""
    video, storage = FakeVideoClient(), MemoryThemeStorage()
    response = run(gen_llm(), review_llm(), image=FakeImageClient(), video=video, storage=storage)
    assert response.failure is None and response.warnings == []
    assert len(video.calls) == 9  # Veo는 사람·함께·달리기 9컷만
    close = {INTRO_CUTS[4]["action"], OUTRO_CUTS[0]["action"], OUTRO_CUTS[3]["action"]}
    assert not any(a in c[0] for c in video.calls for a in close)
    for scene in ("INTRO", "OUTRO"):
        body, _ = storage.objects[response.videos[scene]]
        assert mp4_seconds(body) == pytest.approx(6 * 4 - 5 * 0.5, abs=0.15)


def test_end_face_failure_replaces_only_that_cut() -> None:
    """끝 표정 그림이 끝내 떨어지면 장면 영상을 빼지 않고 그 컷만 움직이는 그림(경고 IMAGE·VIDEO).
    첫 그림이 실패하면 끝 표정 그림은 그리지 않음."""

    def verdicts(user: dict) -> dict[str, str]:
        end = user.get("mungchiMouth") == "웃는 입" and user["scene"] == OUTRO_CUTS[0]["scene"]
        return {"MUNGCHI": "FAIL"} if end else {}

    response = run(
        gen_llm(),
        review_llm(image=verdicts),
        image=FakeImageClient(),
        video=FakeVideoClient(),
        storage=MemoryThemeStorage(),
    )
    assert response.failure is None and set(response.videos) == {"INTRO", "OUTRO"}
    assert {(w.stage, w.item) for w in response.warnings} == {
        ("IMAGE", "OUTRO1END"),
        ("VIDEO", "OUTRO"),
    }
    assert any("OUTRO1 영상 FACE 끝 표정 그림 없음" in w.reason for w in response.warnings)
    assert "OUTRO1END" not in response.regen["assets"]

    def start_fails(user: dict) -> dict[str, str]:
        return {"TEXT": "FAIL"} if user["scene"] == INTRO_CUTS[4]["scene"] else {}

    image = FakeImageClient()
    failed = run(
        gen_llm(), review_llm(image=start_fails), image=image, storage=MemoryThemeStorage()
    )
    assert failed.failure is None
    assert not any("Change only Mungchi's mouth" in c[0] and "INTRO" in c[0] for c in image.calls)
    assert any(w.item == "INTRO5END" and image_node.NO_START in w.reason for w in failed.warnings)


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
    assert set(response.videos) == {"INTRO"} and len(video.calls) == 5  # 시작 Veo 5컷
    assert {(w.stage, w.item) for w in response.warnings} == {("VIDEO", "OUTRO")}
    assert all(w.reason.startswith("OUTRO2 그림 TEXT") for w in response.warnings)
    assert "OUTRO" in response.images  # 4번째 컷 그림은 통과
    assert response.motions["OUTRO"].captions == []  # 영상이 없으면 문구 없음


@pytest.mark.parametrize("item", ["FRAME", "FLOW", "PEOPLE"])
def test_cut_image_failing_only_soft_items_is_kept_with_warning(item: str) -> None:
    """#779(사용자 결정 2026-11-20): 6컷 컷 그림이 구도·이어짐·인물 닮음에서만 끝내 떨어지면 마지막
    그림을 쓰고 경고(컷 하나 때문에 그 장면 영상 전체가 빠지지 않게). 종료 5컷은 사람 컷(PEOPLE)·
    앞 컷 잇기(FLOW)·구도 틀(FRAME)이 모두 있는 컷."""

    def verdicts(user: dict) -> dict[str, str]:
        return {item: "FAIL"} if user["scene"] == OUTRO_CUTS[4]["scene"] else {}

    video, image = FakeVideoClient(), FakeImageClient()
    response = run(
        gen_llm(),
        review_llm(image=verdicts),
        image=image,
        video=video,
        storage=MemoryThemeStorage(),
    )
    assert response.failure is None
    assert set(response.videos) == {"INTRO", "OUTRO"} and len(video.calls) == 9
    assert {(w.stage, w.item) for w in response.warnings} == {("IMAGE", "OUTRO5")}
    note = image_node.SOFT_NOTE
    assert all(w.reason == f"{item} {item} 사유 ({note})" for w in response.warnings)
    # 다시 그리기는 상한까지 다 해 본 뒤에 마지막 그림을 씀
    assert len(prompts_with(image, OUTRO_CUTS[4]["scene"])) >= get_settings().theme_max_regen + 1


def test_image_review_gets_start_mouth_only_for_moving_mungchi_cuts() -> None:
    """그림 검토가 시작 입 모양(mungchiMouth)을 받는 컷: 움직임이 있는 6컷 뭉치 컷(시작 5·6, 종료
    1·4·6). 종료 1컷은 다문 일자 입(갈래 확인 2026-11-20: 검토가 동작 글의 뒤 표정으로 경고)."""
    seen: dict[str, list[str | None]] = {}

    def verdicts(user: dict) -> dict[str, str]:
        seen.setdefault(user["scene"], []).append(user.get("mungchiMouth"))
        return {}

    run(
        gen_llm(), review_llm(image=verdicts), image=FakeImageClient(), storage=MemoryThemeStorage()
    )
    # 표정 그림 두 장 컷(#779 A안): 첫 그림은 시작 입, 그다음 끝 표정 그림은 끝 입
    assert seen[INTRO_CUTS[4]["scene"]] == ["작은 동그란 o 입", "다문 일자 입"]
    assert seen[OUTRO_CUTS[0]["scene"]] == ["다문 일자 입", "웃는 입"]
    assert seen[OUTRO_CUTS[3]["scene"]] == ["작은 동그란 o 입", "웃는 입"]
    assert seen[INTRO_CUTS[3]["scene"]] == [None]  # 달리기 컷(움직임 줄 없음)
    assert seen[OUTRO_CUTS[2]["scene"]] == [None]  # 사람 컷


def test_cut_image_failing_a_hard_item_is_still_dropped_even_with_soft_fails() -> None:
    """장면 맞음(SCENE_FIT) 같은 다른 항목이 함께 떨어진 그림은 쓰지 않음. 미션 그림은 구도·인물
    항목만 떨어져도 예전처럼 실패(IMAGE)."""

    def cut(user: dict) -> dict[str, str]:
        hit = user["scene"] == OUTRO_CUTS[4]["scene"]
        return {"FRAME": "FAIL", "SCENE_FIT": "FAIL"} if hit else {}

    response = run(
        gen_llm(),
        review_llm(image=cut),
        image=FakeImageClient(),
        video=FakeVideoClient(),
        storage=MemoryThemeStorage(),
    )
    assert set(response.videos) == {"INTRO"}
    assert {(w.stage, w.item) for w in response.warnings} == {("VIDEO", "OUTRO")}

    def mission(user: dict) -> dict[str, str]:
        return {"PEOPLE": "FAIL"} if scene_is(user, "마을 tue 길") else {}

    failed = run(
        gen_llm(), review_llm(image=mission), image=FakeImageClient(), storage=MemoryThemeStorage()
    )
    assert failed.failure is not None and failed.failure.stage == "IMAGE"


def test_video_skipped_near_deadline() -> None:
    video = FakeVideoClient()
    response = run(
        gen_llm(),
        review_llm(),
        image=FakeImageClient(),
        video=video,
        storage=MemoryThemeStorage(),
        deadline_in=290,  # theme_video_min_seconds(300) 미만
    )
    assert response.failure is None and video.calls == [] and response.videos == {}
    assert [(w.stage, w.item) for w in response.warnings] == [("VIDEO", "ALL")]
    assert "마감" in response.warnings[0].reason
    assert len(response.motions) == 7


def test_video_runs_when_min_seconds_left() -> None:
    """컷 1개 상한(400초)보다 짧게 남아도 기준(300초) 이상이면 영상을 만든다(마감까지만 기다림).
    예전 기준(400 + 60초)은 줄거리를 한 번만 다시 만들어도 영상이 빠졌음(실측 2026-11-11)."""
    video = FakeVideoClient()
    response = run(
        gen_llm(),
        review_llm(),
        image=FakeImageClient(),
        video=video,
        storage=MemoryThemeStorage(),
        deadline_in=400,
    )
    assert response.failure is None and set(response.videos) == {"INTRO", "OUTRO"}
    assert len(video.calls) == 9  # Veo 9컷(표정 그림 두 장 컷 3개는 Veo 없음)


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
    assert "No letters, numbers or real emblems" in prompts.outfit_prompt(theme)
    assert "fits Mungchi tightly over the lower half" in prompts.outfit_prompt(theme)  # #779
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
    assert user["evidenceKind"] == "SIGHTING" and user["answerAllowed"] is False
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
    # 장면 그림 7장 + 재료 그림 17장(테마 옷 뭉치·인물 그림·컷 첫 그림 12장·끝 표정 그림 3장,
    # #537·#779)
    assert set(body["images"]) == set(SCENES) and len(storage.objects) == 24
    assert set(body["motions"]["MON"]["camera"]) == {"from", "to", "seconds"}
    assert DAYS[0] in body["motions"]


def test_cut_freezes_trims_ends_and_fails_middle() -> None:
    """앞뒤 정지 화면은 잘라 내고 실제 길이를 돌려줌, 중간에 0.7초 이상 멈추면 FREEZE(그 컷을
    다시 만듦), 0.5~0.7초는 WARN(#779: 3테마 실행에서 0.5~0.6초 멈춤 3건이 컷을 떨어뜨림). 처음
    실측에서는 컷 안 0.4~0.9초 멈춤이 재생 중 끊김으로 보였음."""
    from app.llm.media import color_clip, concat_mp4
    from app.theme_draft.nodes.video import cut_freezes

    ends = concat_mp4(
        [color_clip(1, 1, still=True), color_clip(2, 3), color_clip(3, 1, still=True)]
    )
    trimmed, length, bad, warns = cut_freezes(ends, 5)
    assert bad == [] == warns and length == pytest.approx(3, abs=0.4) and trimmed != ends
    middle = concat_mp4([color_clip(4, 2), color_clip(5, 1, still=True), color_clip(6, 2)])
    _, _, bad, warns = cut_freezes(middle, 5)
    assert len(bad) == 1 and bad[0].startswith("FREEZE ") and warns == []
    short = concat_mp4([color_clip(4, 2), color_clip(5, 0.6, still=True), color_clip(6, 2)])
    _, _, bad, warns = cut_freezes(short, 4)
    assert bad == [] and len(warns) == 1 and warns[0].startswith("FREEZE 2.0~2.7초")
    _, _, bad, _ = cut_freezes(color_clip(7, 4, still=True), 4)
    assert len(bad) == 1 and bad[0].startswith("FREEZE ")


def test_video_prompt_and_review_keep_everyone_and_outfit() -> None:
    """영상 지시문·금지 조건·검토가 인물 유지·뭉치 모양·옷 유지를 다룸(실측: 인물이 사라지고 팔이
    생기고 옷이 바뀜). 검토는 첫 장면 + 1초마다 장면, 항목 CONTINUITY."""
    from app.theme_draft import prompts

    theme = valid_theme()
    text = prompts.video_prompt(theme, "OUTRO", 6, OUTRO_CUTS[5], [])  # 함께 나오는 컷
    assert "Nobody walks out of the frame, disappears, appears or merges" in text
    assert "never arms" in text and "stay exactly as in the first frame" in text  # #779 손 문구
    assert "nobody is cut off" in text and "push-in" not in text  # 넓은 장면은 다가가지 않음
    close = prompts.video_prompt(theme, "OUTRO", 4, OUTRO_CUTS[3], [])  # #779 뭉치 클로즈업만
    assert "slow gentle push-in toward the face" in close
    for word in ("character leaving the frame", "wings", "outfit change", "freeze frame"):
        assert word in VIDEO_NEGATIVE
    assert "CONTINUITY" in VIDEO_REVIEW_IDS and "CONTINUITY:" in prompts.VIDEO_REVIEW_SYSTEM
    assert (
        "한눈에 알아보게" in prompts.PLAN_SYSTEM and "화면 밖으로 나가거나" in prompts.PLAN_SYSTEM
    )


def test_video_prompt_keeps_held_outfit_props_but_blocks_grabbing() -> None:
    """영상 생성도 검토와 같은 기준(사용자 결정 2026-11-15, 생성 쪽도 B안): 첫 그림에 든 차림 소품은
    그대로 들어도 되고, 새 물건·사건 대상을 집거나 건네는 것과 손 들기·팔/날개 생김은 막음."""
    from app.theme_draft import prompts

    theme = valid_theme()
    text = prompts.video_prompt(theme, "OUTRO", 6, OUTRO_CUTS[5], [])  # 뭉치가 나오는 컷
    assert (
        "never picks up, lifts, hugs, hands over or receives anything, especially 강아지 보리"
        in text
    )
    assert "already holds in the first frame (such as a magnifying glass) stays in its hand" in text
    assert "moves its hands" in text and "never arms" in text  # #779 뭉치 거의 정지·손 문구
    assert "holds, hugs or hands over anything" not in text  # 예전 "아무것도 들지 않음" 문구는 없음
    assert "Mungchi grabbing or handing over objects" in VIDEO_NEGATIVE
    assert "Mungchi holding objects" not in VIDEO_NEGATIVE
    assert "Mungchi raising hands" in VIDEO_NEGATIVE and "wings" in VIDEO_NEGATIVE


def test_video_review_flags_target_grab_but_not_outfit_props() -> None:
    """영상 검토 CONTINUITY 결함은 뭉치가 사건 대상을 잡거나 건네는 것(사람과 함께 잡기 포함)과
    뭉치 팔·다리·얼굴이 원래 모습에서 벗어나는 것(#779 판정 예시 기준). 차림 소품(돋보기·모자 등)을
    쥐거나 지닌 것은 결함이 아님(실측 2026-11-11 종료 3컷, 사용자 결정 2026-11-15 B안: 그림 검토
    MUNGCHI가 손에 든 물건을 허용해 첫 그림 통과·영상 실패로 어긋나지 않게)."""
    from app.theme_draft import prompts

    system = prompts.VIDEO_REVIEW_SYSTEM
    continuity = system.split("CONTINUITY:")[1].split("MORPH:")[0]
    assert "뭉치의 팔·다리·얼굴이 원래 모습에서 벗어나지 않는지" in continuity
    assert (
        "사건 대상(target, 찾는 대상 등 이야기 속 물건)을 잡거나 들거나 안거나 건네거나"
        in continuity
    )
    assert "사람과 함께 잡아도 결함" in continuity
    assert "차림 소품" in continuity and "결함이 아니다" in continuity
    assert "뭉치 손이 물건을 쥐고 있어도 결함" not in system  # 예전(08eb4f5b) 넓은 문구는 없음
    morph = system.split("MORPH:")[1].split("ANSWER_HINT:")[0]
    assert "뭉치가 쥔 차림 소품은 동작에 따라 달라도 된다" in morph
    # 그림 검토는 손에 든 물건을 허용(영상과 같은 기준)
    assert "손에 든 물건·자세·표정은" in prompts.IMAGE_REVIEW_SYSTEM
    # 검토 입력에 사건 대상 이름이 들어가 판단 근거가 됨
    user = prompts.video_review_user(
        {"target": "꼬마 로봇", "answer": "소리방"}, {"scene": "s", "action": "a"}, True
    )
    assert '"target": "꼬마 로봇"' in user
