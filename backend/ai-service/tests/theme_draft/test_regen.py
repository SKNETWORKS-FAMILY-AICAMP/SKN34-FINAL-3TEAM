"""부분 다시 생성(#537) 시험: 재료 묶음(regen), 고른 대상만 다시 만들기, 대상 밖 고치기 거절.

실제 OpenAI·Google·S3는 부르지 않는다(test_media_graph와 같은 가짜 클라이언트·MemoryThemeStorage).
원래 결과(base)는 learning이 하듯 응답에서 failure·versions를 뺀 JSON으로 만든다.
"""

import asyncio
from typing import Any

import pytest
from pydantic import ValidationError

from app.llm.media import FakeImageClient, FakeVideoClient
from app.theme_draft.checks import DAYS
from app.theme_draft.models import GeneratedStoryReview, ThemeDraftRequest, ThemeWarning
from app.theme_draft.nodes.images import KEPT_NOTE
from app.theme_draft.regen import OUTSIDE_REASON, TARGET_ORDER, keep_warnings, plan_of
from app.theme_draft.storage import MemoryThemeStorage, scene_key
from tests.theme_draft.fixtures import INTRO_CUTS, story_review
from tests.theme_draft.helpers import request_body
from tests.theme_draft.test_media_graph import gen_llm, review_llm, run, scene_is

SCENES = ("INTRO", "MON", "TUE", "WED", "THU", "FRI", "OUTRO")
CUT_ASSETS = {f"{s}{i}" for s in ("INTRO", "OUTRO") for i in range(1, 5)}
RUN_ID = "0123456789abcdef0123456789abcdef"


def full(review: Any = None) -> tuple[Any, MemoryThemeStorage]:
    storage = MemoryThemeStorage()
    response = run(
        gen_llm(),
        review or review_llm(),
        image=FakeImageClient(),
        video=FakeVideoClient(),
        storage=storage,
    )
    assert response.failure is None
    return response, storage


def base_of(response: Any) -> dict:
    return response.model_dump(by_alias=True, mode="json", exclude={"failure", "versions"})


def partial(response: Any, storage: MemoryThemeStorage, targets: list[str], **kw: Any) -> tuple:
    gen, review = kw.pop("gen", None) or gen_llm(), kw.pop("review", None) or review_llm()
    image, video = FakeImageClient(), FakeVideoClient()
    out = run(
        gen,
        review,
        image=image,
        video=video,
        storage=storage,
        regenerate={"targets": targets, "base": base_of(response)},
    )
    return out, gen, review, image, video


def others(values: dict, skip: str) -> dict:
    return {k: v for k, v in values.items() if k != skip}


# --- 재료 묶음 ------------------------------------------------------------------------


def test_full_run_keeps_regen_materials() -> None:
    response, storage = full()
    regen = response.regen
    assert regen is not None and regen["version"] == 1
    assert regen["targets"] == list(TARGET_ORDER)  # 재료가 다 있으면 14개 모두
    assert set(regen["assets"]) == {"OUTFIT", "PERSON", *CUT_ASSETS}
    assert regen["assets"]["PERSON"] == regen["assets"]["INTRO1"]  # 인물 기준 = 시작 1컷
    assert all(key in storage.objects for key in regen["assets"].values())
    # 응답 theme에 없는 내부 칸(콘티·수사 연결 문장)이 regen.theme에 있음
    assert len(regen["theme"]["introCuts"]) == 4 and regen["theme"]["days"][0]["missionHook"]
    assert set(regen["videoDurations"]) == {"INTRO", "OUTRO"}


def test_no_image_setup_allows_only_mission_targets() -> None:
    response = run(gen_llm(), review_llm())
    assert response.regen is not None
    assert response.regen["targets"] == [f"MISSION:{d}" for d in DAYS]
    assert response.regen["assets"] == {}


def test_failed_cut_image_drops_only_that_video_target() -> None:
    review = review_llm(
        image=lambda u: {"SAFETY": "FAIL"} if scene_is(u, INTRO_CUTS[1]["scene"]) else {}
    )
    response, _ = full(review)
    assert "VIDEO:INTRO" not in response.regen["targets"]
    assert "VIDEO:OUTRO" in response.regen["targets"]
    assert "IMAGE:INTRO" in response.regen["targets"]  # 컷 그림은 다시 그릴 수 있음


def test_text_failure_has_no_regen() -> None:
    gen = gen_llm()
    review = review_llm()
    review.handlers[GeneratedStoryReview] = lambda n, d: story_review({"SAFETY": "FAIL"})
    response = run(gen, review)
    assert response.failure is not None and response.failure.stage == "REVIEW"
    assert response.regen is None


# --- 고른 대상만 다시 만들기 ----------------------------------------------------------------


def test_video_only_refilms_that_video_from_kept_cut_images() -> None:
    response, storage = full()
    out, gen, review, image, video = partial(response, storage, ["VIDEO:INTRO"])
    assert out.failure is None
    assert image.calls == []  # 그림은 다시 그리지 않음
    assert len(video.calls) == 4  # 시작 영상 컷 4개만
    kept = {storage.objects[response.regen["assets"][f"INTRO{i}"]][0] for i in range(1, 5)}
    assert {c[1] for c in video.calls} == kept  # 원래 컷 첫 그림에서 다시 찍음
    assert out.videos["INTRO"] != response.videos["INTRO"]
    assert out.videos["OUTRO"] == response.videos["OUTRO"]
    assert out.images == response.images
    assert (out.theme, out.missions, out.dialogues) == (
        response.theme,
        response.missions,
        response.dialogues,
    )
    assert "INTRO" in out.motions and others(out.motions, "INTRO") == others(
        response.motions, "INTRO"
    )
    assert gen.count("GeneratedTheme") == gen.count("GeneratedDraft") == 0
    assert gen.count("GeneratedDialogue") == 0 and gen.count("GeneratedMotion") == 1
    assert review.count("GeneratedStoryReview") == 0
    assert out.regen["targets"] == response.regen["targets"]  # 이어서 또 부분 다시 생성 가능


def test_day_image_redraws_only_that_image_with_kept_references() -> None:
    response, storage = full()
    out, gen, _, image, video = partial(response, storage, ["IMAGE:TUE"])
    assert out.failure is None
    assert len(image.calls) == 1 and image.calls[0][1] == 2  # [원래 옷 뭉치, 원래 인물 기준]
    assert out.images["TUE"] != response.images["TUE"]
    assert others(out.images, "TUE") == others(response.images, "TUE")
    assert video.calls == [] and out.videos == response.videos
    assert gen.count("GeneratedMotion") == 1
    assert others(out.motions, "TUE") == others(response.motions, "TUE")
    assert out.regen["assets"] == response.regen["assets"]  # 재료 그림은 그대로


def test_intro_image_redraws_cuts_and_refilms_intro() -> None:
    response, storage = full()
    out, _, _, image, video = partial(response, storage, ["IMAGE:INTRO"])
    assert out.failure is None
    assert len(image.calls) == 4  # 시작 컷 첫 그림 4장
    assert image.calls[0][1] == 0  # 시작 1컷은 처음처럼 참조 없이
    assert len(video.calls) == 4
    assert out.images["INTRO"] != response.images["INTRO"]
    assert out.videos["INTRO"] != response.videos["INTRO"]
    assert out.videos["OUTRO"] == response.videos["OUTRO"]
    assert out.regen["assets"]["PERSON"] == response.regen["assets"]["PERSON"]  # 인물 기준 그대로
    assert out.regen["assets"]["INTRO1"] != response.regen["assets"]["INTRO1"]


def test_failed_intro_cut_keeps_original_intro() -> None:
    response, storage = full()
    review = review_llm(
        image=lambda u: {"SAFETY": "FAIL"} if scene_is(u, INTRO_CUTS[1]["scene"]) else {}
    )
    out, _, _, _, video = partial(response, storage, ["IMAGE:INTRO"], review=review)
    assert out.failure is None
    assert video.calls == []
    assert out.images["INTRO"] == response.images["INTRO"]
    assert out.videos["INTRO"] == response.videos["INTRO"]
    assert out.motions["INTRO"] == response.motions["INTRO"]
    assert any(
        w.stage == "IMAGE" and w.item == "INTRO2" and KEPT_NOTE in w.reason for w in out.warnings
    )


def test_mission_redoes_that_day_text_review_image_and_motion() -> None:
    response, storage = full()
    out, gen, review, image, video = partial(response, storage, ["MISSION:WED"])
    assert out.failure is None
    assert gen.count("GeneratedTheme") == 0  # 줄거리는 다시 만들지 않음
    assert gen.count("GeneratedDraft") == gen.count("GeneratedDraft", "WED") >= 1
    assert gen.count("GeneratedDialogue") == gen.count("GeneratedDialogue", "WED") == 1
    assert review.count("GeneratedStoryReview") == 1
    assert len(image.calls) == 1 and video.calls == []
    assert out.images["WED"] != response.images["WED"]
    assert others(out.images, "WED") == others(response.images, "WED")
    assert [m for m in out.missions if m.day != "WED"] == [
        m for m in response.missions if m.day != "WED"
    ]


def test_review_asking_for_story_rewrite_fails_instead_of_full_run() -> None:
    response, storage = full()
    review = review_llm()
    review.handlers[GeneratedStoryReview] = lambda n, d: story_review({"ANSWER_HINT": "FAIL"})
    out, gen, _, image, _ = partial(response, storage, ["MISSION:WED"], review=review)
    assert out.failure is not None and out.failure.stage == "REVIEW"
    assert OUTSIDE_REASON in out.failure.reasons
    assert gen.count("GeneratedTheme") == 0 and image.calls == []


def test_review_asking_for_other_day_fails() -> None:
    response, storage = full()
    review = review_llm()
    review.handlers[GeneratedStoryReview] = lambda n, d: story_review(
        {"GRADE_VOCAB": "FAIL"}, {"GRADE_VOCAB": ["MON"]}
    )
    out, gen, *_ = partial(response, storage, ["MISSION:WED"], review=review)
    assert out.failure is not None and OUTSIDE_REASON in out.failure.reasons
    assert gen.count("GeneratedDraft", "MON") == 0


def test_review_asking_for_target_day_retries_that_day() -> None:
    response, storage = full()
    review = review_llm()
    review.handlers[GeneratedStoryReview] = lambda n, d: story_review(
        {"GRADE_VOCAB": "FAIL" if n == 1 else "PASS"}, {"GRADE_VOCAB": ["WED"]}
    )
    out, gen, *_ = partial(response, storage, ["MISSION:WED"], review=review)
    assert out.failure is None
    assert gen.count("GeneratedDialogue", "WED") == 2


# --- 요청 검증·작은 단위 -----------------------------------------------------------------


def test_request_rejects_target_without_material() -> None:
    response = run(gen_llm(), review_llm())  # 그림 없음 → 미션 대상만
    body = request_body(regenerate={"targets": ["VIDEO:INTRO"], "base": base_of(response)})
    with pytest.raises(ValidationError, match="다시 만들 수 없는 대상"):
        ThemeDraftRequest.model_validate(body)
    bad = base_of(response) | {"regen": {"targets": ["MISSION:MON"]}}  # version·theme 없음
    with pytest.raises(ValidationError, match="regen 형식"):
        ThemeDraftRequest.model_validate(
            request_body(regenerate={"targets": ["MISSION:MON"], "base": bad})
        )
    with pytest.raises(ValidationError):
        ThemeDraftRequest.model_validate(
            request_body(regenerate={"targets": [], "base": base_of(response)})
        )


def test_plan_of_targets() -> None:
    plan = plan_of(["VIDEO:OUTRO", "IMAGE:INTRO", "MISSION:FRI", "IMAGE:FRI"])
    assert plan.mission_days == ["FRI"]
    assert plan.images == ["FRI", "INTRO1", "INTRO2", "INTRO3", "INTRO4"]
    assert plan.videos == ["INTRO", "OUTRO"]
    assert plan.motions == ["INTRO", "FRI", "OUTRO"]


def test_keep_warnings_drops_only_redone_items() -> None:
    warnings = [
        ThemeWarning(stage="VIDEO", item="INTRO2", reason="a"),
        ThemeWarning(stage="VIDEO", item="OUTRO", reason="b"),
        ThemeWarning(stage="MOTION", item="INTRO", reason="c"),
        ThemeWarning(stage="REVIEW", item="GRADE_VOCAB MON", reason="d"),
        ThemeWarning(stage="IMAGE", item="TUE", reason="e"),
    ]
    kept = keep_warnings(warnings, plan_of(["VIDEO:INTRO"]))
    assert [w["reason"] for w in kept] == ["b", "d", "e"]
    kept = keep_warnings(warnings, plan_of(["MISSION:TUE"]))
    assert [w["reason"] for w in kept] == ["a", "b", "c"]


def test_asset_keys_and_memory_get() -> None:
    assert scene_key(RUN_ID, "OUTFIT", "png").endswith("/OUTFIT.png")
    assert scene_key(RUN_ID, "INTRO3", "png").endswith("/INTRO3.png")
    with pytest.raises(ValueError):
        scene_key(RUN_ID, "INTRO3", "mp4")  # 재료는 그림만
    with pytest.raises(ValueError):
        scene_key(RUN_ID, "INTRO5", "png")
    storage = MemoryThemeStorage()
    asyncio.run(storage.put("theme-drafts/x/OUTFIT.png", b"png", "image/png"))
    assert asyncio.run(storage.get("theme-drafts/x/OUTFIT.png")) == b"png"
