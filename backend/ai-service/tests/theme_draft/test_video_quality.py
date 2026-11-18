"""시작·종료 영상 품질(#779, 사용자 결정 2026-11-18).

실측(2026-11-18, Veo fast): 뭉치가 뛰거나 손을 쓰거나 제자리에서 통통 튀면 팔·흰 다리가 생기고,
뭉치가 거의 가만히 있고 사람·배경·카메라가 움직이면 모양이 유지됨. 출동 컷은 첫 그림부터 정면을 본
채 달리는 자세로 그리고 옆으로 달리게 하면 갈색 발이 유지되고 배경이 흘러 출동처럼 보임. 검토는
글로만 기준을 주면 판정이 흔들려 판정 예시 그림 2장(허용·결함)을 붙임.
"""

from typing import Any

from app.llm.media import FakeImageClient, FakeVideoClient
from app.theme_draft import checks, prompts
from app.theme_draft.nodes.video import REVIEW_EXAMPLES, review_examples
from app.theme_draft.storage import MemoryThemeStorage
from tests.theme_draft.fixtures import INTRO_CUTS, OUTRO_CUTS, valid_theme
from tests.theme_draft.test_media_graph import gen_llm, review_llm, run


def test_mungchi_bouncing_is_a_cut_action_but_running_is_allowed_in_go_cut() -> None:
    """통통 튀기도 뭉치 동작에서 뺌(흰 다리), 출동 컷(시작 3)만 달리기 허용. 화면 쪽으로 달려오는
    말은 출동 컷에서도 막음."""
    assert checks.cut_action_problems("뭉치가 제자리에서 통통 튄다")
    assert checks.cut_action_problems("뭉치가 기뻐서 깡충 뛴다")
    assert checks.cut_action_problems("뭉치가 옆으로 달려간다")  # 출동 컷이 아니면 걸림
    assert not checks.cut_action_problems("뭉치가 옆으로 힘차게 달려간다", may_run=True)
    assert checks.cut_action_problems("뭉치가 통통 튀어 간다", may_run=True)  # 튀기는 출동도 안 됨
    assert checks.cut_action_problems("뭉치가 화면 쪽으로 달려온다", may_run=True)
    assert not checks.cut_action_problems("지호가 손뼉을 치고 뭉치는 몸을 살짝 흔든다")


def test_check_cuts_allows_running_only_in_intro_go_cut() -> None:
    theme = valid_theme()
    assert "달려간다" in theme["introCuts"][2]["action"]
    assert not [b for b in checks.check_cuts(theme) if b.startswith("CUT_ACTION")]
    theme["outroCuts"][3]["action"] = "뭉치가 옆으로 힘차게 달려간다"
    assert [b for b in checks.check_cuts(theme) if b.startswith("CUT_ACTION outroCuts4.action")]


def test_plan_and_fix_rules_keep_mungchi_still_except_go_cut() -> None:
    assert "통통 튀기는 사람만" in prompts.PLAN_SYSTEM
    go_rule = "시작 3컷(출동)에서는 뭉치가 짧은 갈색 발로 옆으로 힘차게 달려간다"
    assert go_rule in prompts.PLAN_SYSTEM
    go_role = prompts.cut_roles(valid_theme(), "introCuts")[2]
    assert "짧은 갈색 발로 옆으로 힘차게 달려가고" in go_role


def test_go_cut_image_is_drawn_running_and_facing_the_viewer() -> None:
    theme = valid_theme()
    go = prompts.cut_image_prompt(theme, "INTRO", 3, INTRO_CUTS[2], [])
    arrive = prompts.cut_image_prompt(theme, "INTRO", 4, INTRO_CUTS[3], [])
    assert prompts.RUN_POSE in go and "never a side profile" in go
    assert prompts.RUN_POSE not in arrive


def test_video_prompt_story_beat_camera_and_mungchi_rules() -> None:
    """컷 역할·컷별 카메라로 이야기 흐름, 출동 컷만 달리기, 나머지는 뭉치 거의 정지, 배경 움직임은
    실내·실외를 나눔(모든 컷에 구름을 넣자 실내 벽에 구름이 생겼음)."""
    theme = valid_theme()
    go = prompts.video_prompt(theme, "INTRO", 3, INTRO_CUTS[2], [])
    assert prompts.MUNGCHI_RUN in go and prompts.MUNGCHI_STILL not in go
    assert f"Camera: {prompts.CAMERA_TEXT['TRACK_SIDE']}" in go
    assert f"Story beat of this clip (Korean): {prompts.cut_roles(theme, 'introCuts')[2]}" in go
    happy = prompts.video_prompt(theme, "OUTRO", 4, OUTRO_CUTS[3], [])
    assert prompts.MUNGCHI_STILL in happy and prompts.MUNGCHI_RUN not in happy
    assert all(line in happy for line in prompts.MUNGCHI_KEEP)
    assert "indoors, nothing floats inside the room (no clouds, no leaves)" in happy
    assert "hair clips and clothes as in the first frame" in happy  # 토끼 머리핀 → 토끼 귀
    assert "Small, gentle movements in place" not in happy  # 예전 움직임 제한 문구는 없음
    first = prompts.video_prompt(theme, "INTRO", 1, INTRO_CUTS[0], [])
    assert "Mungchi does not appear in this clip." in first
    assert f"Camera: {prompts.CAMERA_TEXT['PAN_SIDE']}" in first  # 콘티 camera 없음 → 기본값
    for word in ("white legs", "dog nose", "brown hands", "clouds indoors", "page curl"):
        assert word in prompts.VIDEO_NEGATIVE


def test_video_review_judges_mungchi_with_examples_face_hands_and_hair_clips() -> None:
    system = prompts.VIDEO_REVIEW_SYSTEM
    assert "마지막 두 장은 뭉치 판정 예시" in system
    continuity = system.split("CONTINUITY:")[1].split("MORPH:")[0]
    for text in (
        "짧은 갈색 발로 걷거나 달리거나",
        "흰(몸 색) 다리",
        "코·주둥이",
        "갈색·어두운 덩어리",
        "토끼 머리핀이 토끼 귀로",
    ):
        assert text in continuity


def test_video_review_gets_judgement_examples_after_frames() -> None:
    """검토 그림 = [첫 그림, 1초마다 장면…, 허용 예시, 결함 예시]."""
    assert all(p.exists() and p.read_bytes()[:2] == b"\xff\xd8" for p in REVIEW_EXAMPLES)  # JPEG
    review = review_llm()
    seen: list[list[Any]] = []
    original = review._request

    async def capture(request: Any) -> Any:
        if request.output.__name__ == "GeneratedVideoReview":
            seen.append(list(request.images))
        return await original(request)

    review._request = capture  # type: ignore[method-assign]
    run(
        gen_llm(),
        review,
        image=FakeImageClient(),
        video=FakeVideoClient(),
        storage=MemoryThemeStorage(),
    )
    assert len(seen) == 8  # 시작·종료 4컷씩
    assert all(len(images) >= 4 and images[-2:] == list(review_examples()) for images in seen)


# --- 만화 연출(#779 시제품 2026-11-18): 컷마다 다른 구도·이동·카메라, 정지 그림 대책 ---


def test_storyboard_rules_scene_is_first_frame_cartoon_staging_and_captions() -> None:
    """scene은 첫 장면(예전 "컷 끝 장면"은 이동 컷이 거꾸로 움직임), 컷마다 다른 구도, 사건 컷은
    가까운 장면, 이동 컷은 가는 쪽을 봄, 하나뿐인 물건은 한 명, 글자 대신 그림, 문구 4줄로
    이야기."""
    plan = prompts.PLAN_SYSTEM
    assert "scene은 그 컷이 시작하는 첫 장면" in plan and "그 컷 끝에 보이는 장면" not in plan
    for text in (
        "컷마다 장소의 다른 곳·다른 구도·다른 장면 크기",
        "시작 2컷(사건)은 사건이 한눈에 보이는 가까운 장면",
        "그 인물이 가는 쪽을 보고(뒷모습·옆모습)",
        "드는 사람을 한 명만",
        "글자 없이 그림·기호",
        "caption 4줄만 읽어도 이야기가 이어진다",
        "뭉치 역할과 사건을 잇는 말",
        "FOLLOW_BEHIND",
        "HOLD_CLOSE",
    ):
        assert text in plan
    fix = prompts.fix_rules(valid_theme(), "introCuts1.scene")
    assert any("컷이 시작하는 첫 모습" in r for r in fix)
    caption = prompts.fix_rules(valid_theme(), "introCuts2.caption")
    assert any("그 컷 영상에 보이는 일만" in r for r in caption)


def test_entering_through_a_door_is_not_an_approach_word() -> None:
    """'들어간'은 뺌(카메라가 뒤에서 따라가며 문 안으로 들어가는 컷), 화면 밖으로 나가기는 막음."""
    assert not checks.cut_action_problems("지호가 문을 지나 놀이터 안으로 걸어 들어간다", False)
    assert checks.cut_action_problems("지호가 걸어서 화면 밖으로 나간다", False)


def test_cut_camera_menu_go_cut_and_defaults() -> None:
    """정해 둔 카메라 중 콘티가 고름(기준안), 출동 컷은 늘 옆에서 따라감, 없거나 목록 밖이면
    역할별 기본값."""
    cut = {**INTRO_CUTS[0], "camera": "FOLLOW_BEHIND"}
    assert prompts.cut_camera("INTRO", 1, cut) == "FOLLOW_BEHIND"
    assert prompts.cut_camera("INTRO", 3, {**INTRO_CUTS[2], "camera": "PAN_SIDE"}) == "TRACK_SIDE"
    assert prompts.cut_camera("INTRO", 2, INTRO_CUTS[1]) == "HOLD_CLOSE"  # 예전 테마: 역할별
    assert prompts.cut_camera("OUTRO", 1, {**OUTRO_CUTS[0], "camera": "PUSH_IN"}) == "PAN_SIDE"
    assert "push" not in " ".join(prompts.CAMERA_TEXT.values()).lower()
    text = prompts.video_prompt(valid_theme(), "INTRO", 1, cut, [])
    assert f"Camera: {prompts.CAMERA_TEXT['FOLLOW_BEHIND']}" in text
    assert "others may leave the view only because the camera moves away" in text
    assert "nobody walks on or through walls" in text and "stays one object" in text
    assert "like a lively cartoon" in text
    for word in ("walking on walls", "passing through objects", "duplicated objects"):
        assert word in prompts.VIDEO_NEGATIVE


def test_cut_images_use_own_framing_close_shot_and_pictures_instead_of_letters() -> None:
    theme = valid_theme()
    close = prompts.cut_image_prompt(
        theme, "INTRO", 2, INTRO_CUTS[1], []
    )  # 사건 컷 기본 HOLD_CLOSE
    wide = prompts.cut_image_prompt(theme, "INTRO", 1, INTRO_CUTS[0], [])
    assert prompts.CLOSE_SHOT in close and prompts.CLOSE_SHOT not in wide
    for text in (close, wide):
        assert prompts.CUT_FRAMING in text and prompts.WRITTEN_THINGS in text
    sheet = prompts.characters_prompt(theme)
    assert "Draw only these people" in sheet and "No Mungchi" in sheet
    assert all(c["name"] in sheet for c in theme["characters"])


def test_safe_video_prompt_reduces_motion_and_keeps_close_shot() -> None:
    theme = valid_theme()
    go = prompts.video_prompt(theme, "INTRO", 3, INTRO_CUTS[2], [], safe=True)
    assert prompts.MUNGCHI_GO_SAFE in go and prompts.MUNGCHI_RUN not in go
    assert "The people make small, gentle movements" in go
    assert f"Camera: {prompts.CAMERA_TEXT['PAN_SIDE']}" in go
    close = prompts.video_prompt(theme, "INTRO", 2, INTRO_CUTS[1], [], safe=True)
    assert f"Camera: {prompts.CAMERA_TEXT['HOLD_CLOSE']}" in close  # 가까운 장면은 그대로


def test_review_judges_space_objects_pictures_and_small_flaws() -> None:
    system = prompts.VIDEO_REVIEW_SYSTEM
    assert "1초 안팎 잠깐 보이는 작은 흠" in system and "WARN" in system
    continuity = system.split("CONTINUITY:")[1].split("MORPH:")[0]
    for text in (
        "카메라가 다른 인물을 따라가 움직여서 화면 밖으로 빠지는 것",
        "기준 장면부터 가까운 장면이라 몸 일부가 화면 밖인 것은 결함이 아니다",
        "담·울타리·화단",
        "하나뿐인 물건(쪽지·상자 등)이 둘로 늘어나지",
    ):
        assert text in continuity
    hint = system.split("ANSWER_HINT:")[1].split("TEXT:")[0]
    assert "쪽지·지도·사진 속 그림으로 그려진 것도 보이는 것" in hint
    assert "점선·X 표시 같은 그림 기호는 글자가 아니다" in system


def test_failed_cut_tries_safe_version_before_still_cut() -> None:
    """다시 만들기까지 실패한 컷은 안전한 버전으로 한 번 더, 통과하면 정지 그림 대신 그 영상과
    경고(사용자 결정 2026-11-18)."""
    from app.theme_draft.nodes.video import SAFE_NOTE, STILL_NOTE

    seen: dict[str, int] = {}

    def verdicts(user: dict) -> dict[str, str]:
        if user["scene"] != OUTRO_CUTS[3]["scene"]:
            return {}
        seen["n"] = seen.get("n", 0) + 1
        return {"CONTINUITY": "FAIL"} if seen["n"] <= 2 else {}  # 처음·다시 만들기 실패, 안전 통과

    video = FakeVideoClient()
    response = run(
        gen_llm(),
        review_llm(video=verdicts),
        image=FakeImageClient(),
        video=video,
        storage=MemoryThemeStorage(),
    )
    assert response.failure is None and set(response.videos) == {"INTRO", "OUTRO"}
    assert len(video.calls) == 8 + 1 + 1
    reasons = [w.reason for w in response.warnings]
    assert any(r.startswith(SAFE_NOTE) for r in reasons)
    assert not any(STILL_NOTE in r for r in reasons)


def test_characters_sheet_failure_falls_back_to_intro1_as_person() -> None:
    """인물만 그린 그림을 끝내 못 그리면 예전처럼 시작 1컷을 먼저 그려 인물 기준으로."""
    from app.llm.base import LlmUnavailable

    class NoSheet(FakeImageClient):
        async def edit(self, prompt: str, refs: Any, **kw: Any) -> bytes:
            if prompt.startswith("Draw only these people"):
                self.calls.append((prompt, len(refs)))
                raise LlmUnavailable("LLM_REFUSED", retryable=False)
            return await super().edit(prompt, refs, **kw)

    image, storage = NoSheet(), MemoryThemeStorage()
    response = run(gen_llm(), review_llm(), image=image, storage=storage)
    assert response.failure is None and response.regen is not None
    assert "CHARS" not in response.regen["assets"]
    assert response.regen["assets"]["PERSON"] == response.regen["assets"]["INTRO1"]
