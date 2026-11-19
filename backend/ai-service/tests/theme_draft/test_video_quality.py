"""시작·종료 영상 품질(#779, 사용자 결정 2026-11-18·19).

실측(2026-11-18, Veo fast): 뭉치가 뛰거나 손을 쓰거나 제자리에서 통통 튀면 팔·흰 다리가 생기고,
뭉치가 거의 가만히 있고 사람·배경·카메라가 움직이면 모양이 유지됨. 출동 컷은 첫 그림부터 정면을 본
채 달리는 자세로 그리고 옆으로 달리게 하면 갈색 발이 유지되고 배경이 흘러 출동처럼 보임. 검토는
글로만 기준을 주면 판정이 흔들려 판정 예시 그림 2장(허용·결함)을 붙임.

2026-11-19 만화 예고편 컷 문법(6컷 × 4초): 사람이 손으로 하는 동작 곁에 뭉치가 있으면 사람 팔이
뭉치에게 옮겨 붙어(3테마 실행 실패 5컷) 사람 컷과 뭉치 컷을 나누고, 자막은 중요한 순간 컷에만 그
컷에 보이는 인물의 '이름: 대사'로, 옷은 소매 없는 조끼로.
"""

from typing import Any

from app.llm.media import FakeImageClient, FakeVideoClient
from app.theme_draft import checks, cuts, prompts
from app.theme_draft.nodes.video import REVIEW_EXAMPLES, review_examples
from app.theme_draft.storage import MemoryThemeStorage
from tests.theme_draft.fixtures import INTRO_CUTS, OUTRO_CUTS, valid_theme
from tests.theme_draft.test_media_graph import gen_llm, review_llm, run


def test_mungchi_bouncing_is_a_cut_action_but_running_is_allowed_in_go_cut() -> None:
    """통통 튀기도 뭉치 동작에서 뺌(흰 다리), 뭉치 혼자 달리는 컷만 달리기 허용. 화면 쪽으로
    달려오는 말은 달리는 컷에서도 막음."""
    assert checks.cut_action_problems("뭉치가 제자리에서 통통 튄다")
    assert checks.cut_action_problems("뭉치가 기뻐서 깡충 뛴다")
    assert checks.cut_action_problems("뭉치가 옆으로 달려간다")  # 달리는 컷이 아니면 걸림
    assert not checks.cut_action_problems("뭉치가 옆으로 힘차게 달려간다", may_run=True)
    assert checks.cut_action_problems("뭉치가 통통 튀어 간다", may_run=True)  # 튀기는 출동도 안 됨
    assert checks.cut_action_problems("뭉치가 화면 쪽으로 달려온다", may_run=True)
    assert not checks.cut_action_problems("지호가 손뼉을 치고 뭉치는 몸을 살짝 흔든다")


def test_check_cuts_allows_running_only_in_run_cuts() -> None:
    """6컷 틀: 뭉치 혼자 달리는 컷(시작 4·종료 2)만 달리기 허용."""
    theme = valid_theme()
    assert "달려간다" in theme["introCuts"][3]["action"]
    assert "달려간다" in theme["outroCuts"][1]["action"]
    assert not [b for b in checks.check_cuts(theme) if b.startswith("CUT_ACTION")]
    theme["outroCuts"][3]["action"] = "뭉치가 옆으로 힘차게 달려간다"
    assert [b for b in checks.check_cuts(theme) if b.startswith("CUT_ACTION outroCuts4.action")]


def test_plan_and_fix_rules_keep_mungchi_still_except_run_cuts() -> None:
    assert "통통 튀기는 사람만" in prompts.PLAN_SYSTEM
    go_rule = "뭉치 혼자 달리는 컷(시작 4·종료 2)에서는 뭉치가 짧은 갈색 발로 옆으로"
    assert go_rule in prompts.PLAN_SYSTEM
    go_role = prompts.cut_roles(valid_theme(), "introCuts")[2]
    assert "짧은 갈색 발로 옆으로 힘차게 달려가고" in go_role
    run_fix = prompts.fix_rules(valid_theme(), "outroCuts2.action")
    assert any("이 컷에서 짧은 갈색 발로 옆으로 힘차게 달려간다" in r for r in run_fix)


def test_run_cut_images_are_drawn_running_and_facing_the_viewer() -> None:
    theme = valid_theme()
    go = prompts.cut_image_prompt(theme, "INTRO", 4, INTRO_CUTS[3], [])
    to_answer = prompts.cut_image_prompt(theme, "OUTRO", 2, OUTRO_CUTS[1], [])
    close = prompts.cut_image_prompt(theme, "INTRO", 5, INTRO_CUTS[4], [])
    assert prompts.RUN_POSE in go and "never a side profile" in go and prompts.RUN_POSE in to_answer
    assert prompts.RUN_POSE not in close


def test_video_prompt_story_beat_camera_and_mungchi_rules() -> None:
    """컷 틀의 할 일·카메라로 이야기 흐름, 달리는 컷만 달리기, 나머지는 뭉치 거의 정지, 배경
    움직임은 실내·실외를 나눔(모든 컷에 구름을 넣자 실내 벽에 구름이 생겼음)."""
    theme = valid_theme()
    go = prompts.video_prompt(theme, "INTRO", 4, INTRO_CUTS[3], [])
    assert prompts.MUNGCHI_RUN in go and prompts.MUNGCHI_STILL not in go
    assert f"Camera: {prompts.CAMERA_TEXT['TRACK_SIDE']}" in go
    assert f"Story beat of this clip (Korean): {prompts.cut_beat(theme, 'INTRO', 4)}" in go
    end = prompts.video_prompt(theme, "OUTRO", 6, OUTRO_CUTS[5], [])
    assert prompts.MUNGCHI_STILL in end and prompts.MUNGCHI_RUN not in end
    assert all(line in end for line in prompts.MUNGCHI_KEEP)
    assert "indoors, nothing floats inside the room (no clouds, no leaves)" in end
    assert "same face, hair and clothes as in the first frame" in end  # 토끼 머리핀 → 토끼 귀
    # 3테마 실행: 영상 지시에 안경·머리핀을 쓰자 없던 안경·콧수염이 생김(6건) → 금지 목록으로만
    assert "nothing added to anyone's face" in end and "glasses" not in end
    # 엔딩 컷 움직임(컷 표, #779 뭉치에게 고마워함, 손뼉 없음)
    assert "turn toward Mungchi and smile warmly" in end and prompts.HAND_RULE in end
    first = prompts.video_prompt(theme, "INTRO", 1, INTRO_CUTS[0], [])
    assert "Mungchi does not appear in this clip." in first
    assert f"Camera: {prompts.CAMERA_TEXT['PAN_SIDE']}" in first
    aha = prompts.video_prompt(theme, "OUTRO", 1, OUTRO_CUTS[0], [])
    assert "breaks into a big smile" in aha and "Only Mungchi is in this clip" in aha
    for word in ("white legs", "dog nose", "brown hands", "clouds indoors", "page curl"):
        assert word in prompts.VIDEO_NEGATIVE
    # 대사 자막은 입 모양 없이(립싱크 하지 않음)
    assert "talking, lip sync" in prompts.VIDEO_NEGATIVE
    assert all(w not in t for t in (first, end, aha) for w in ("talking", "lip sync", "speaks"))


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
        "옷 소매나 몸 옆 울퉁불퉁한 곳이 팔처럼",  # #779 2026-11-19
        "뭉치가 사람과 합쳐지는 것",
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
    assert len(seen) == 12  # 시작·종료 6컷씩(#779)
    assert all(len(images) >= 4 and images[-2:] == list(review_examples()) for images in seen)


# --- 만화 연출(#779 시제품 2026-11-18): 컷마다 다른 구도·이동·카메라, 정지 그림 대책 ---


def test_storyboard_rules_scene_is_first_frame_cartoon_staging() -> None:
    """scene은 첫 장면(예전 "컷 끝 장면"은 이동 컷이 거꾸로 움직임), 컷마다 다른 구도, 이동 컷은
    가는 쪽을 봄, 하나뿐인 물건은 한 명, 글자 대신 그림."""
    plan = prompts.PLAN_SYSTEM
    assert "scene은 그 컷이 시작하는 첫 장면" in plan and "그 컷 끝에 보이는 장면" not in plan
    for text in (
        "같은 장소 컷끼리는 다른 자리·다른 구도로",  # 장소는 컷 틀(#779 place)
        "그 인물이 가는 쪽을 보고(뒷모습·옆모습)",
        "드는 사람을 한 명만",
        "글자 없이 그림·기호",
        "camera는 PAN_SIDE로 둔다(카메라는 코드가 컷 틀대로 정함)",
    ):
        assert text in plan
    fix = prompts.fix_rules(valid_theme(), "introCuts1.scene")
    assert any("컷이 시작하는 첫 모습" in r for r in fix)


def test_entering_through_a_door_is_not_an_approach_word() -> None:
    """'들어간'은 뺌(카메라가 뒤에서 따라가며 문 안으로 들어가는 컷), 화면 밖으로 나가기는 막음."""
    assert not checks.cut_action_problems("지호가 문을 지나 놀이터 안으로 걸어 들어간다", False)
    assert checks.cut_action_problems("지호가 걸어서 화면 밖으로 나간다", False)


def test_legacy_four_cut_camera_menu_go_cut_and_defaults() -> None:
    """예전 4컷 초안: 정해 둔 카메라 중 콘티가 고름, 출동 컷은 늘 옆에서 따라감, 시작 1컷은 가까운
    장면이 아님, 없거나 목록 밖이면 역할별 기본값."""
    cut = {**INTRO_CUTS[0], "camera": "FOLLOW_BEHIND"}
    assert prompts.cut_camera("INTRO", 1, cut, 4) == "FOLLOW_BEHIND"
    assert (
        prompts.cut_camera("INTRO", 3, {**INTRO_CUTS[2], "camera": "PAN_SIDE"}, 4) == "TRACK_SIDE"
    )
    assert prompts.cut_camera("INTRO", 2, {"scene": "s"}, 4) == "HOLD_CLOSE"  # 역할별 기본값
    assert prompts.cut_camera("OUTRO", 1, {**OUTRO_CUTS[0], "camera": "PUSH_IN"}, 4) == "PAN_SIDE"
    assert (
        prompts.cut_camera("INTRO", 1, {**INTRO_CUTS[0], "camera": "HOLD_CLOSE"}, 4) == "PAN_SIDE"
    )
    legacy = {
        **valid_theme(),
        "introCuts": [{**c, "camera": "FOLLOW_BEHIND"} for c in INTRO_CUTS[:4]],
    }
    text = prompts.video_prompt(legacy, "INTRO", 1, legacy["introCuts"][0], [])
    assert f"Camera: {prompts.CAMERA_TEXT['FOLLOW_BEHIND']}" in text
    assert "others may leave the view only because the camera moves away" in text
    assert "nobody walks on or through walls" in text and "stays one object" in text
    assert "like a lively cartoon" in text
    for word in ("walking on walls", "passing through objects", "duplicated objects"):
        assert word in prompts.VIDEO_NEGATIVE


def test_six_cut_camera_is_fixed_by_layout() -> None:
    """6컷 틀은 카메라를 코드가 컷 역할마다 정함(콘티 camera 칸은 보지 않음, 2026-11-19).
    PUSH_SLOW는 얼굴 클로즈업에서만."""
    expect = {
        "INTRO": ["PAN_SIDE", "PUSH_SLOW", "HOLD_CLOSE", "TRACK_SIDE", "PUSH_SLOW", "PAN_SIDE"],
        "OUTRO": ["PUSH_SLOW", "TRACK_SIDE", "HOLD_CLOSE", "PUSH_SLOW", "PAN_SIDE", "PAN_SIDE"],
    }
    for scene, cams in expect.items():
        for i, cam in enumerate(cams, 1):
            assert prompts.cut_camera(scene, i, {"camera": "FOLLOW_BEHIND"}, 6) == cam
            # 카메라는 구도 틀이 정함(#779 설계 H). 천천히 다가가기는 클로즈업 틀에서만
            frame = cuts.spec(scene, i, 6).frame
            assert prompts.FRAMES[frame].camera == cam
            assert cam != "PUSH_SLOW" or frame in ("OBJECT_CLOSE", "MUNGCHI_CLOSE")


def test_cut_images_use_own_framing_shots_mystery_and_pictures_instead_of_letters() -> None:
    theme = valid_theme()
    close = prompts.cut_image_prompt(theme, "INTRO", 2, INTRO_CUTS[1], [])  # 사건 클로즈업
    wide = prompts.cut_image_prompt(theme, "INTRO", 1, INTRO_CUTS[0], [])
    alone = prompts.cut_image_prompt(theme, "OUTRO", 4, OUTRO_CUTS[3], [])
    react = prompts.cut_image_prompt(theme, "INTRO", 3, INTRO_CUTS[2], [])  # 리액션 틀
    # 장면 크기·조명은 구도 틀(#779 설계 H): 사건 클로즈업 틀은 물건을 크게, 리액션은 어깨 위
    assert prompts.FRAMES["OBJECT_CLOSE"].image in close
    assert prompts.CLOSE_SHOT in react and prompts.CLOSE_SHOT not in wide
    assert prompts.WIDE_SHOT in wide and prompts.MUNGCHI_CLOSE_SHOT in alone
    assert "empty space above its head" in prompts.MUNGCHI_CLOSE_SHOT  # 자막 자리
    assert prompts.MYSTERY_LIGHT in close and prompts.MYSTERY_LIGHT not in wide
    assert "never dark or scary" in prompts.MYSTERY_LIGHT
    for text in (close, wide):
        assert prompts.CUT_FRAMING in text
    # 쪽지·지도 지시는 장면에 그런 물건이 있을 때만(#779 경찰관 떡집 콘티)
    for cut, text in ((INTRO_CUTS[1], close), (INTRO_CUTS[0], wide)):
        has_note = bool(prompts.WRITTEN_WORDS.search(f"{cut['scene']} {cut['action']}"))
        assert (prompts.WRITTEN_THINGS in text) == has_note
    sheet = prompts.characters_prompt(theme)
    assert "Draw only these people" in sheet and "No Mungchi" in sheet
    assert all(c["name"] in sheet for c in theme["characters"])


def test_safe_video_prompt_reduces_motion_and_keeps_close_shot() -> None:
    theme = valid_theme()
    go = prompts.video_prompt(theme, "INTRO", 4, INTRO_CUTS[3], [], safe=True)
    assert prompts.MUNGCHI_GO_SAFE in go and prompts.MUNGCHI_RUN not in go
    # 첫 그림이 달리는 자세라 안전판도 달리는 자세 그대로, 카메라는 옆으로 따라감(3테마 실행)
    assert "keeps the running pose of the first frame" in prompts.MUNGCHI_GO_SAFE
    assert f"Camera: {prompts.CAMERA_TEXT['TRACK_SIDE']}" in go
    people = prompts.video_prompt(theme, "OUTRO", 5, OUTRO_CUTS[4], [], safe=True)
    assert "The people make small, gentle movements" in people
    assert f"Camera: {prompts.CAMERA_TEXT['PAN_SIDE']}" in people
    close = prompts.video_prompt(theme, "OUTRO", 1, OUTRO_CUTS[0], [], safe=True)
    assert f"Camera: {prompts.CAMERA_TEXT['HOLD_CLOSE']}" in close  # 다가가지 않고 그대로
    assert "breaks into a big smile" not in close  # 안전판은 표정 변화 지시도 뺌


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
    assert len(video.calls) == 12 + 1 + 1
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


# --- 3테마 실행(2026-11-18) 뒤 고친 것: 고칠 점 1~8·후보 여러 개(사용자 결정 2026-11-18) ---


def test_video_negative_blocks_added_faces_animal_features_and_flashes() -> None:
    for word in (
        "added glasses",
        "added mustache",
        "animal tail",
        "Mungchi turning into an animal",
        "Mungchi merging with a person",  # 2026-11-19
        "sleeves on Mungchi",
    ):
        assert word in prompts.VIDEO_NEGATIVE
    for word in ("bright flash", "light burst", "lens flare"):
        assert word in prompts.VIDEO_NEGATIVE
    assert "never a flash or bright burst" in prompts.SCENE_MOTION
    assert "the light shifts softly" not in prompts.SCENE_MOTION  # 실내 빛 흔들림 → 번쩍임


def test_mungchi_stays_apart_from_animals_and_people_in_image_and_video() -> None:
    """뭉치가 동물 곁에 붙어 있으면 그 동물(너구리)로, 사람 곁이면 사람 팔이 옮겨 붙음."""
    theme = valid_theme()
    image = prompts.cut_image_prompt(theme, "OUTRO", 6, OUTRO_CUTS[5], [])
    video = prompts.video_prompt(theme, "OUTRO", 6, OUTRO_CUTS[5], [])
    for line in (prompts.APART_FROM_ANIMALS, prompts.MUNGCHI_SEPARATE):
        assert line in image and line in video
    no_mungchi = prompts.cut_image_prompt(theme, "INTRO", 1, INTRO_CUTS[0], [])
    assert prompts.APART_FROM_ANIMALS not in no_mungchi
    assert prompts.MUNGCHI_SEPARATE not in no_mungchi


def test_people_do_not_line_up() -> None:
    assert "카메라를 보고 한 줄로 서지 않고" in prompts.PLAN_SYSTEM
    assert "do not stand in a row facing the viewer" in prompts.CUT_FRAMING


def test_cut_uses_first_passing_candidate_without_regenerating() -> None:
    """Veo 한 번 호출로 후보 2개(설정으로 올렸을 때), 한 후보가 실패해도 다른 후보가 통과하면 다시
    만들지 않음."""
    seen: dict[str, int] = {}

    def verdicts(user: dict) -> dict[str, str]:
        if user["scene"] != OUTRO_CUTS[3]["scene"]:
            return {}
        seen["n"] = seen.get("n", 0) + 1
        return {"CONTINUITY": "FAIL"} if seen["n"] == 1 else {}  # 두 후보 중 하나만 실패

    video = FakeVideoClient()
    response = run(
        gen_llm(),
        review_llm(video=verdicts),
        image=FakeImageClient(),
        video=video,
        storage=MemoryThemeStorage(),
        settings={"theme_video_candidates": 2},
    )
    assert response.failure is None and set(response.videos) == {"INTRO", "OUTRO"}
    assert video.counts == [2] * 12 and len(video.calls) == 24  # 컷 12개 × 후보 2, 다시 없음
    assert seen["n"] == 2 and response.warnings == []


def test_all_candidates_failing_regenerates_with_their_reasons() -> None:
    from app.theme_draft.nodes.video import STILL_NOTE

    seen: dict[str, int] = {}

    def verdicts(user: dict) -> dict[str, str]:
        if user["scene"] != OUTRO_CUTS[3]["scene"]:
            return {}
        seen["n"] = seen.get("n", 0) + 1
        return {"MORPH": "FAIL"} if seen["n"] <= 2 else {}  # 첫 시도 후보 2개 모두 실패

    video = FakeVideoClient()
    response = run(
        gen_llm(),
        review_llm(video=verdicts),
        image=FakeImageClient(),
        video=video,
        storage=MemoryThemeStorage(),
        settings={"theme_video_candidates": 2},
    )
    assert response.failure is None and len(video.calls) == 24 + 2  # 그 컷만 후보 2개로 다시
    assert not any(STILL_NOTE in w.reason for w in response.warnings)
    regen = [c[0] for c in video.calls if "MORPH" in c[0]]
    assert len(regen) == 2  # 다시 만들기 지시에 실패 사유가 들어감


def test_candidates_default_is_one() -> None:
    """후보 기본 1(사용자 결정 2026-11-19: 관리자 검수가 있어 2개는 과함, 설정으로 올림)."""
    from app.config import Settings

    assert Settings.model_fields["theme_video_candidates"].default == 1


def test_mungchi_role_is_a_case_solver_and_caption_examples_have_no_fixed_role() -> None:
    """뭉치 역할은 사건을 풀거나 찾아 주는 해결사 직업(사용자 결정 2026-11-18). 자막 예시에 특정
    역할(해적 선장)을 쓰면 다른 테마 자막에도 끌려 들어감."""
    assert "해적" not in prompts.PLAN_SYSTEM
    assert "사건을 해결하거나 찾아 주는 해결사 직업" in prompts.PLAN_SYSTEM
    assert "씨앗의 역할을 그대로" in prompts.PLAN_SYSTEM


def test_still_clip_zooms_smoothly_with_perspective() -> None:
    """정지 그림 컷은 원근 필터로 확대(zoompan은 정수 픽셀 반올림으로 1px씩 떨림)."""
    import inspect

    from app.llm.media import still_clip

    source = inspect.getsource(still_clip)
    assert "perspective=" in source and "zoompan" not in source.split('"""')[2]


# --- 만화 예고편 컷 문법(6컷, 사용자 결정 2026-11-19) -------------------------------------


def test_layout_table_separates_people_and_mungchi_cuts() -> None:
    """사람 컷과 뭉치 컷을 나누고, 함께 나오는 컷은 시작 6·종료 6뿐. 자막은 시작 1·2·4·6, 종료
    1·3·6. 예전 4컷 틀은 그대로(시작 1·2 사람, 3 뭉치 달림, 4·종료 모두 함께)."""
    new = cuts.layout(6)
    who = {s: [c.who for c in specs] for s, specs in new.items()}
    assert who == {
        "INTRO": ["PEOPLE", "OBJECT", "PEOPLE", "RUN", "MUNGCHI", "GROUP"],
        "OUTRO": ["MUNGCHI", "RUN", "PEOPLE", "MUNGCHI", "PEOPLE", "GROUP"],
    }
    captions = {s: [i for i, c in enumerate(specs, 1) if c.caption] for s, specs in new.items()}
    assert captions == {"INTRO": [1, 2, 4, 6], "OUTRO": [1, 3, 6]}
    roles = {s: [c.role for c in specs] for s, specs in new.items()}
    assert roles == {"INTRO": [1, 2, 2, 3, 3, 4], "OUTRO": [1, 2, 3, 3, 4, 4]}
    legacy = cuts.layout(4)
    assert [c.who for c in legacy["INTRO"]] == ["PEOPLE", "PEOPLE", "RUN", "GROUP"]
    assert all(c.who == "GROUP" and c.caption and not c.frame for c in legacy["OUTRO"])
    assert cuts.seconds(6, [4, 4, 4, 4, 4, 4]) == [4.0] * 6
    assert cuts.seconds(4, [4, 4, 4, 4, 4, 4]) == [4.0, 6.0, 8.0, 6.0]  # 예전 초안
    assert "6컷(무음 영상, 컷마다 4초)" in prompts.PLAN_SYSTEM
    assert "가장 긴 3번째 컷" not in prompts.PLAN_SYSTEM
    assert "종료 4컷에는 모두 뭉치가 나온다" not in prompts.PLAN_SYSTEM


def test_off_captions_are_cleared_by_code() -> None:
    theme = valid_theme()
    for c in [*theme["introCuts"], *theme["outroCuts"]]:
        c["caption"] = c["caption"] or "지호: 남은 자막"
    checks.clear_off_captions(theme)
    assert [bool(c["caption"]) for c in theme["introCuts"]] == [
        True,
        True,
        False,
        True,
        False,
        True,
    ]
    assert [bool(c["caption"]) for c in theme["outroCuts"]] == [
        True,
        False,
        True,
        False,
        False,
        True,
    ]


def test_caption_speaker_must_be_visible_in_that_cut() -> None:
    """'이름: 대사' 꼴, 뭉치 혼자 컷은 뭉치, 사람 컷은 그 컷에 나오는 인물(사용자 결정 2026-11-19).
    걸리면 그 자막만 고쳐 씀(CUT_SPEAKER)."""
    theme = valid_theme()
    assert not [b for b in checks.check_cuts(theme) if "CUT_SPEAKER" in b]
    cases = [
        ("introCuts", 4, "구조대 뭉치, 출동!", "'이름: 대사' 꼴이 아님"),
        ("introCuts", 4, "지호: 출동!", "말하는 사람은 '뭉치'"),
        ("introCuts", 2, "뭉치: 어라?", "그 컷에 보이는 인물"),
        ("outroCuts", 3, "엄마: 짜잔!", "그 컷에 보이는 인물"),
    ]
    for key, i, text, why in cases:
        t = valid_theme()
        t[key][i - 1]["caption"] = text
        bad = [b for b in checks.check_cuts(t) if b.startswith("CUT_SPEAKER")]
        assert bad and bad[0].startswith(f"CUT_SPEAKER {key}{i}.caption") and why in bad[0], text
        assert list(checks.fix_targets(bad)) == [f"{key}{i}.caption"]  # 그 자막만 고쳐 씀
    narrator = valid_theme()
    narrator["introCuts"][0]["caption"] = "평화로운 마을 길…"  # 시작 1컷은 이름 없는 장면 소개
    assert not [b for b in checks.check_cuts(narrator) if "CUT_SPEAKER" in b]
    long = valid_theme()
    long["outroCuts"][5]["caption"] = "뭉치: " + "가" * 20
    assert [b for b in checks.check_cuts(long) if b.startswith("LENGTH outroCuts6.caption")]
    empty = valid_theme()
    empty["outroCuts"][2]["caption"] = ""
    assert "REQUIRED outroCuts3.caption" in checks.check_cuts(empty)
    assert list(checks.fix_targets(["REQUIRED outroCuts3.caption"])) == ["outroCuts3.caption"]


def test_caption_rules_dialogue_with_visible_speaker() -> None:
    rule = prompts.CAPTION_RULE
    for text in ("'이름: 대사'", "그 컷 화면에 보이는 한 명", "시작 1컷만 이름 없이", "20자 이내"):
        assert text in rule
    assert "'범인'이라는 말은 쓰지 않는다" in rule and "종료 1컷은 뭉치가 정답을 말한다" in rule
    assert rule in prompts.PLAN_SYSTEM
    fix = prompts.fix_rules(valid_theme(), "outroCuts1.caption")
    assert any("뭉치가 '알았다!' 뒤에 이번 정답을 말함" in r for r in fix)


def test_outfit_fits_tightly_and_squashes_the_lower_body() -> None:
    """셔츠·가운은 몸 옆이 소매로, 소매 없는 조끼는 조끼 가장자리가 옆 돌기를 잘라 크림색 팔처럼
    보였음(2026-11-19). 옷은 아래쪽을 꽉 끼게 감싸 매끈한 둥근 몸통으로(사용자 결정 A안)."""
    for text in (prompts.MUNGCHI_LOOK, prompts.OUTFIT_VEST):
        assert "fits Mungchi tightly" in text and "no bumps poking out at its sides" in text
        assert "no sleeves" in text and "sleeveless vest" not in text
    assert (
        "꽉 끼게 감싸는 조끼" in prompts.PLAN_SYSTEM
        and "소매 없는 조끼로만" not in prompts.PLAN_SYSTEM
    )
    assert "팔이 넷처럼 보이면 결함" in prompts.IMAGE_REVIEW_SYSTEM


def test_note_hint_only_when_the_cut_has_a_note_and_reaction_cut_is_surprised() -> None:
    """쪽지가 없는 리액션 컷에 점선·X 예시를 따라 보물 지도를 그리고 웃는 얼굴로 그렸음
    (경찰관 떡집 콘티 2026-11-19)."""
    theme = valid_theme()
    plain = {
        "scene": "떡집 안 두 사람의 얼굴",
        "action": "펄쩍 놀란다",
        "caption": "",
        "mungchiMood": "none",
    }
    note = {**plain, "scene": "아린이 쪽지를 펼쳐 든다"}
    six = {**theme, "introCuts": [plain] * 6, "outroCuts": [plain] * 6}
    reaction = prompts.cut_image_prompt(six, "INTRO", 3, plain, [])
    assert prompts.WRITTEN_THINGS not in reaction
    assert "big surprised face" in reaction and "not smiling" in reaction
    assert prompts.WRITTEN_THINGS in prompts.cut_image_prompt(six, "INTRO", 3, note, [])
    assert "big surprised face" not in prompts.cut_image_prompt(six, "INTRO", 1, plain, [])


def test_outro_first_caption_must_say_the_answer() -> None:
    """종료 1컷 자막은 뭉치가 정답을 말함(경찰관 떡집 콘티: "장난꾸러기 찾았다!"로 정답이 빠짐)."""
    theme = valid_theme()
    cut = {"scene": "뭉치가 단서 판 앞에 있다", "action": "뭉치가 웃는다", "mungchiMood": "smile"}
    six = {**theme, "introCuts": [dict(cut)] * 6, "outroCuts": [dict(cut) for _ in range(6)]}
    six["outroCuts"][0]["caption"] = "뭉치: 장난꾸러기 찾았다!"
    bad = checks.caption_problems(six, "OUTRO", 1)
    assert any(r.startswith("CUT_ANSWER outroCuts1.caption") for r in bad)
    assert any(p.match(bad[-1]) for p in checks.FIX_REASON)  # 그 자막 칸만 고쳐 씀
    six["outroCuts"][0]["caption"] = f"뭉치: 알았다! {theme['answer']}!"
    assert not any(r.startswith("CUT_ANSWER") for r in checks.caption_problems(six, "OUTRO", 1))


def test_outro_ending_thanks_mungchi_and_animal_farewell_in_cut5() -> None:
    """종료 흐름(#779 사용자 결정 2026-11-19): 동물 종류는 3컷 딱 걸림(현장 포착, 아무도 안 만짐),
    5컷 덮어 두기 + 배웅, 6컷(엔딩)은 모든 종류가 같은 '뭉치에게 고마워함'(종료 6컷이 반만 바뀌어
    공통 할 일·뭉치 동작과 배웅이 부딪혔던 4차 콘티)."""
    from app.theme_draft import families

    ending = cuts.layout(6)["OUTRO"][5]
    assert ending.own and "뭉치에게 고마워함" in ending.beat and "shyly" in ending.motion
    assert "clap" not in ending.motion + ending.act and "손뼉" not in ending.beat
    for code in ("PRANK", "FOOTPRINT"):
        t = families.STORY_TYPES[code]
        assert "딱 걸려" in t.outro_cuts[2] and "만지지 않음" in t.outro_cuts[2]
        assert "배웅" in t.outro_cuts[3] and "제가 사는 쪽" in t.outro_cuts[3]
        c = families.type_cuts(t, 6)
        assert c.target == {("OUTRO", 3), ("OUTRO", 5)}  # 6컷엔 동물이 이미 떠남
    theme = valid_theme()
    for code in ("LOST", "PRANK"):  # 엔딩 할 일은 종류와 상관없이 같음(종류 역할을 붙이지 않음)
        assert prompts.cut_beat({**theme, "storyType": code}, "OUTRO", 6) == ending.beat
    assert "종료 6 [함께(뭉치는 떨어져)·정답 장소]: 엔딩" in prompts.PLAN_SYSTEM
    # 엔딩 자막: 그 컷에 보이는 인물이 뭉치에게 고마워함(CUT_THANKS, 그 자막만 고쳐 씀)
    six = valid_theme()
    assert not checks.caption_problems(six, "OUTRO", 6)
    for bad_caption in ("지호: 사건 해결!", "뭉치: 고마워, 지호!", "지호: 고마워!"):
        six["outroCuts"][5]["caption"] = bad_caption
        bad = checks.caption_problems(six, "OUTRO", 6)
        assert any(r.startswith("CUT_THANKS outroCuts6.caption") for r in bad), bad_caption
        assert any(p.match(bad[-1]) for p in checks.FIX_REASON)
    # 그림은 그 컷 할 일·동작의 첫 순간(4차 콘티: 5컷에 덮을 떡이 없고 6컷에서 아무도 안 봄)
    img = prompts.cut_image_prompt(theme, "OUTRO", 6, theme["outroCuts"][5], [])
    assert f"This cut's story beat (Korean): {ending.beat}" in img
    assert theme["outroCuts"][5]["action"] in img and prompts.FIRST_MOMENT in img


def test_follow_cuts_point_to_earlier_people_cut() -> None:
    """앞 컷 잇기(#779 B안): 잇는 컷은 같은 영상의 앞쪽 사람 컷을 잇고, 뭉치 혼자 컷은 잇지 않는다.

    경찰관 떡집 콘티(2026-11-19)에서 종료 5컷에 덮은 떡이 6컷에서 벗겨지고 탁자·담이 바뀌었음."""
    six = cuts.layout(6)
    follows = {(s, i): spec.follows for s, specs in six.items() for i, spec in enumerate(specs, 1)}
    assert {k: v for k, v in follows.items() if v} == {
        ("INTRO", 2): 1,
        ("INTRO", 3): 1,
        ("INTRO", 6): 1,
        ("OUTRO", 5): 3,
        ("OUTRO", 6): 3,  # 두 단(3 → 5·6), 대표 5종 2차에서 3 → 5 → 6이 그림 시간을 늘림
    }
    for (scene, i), k in follows.items():
        if k:
            assert k < i and six[scene][k - 1].has_people and not six[scene][i - 1].mungchi_alone
    assert all(spec.follows == 0 for specs in cuts.layout(4).values() for spec in specs)
    # 장면 글도 앞 컷에서 바뀐 물건 상태를 다음 컷에 그대로 씀
    assert "앞 컷에서 바뀐 물건 상태(덮개를 씌운 접시" in prompts.PLAN_SYSTEM
    theme = valid_theme()
    plain = prompts.cut_image_prompt(theme, "OUTRO", 6, theme["outroCuts"][5], [])
    follow = prompts.cut_image_prompt(
        theme, "OUTRO", 6, theme["outroCuts"][5], [], theme["outroCuts"][4]["scene"]
    )
    assert "earlier cut" not in plain and prompts.CUT_FRAMING in plain
    assert "something covered stays covered" in follow and prompts.CUT_FRAMING not in follow


def test_cut_place_is_fixed_by_layout() -> None:
    """컷 장소(#779 사용자 결정 2026-11-19): 장소는 컷 틀이 정하고 모습은 테마에 한 번만.

    경찰관 떡집 콘티 3차에서 컷마다 글 모델이 장소를 정해 종료 3컷 숲 → 5컷 떡집 문가로 바뀌었음."""
    six = cuts.layout(6)
    places = {(s, i): spec.place for s, specs in six.items() for i, spec in enumerate(specs, 1)}
    assert [places["INTRO", i] for i in range(1, 7)] == [
        "INCIDENT",
        "INCIDENT",
        "INCIDENT",
        "ROAD",
        "INCIDENT",
        "INCIDENT",
    ]
    assert [places["OUTRO", i] for i in range(1, 7)] == [
        "INCIDENT",
        "ROAD",
        "ANSWER",
        "ANSWER",
        "ANSWER",
        "ANSWER",
    ]
    # 잇는 컷은 같은 장소의 앞 컷만(장소가 바뀌면 앞 컷 그림을 따라 그리지 않음)
    for specs in six.values():
        for spec in specs:
            if spec.follows:
                assert specs[spec.follows - 1].place == spec.place
    assert all(spec.place == "" for specs in cuts.layout(4).values() for spec in specs)
    # 줄거리 지시: 컷 틀 줄에 장소, 장소 모습 칸 설명, 다른 장소로 옮기지 않음
    plan = prompts.PLAN_SYSTEM
    assert "종료 3 [사람만·정답 장소]" in plan and "시작 4 [뭉치 혼자 달림·가는 길]" in plan
    assert "introPlace는 사건 장소" in plan and "다른 장소로 옮기지 않는다" in plan
    # 그림 지시: 장소 모습을 코드가 넣음(가는 길은 그 장소로 가는 길)
    theme = valid_theme()
    outro5 = prompts.cut_image_prompt(theme, "OUTRO", 5, theme["outroCuts"][4], [])
    assert f"Place (Korean): {theme['outroPlace']}." in outro5
    intro4 = prompts.cut_image_prompt(theme, "INTRO", 4, theme["introCuts"][3], [])
    assert f"if it is outdoors (Korean): {theme['introPlace']}." in intro4 and "hallway" in intro4
    outro1 = prompts.cut_image_prompt(theme, "OUTRO", 1, theme["outroCuts"][0], [])
    assert f"Place (Korean): {theme['introPlace']}." in outro1  # 단서판은 사건 장소
    old = {k: v for k, v in theme.items() if k not in ("introPlace", "outroPlace")}
    assert "Place" not in prompts.cut_image_prompt(old, "OUTRO", 5, theme["outroCuts"][4], [])
    # 6컷 테마는 장소 칸 필수(빈 칸은 그 칸만 써 넣음), 예전 4컷 테마는 아님
    bad = checks.check_theme({**theme, "introPlace": " ", "outroPlace": None}, 3)
    assert {"REQUIRED introPlace", "REQUIRED outroPlace"} <= set(bad)
    assert set(checks.fix_targets(["REQUIRED introPlace", "REQUIRED outroPlace"])) == {
        "introPlace",
        "outroPlace",
    }
    assert prompts.fix_rules(theme, "outroPlace")
