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
    assert "Camera: a side tracking shot that moves along with Mungchi" in go
    assert f"Story beat of this clip (Korean): {prompts.cut_roles(theme, 'introCuts')[2]}" in go
    happy = prompts.video_prompt(theme, "OUTRO", 4, OUTRO_CUTS[3], [])
    assert prompts.MUNGCHI_STILL in happy and prompts.MUNGCHI_RUN not in happy
    assert all(line in happy for line in prompts.MUNGCHI_KEEP)
    assert "indoors, nothing floats inside the room (no clouds, no leaves)" in happy
    assert "hair clips and clothes as in the first frame" in happy  # 토끼 머리핀 → 토끼 귀
    assert "Small, gentle movements in place" not in happy  # 예전 움직임 제한 문구는 없음
    first = prompts.video_prompt(theme, "INTRO", 1, INTRO_CUTS[0], [])
    assert "Mungchi does not appear in this clip." in first
    assert "Camera: a slow sideways pan that shows the everyday scene" in first
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
