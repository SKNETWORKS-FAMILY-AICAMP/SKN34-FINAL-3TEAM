"""6컷 설계 걸어 보기(#779 설계 E 4단계, 2026-11-19).

줄거리 종류 11개 × 갈래 × 시작·종료 12컷의 실제 그림·영상 지시와 금지 목록을 코드에서 만들어, 설계표
(ai.md 26절 "6컷 설계" A·B·C)와 어긋나는 곳이 없는지 본다. 콘티를 돌릴 때마다 새 빈틈이 나온 것은 한
씨앗(떡집)으로만 확인했기 때문이라, 모든 종류·갈래·컷을 한 번에 본다(한 예시로 일반화하지 않음).
"""

from typing import Any

import pytest

from app.theme_draft import cuts, families, prompts
from tests.theme_draft.fixtures import valid_theme
from tests.theme_draft.test_families import animal_theme
from tests.theme_draft.test_families_in_hand import gift_theme
from tests.theme_draft.test_families_sound import sound_theme
from tests.theme_draft.test_families_when_how import vehicle_theme, when_theme

SCENES = ("INTRO", "OUTRO")
KEY = {"INTRO": "introCuts", "OUTRO": "outroCuts"}


def theme_of(code: str) -> dict[str, Any]:
    """종류마다 검사를 통과하는 시험용 줄거리(없는 종류는 기본 줄거리에 종류만 바꿈)."""
    builders = {
        "PRANK": lambda: animal_theme("PRANK"),
        "FOOTPRINT": lambda: animal_theme("FOOTPRINT"),
        "GIFT": gift_theme,
        "SOUND": sound_theme,
        "WHEN": when_theme,
        "VEHICLE": vehicle_theme,
    }
    return builders[code]() if code in builders else {**valid_theme(), "storyType": code}


CASES = [
    (code, branch) for code, t in families.STORY_TYPES.items() for branch in [None, *t.branch_cuts]
]
IDS = [f"{c}-{b or '공통'}" for c, b in CASES]


def all_cuts(theme: dict[str, Any]):
    for scene in SCENES:
        for i, cut in enumerate(theme[KEY[scene]], 1):
            yield scene, i, cut, cuts.spec(scene, i, 6)


@pytest.mark.parametrize(("code", "branch"), CASES, ids=IDS)
def test_every_cut_follows_design_tables(code: str, branch: str | None) -> None:
    theme = theme_of(code) | ({"branch": branch} if branch else {})
    negative = prompts.video_negative(theme)
    for scene, i, cut, spec in all_cuts(theme):
        where = f"{code}/{branch} {scene}{i}"
        image = prompts.cut_image_prompt(theme, scene, i, cut, [])
        video = prompts.video_prompt(theme, scene, i, cut, [])
        beat = prompts.cut_beat(theme, scene, i)
        # C표: 뭉치 컷 공통 규칙은 대상 줄에 얹지 않고 뭉치 컷 전부에
        if spec.has_mungchi:
            for line in (prompts.MUNGCHI_SEPARATE, prompts.MUNGCHI_HOLDS_NOTHING):
                assert line in image, where
            assert prompts.MUNGCHI_SEPARATE in video, where
        # C표: 사람 컷 공통 규칙(만지기 예외·한 줄 서기·손)과 컷 표의 표정·4초 움직임
        if spec.has_people:
            assert prompts.NO_TOUCH in image and prompts.NOT_IN_A_ROW in image, where
            for line in (prompts.HAND_RULE, prompts.NO_ROW_VIDEO, prompts.NO_TOUCH, spec.act):
                assert line and line in video, where
            assert prompts.LEGACY_PEOPLE_MOTION not in video, where
            if scene == "OUTRO" and i in (3, 5):  # 공개·마무리 표정은 종류 문구(B표)
                assert "얼굴" in beat and beat in image, f"{where} 공개·마무리 표정 없음: {beat}"
            else:
                assert spec.look and spec.look in image, f"{where} 컷 표 표정이 그림에 없음"
        # A·B표: 공중 손짓(흔들기·손뼉)은 어느 컷의 할 일·영상 지시에도 없음(금지 목록에만)
        for word in ("손을 흔", "손뼉을 치", "손뼉 치"):
            assert word not in beat, f"{where} 할 일에 공중 손짓: {beat}"
        assert "waving" not in video.replace("No waving", "") and "clap" not in video.replace(
            "no clapping", ""
        ), where
        # 장소 칸: 사건 장소·정답 장소 컷은 장소 모습 줄, 잇는 컷은 같은 장소의 앞 컷
        if spec.place in ("INCIDENT", "ANSWER"):
            assert "Place (Korean):" in image, where
        if spec.follows:
            assert cuts.spec(scene, spec.follows, 6).place == spec.place, where
        # 동물이 떠나는 곳은 숲이 아니라 사는 쪽(숲이 없는 씨앗 장소가 있음)
        assert "숲으로 난 출구" not in beat and "숲길로" not in beat, where
    # 금지 목록: 공중 손짓·한 줄 서기는 모든 종류, 야생 동물 만지기는 동물 종류만
    assert prompts.VIDEO_NEGATIVE_EXTRA in negative
    wild = code in ("PRANK", "FOOTPRINT") or (code == "SOUND" and theme["answer"] == "너구리")
    assert (prompts.TOUCH_NEGATIVE in negative) == wild, code


def test_ending_is_the_same_thanks_scene_for_every_type_and_branch() -> None:
    """A표 종료 6: 모든 종류·갈래가 같은 '뭉치에게 고마워함', 동물 종류는 동물이 이미 떠남."""
    ending = cuts.spec("OUTRO", 6, 6).beat
    for code, branch in CASES:
        theme = theme_of(code) | ({"branch": branch} if branch else {})
        assert prompts.cut_beat(theme, "OUTRO", 6) == ending, (code, branch)
    for code in ("PRANK", "FOOTPRINT"):
        assert not prompts.cut_shows_target({"storyType": code}, "OUTRO", 6)
        assert prompts.cut_shows_target({"storyType": code}, "OUTRO", 5)


def test_branches_change_only_ending_scenes() -> None:
    """갈래는 종료 영상 마무리(와 시작 2컷 사건 모습)만 바꾸고, 갈래 없는 역할 수·모양은 그대로."""
    for code, t in families.STORY_TYPES.items():
        for branch, over in t.branch_cuts.items():
            assert set(over) <= {("INTRO", 2), ("OUTRO", 3), ("OUTRO", 4)}, (code, branch)
            roles = families.branch_roles(t, "OUTRO", branch)
            assert len(roles) == 4 and roles[0] == t.outro_cuts[0], (code, branch)
    assert families.branch_roles(families.LOST, "OUTRO", "모르는 값") == families.LOST.outro_cuts
    # 큰 동물은 안아 올리지 않음, 작은 생물은 안지 않음(B표)
    assert "안아 올리지 않음" in families.LOST.branch_cuts["큰 동물"][("OUTRO", 3)]
    assert "안" not in families.LOST.branch_cuts["작은 생물"][("OUTRO", 4)].replace("안도", "")


def test_plan_and_review_texts_have_no_old_ending_or_air_gestures() -> None:
    """줄거리 지시·종류 규칙·검토 지시에도 바꾼 설계의 옛 말이 남지 않음(걸어 보기가 그림·영상
    지시만 보다가 줄거리 예시 '손뼉을 치며'와 검토 '손을 흔들거나'를 놓쳤음, 2026-11-19)."""
    import re

    old = re.compile(
        r"손을 흔들|손뼉을 치|손뼉 치|숲으로 난|숲길로|마지막에는 .*배웅|반려동물을 찾은 주인"
        r"|clap for"
    )
    texts = {
        "PLAN_SYSTEM": prompts.PLAN_SYSTEM,
        "IMAGE_REVIEW": prompts.IMAGE_REVIEW_SYSTEM,
        "VIDEO_REVIEW": prompts.VIDEO_REVIEW_SYSTEM,
    }
    for code, t in families.STORY_TYPES.items():
        texts[f"outro_rule {code}"] = t.outro_rule
        for branch in [None, *t.branch_cuts]:
            texts[f"type_rules {code}/{branch}"] = families.type_rules(t, branch)
    assert [(k, m.group(0)) for k, v in texts.items() for m in old.finditer(v)] == []


def test_role_texts_pass_existing_checks_and_examples_carry_no_content() -> None:
    """대표 5종 콘티(2026-11-19)에서 걸어 보기가 못 잡은 것: 콘티 문구가 기존 검사를 부름('다가가'
    → 다가오기 금지), 엔딩에서 든 것을 '예린은 … 안고'가 뭉치 손 동작으로 오탐, 자막 예시의 이름·
    정답('아린'·'너구리')을 글 모델이 그대로 씀, 뭉치에게 그릴 수 없는 시선(늘 정면)을 시킴."""
    from app.theme_draft import checks

    beats = [s.beat for specs in cuts.layout(6).values() for s in specs]
    roles = [
        role
        for t in families.STORY_TYPES.values()
        for b in [None, *t.branch_cuts]
        for scene in SCENES
        for role in families.branch_roles(t, scene, b)
    ]
    # 다가오기 금지 검사(APPROACH_WORDS)의 줄기를 콘티 문구가 부르지 않음
    near = (*checks.APPROACH_WORDS, "다가가", "다가와", "다가간")  # '놀랐다가'는 아님
    for text in beats + roles:
        assert not any(w in text for w in near), text
    # 엔딩에서 인물이 든 것을 안은 채 뭉치 쪽으로 돌아도 뭉치 손 동작이 아님
    for line in (
        "예린은 아기 염소를 안고 뭉치 쪽으로 몸을 돌린다",
        "사장님은 바구니를 안고 웃는다",
    ):
        assert not [
            p for p in checks.cut_action_problems(line, True, False, ["예린"]) if "손·팔다리" in p
        ], line
    assert checks.cut_action_problems("뭉치는 작은 상자를 안고 웃는다", True, False, ["예린"])
    # 자막 예시에 인물 이름·후보·장소를 박지 않음
    words = [*prompts.NAME_POOL, *families.ANIMALS.rows, *families.GIFTS.rows, "떡"]
    speakers = [s.speaker for specs in cuts.layout(6).values() for s in specs]
    for text in [*speakers, prompts.CAPTION_RULE]:
        assert not [w for w in words if w in text], text
    # 뭉치는 늘 정면: 뭉치 컷·함께 컷 할 일에 뭉치가 다른 곳을 보라는 말이 없음
    for s in (x for specs in cuts.layout(6).values() for x in specs if x.has_mungchi):
        assert "올려다" not in s.beat and "뭉치도" not in s.beat, s.beat
    assert "정면" in cuts.spec("INTRO", 6, 6).beat and "정면" in cuts.spec("OUTRO", 1, 6).beat


def test_road_and_direction_frames_are_in_image_prompts() -> None:
    """가는 길은 실내면 복도(과학관에 마을 길을 그려 실패), 엔딩·배웅은 방향을 못박음(인물들이
    카메라 쪽을 보고 나란히 섬, 대표 5종 콘티 3/3)."""
    theme = valid_theme()
    for scene, i in (("INTRO", 4), ("OUTRO", 2)):
        image = prompts.cut_image_prompt(theme, scene, i, theme[KEY[scene]][i - 1], [])
        assert "hallway or corridor if the place is indoors" in image, (scene, i)
    ending = prompts.cut_image_prompt(theme, "OUTRO", 6, theme["outroCuts"][5], [])
    assert cuts.spec("OUTRO", 6, 6).frame in ending and "turned toward" in ending
    for code in ("PRANK", "FOOTPRINT"):
        animal = theme_of(code)
        farewell = prompts.cut_image_prompt(animal, "OUTRO", 5, animal["outroCuts"][4], [])
        assert families.ANIMAL_FAREWELL_FRAME in farewell, code
    lost5 = prompts.cut_image_prompt(theme, "OUTRO", 5, theme["outroCuts"][4], [])
    assert families.ANIMAL_FAREWELL_FRAME not in lost5
