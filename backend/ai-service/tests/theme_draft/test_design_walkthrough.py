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
