"""6컷 설계 걸어 보기(#779 설계 E 4단계, 2026-11-19).

줄거리 종류 11개 × 갈래 × 시작·종료 12컷의 실제 그림·영상 지시와 금지 목록을 코드에서 만들어, 설계표
(ai.md 28절 "6컷 설계" A·B·C)와 어긋나는 곳이 없는지 본다. 콘티를 돌릴 때마다 새 빈틈이 나온 것은 한
씨앗(떡집)으로만 확인했기 때문이라, 모든 종류·갈래·컷을 한 번에 본다(한 예시로 일반화하지 않음).
"""

import json
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


def mungchi_image(theme: dict[str, Any], scene: str, i: int, cut: dict[str, Any]) -> str:
    """그 컷에서 뭉치를 그리는 그림 지시. 달리기 합성 컷(#779 ②안)은 컷 그림이 뭉치 없는 길
    배경이라 기본 자세 그림 지시가 뭉치 규칙·표정을 받는다."""
    if cuts.spec(scene, i, 6).run_comp:
        return prompts.run_base_prompt(theme, scene, i, [])
    return prompts.cut_image_prompt(theme, scene, i, cut, [])


@pytest.mark.parametrize(("code", "branch"), CASES, ids=IDS)
def test_every_cut_follows_design_tables(code: str, branch: str | None) -> None:
    theme = theme_of(code) | ({"branch": branch} if branch else {})
    negative = prompts.video_negative(theme)
    for scene, i, cut, spec in all_cuts(theme):
        where = f"{code}/{branch} {scene}{i}"
        image = mungchi_image(theme, scene, i, cut)
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
            for line in (prompts.NO_ROW_VIDEO, prompts.NO_TOUCH, spec.act):
                assert line and line in video, where
            # 공중 손짓 금지는 뭉치가 함께 나오는 사람 컷만(설계 v2 2026-11-23, 사람만 나오면
            # 손뼉 됨)
            assert (prompts.HAND_RULE in video) == spec.has_mungchi, where
            cut_negative = prompts.video_negative(theme, scene, i)
            assert ("clapping" in cut_negative) == spec.has_mungchi, where
            assert prompts.LEGACY_PEOPLE_MOTION not in video, where
            if scene == "OUTRO" and i in (3, 5):  # 공개·마무리 표정은 종류 문구(B표)
                assert "얼굴" in beat and beat in image, f"{where} 공개·마무리 표정 없음: {beat}"
            else:
                assert spec.look and spec.look in image, f"{where} 컷 표 표정이 그림에 없음"
        # A·B표: 뭉치가 나오는 컷은 공중 손짓(흔들기·손뼉)이 할 일·영상 지시에 없음(금지 목록에만)
        if spec.has_mungchi:
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
        r"손을 흔들|숲으로 난|숲길로|마지막에는 .*배웅|반려동물을 찾은 주인"
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
    # 손뼉은 사람만 나오는 컷(종료 5컷 마무리)에서만(설계 v2 2026-11-23)
    assert "사람만 나오는 컷은 손뼉 쳐도 됨" in prompts.PLAN_SYSTEM


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
    # 뭉치가 나오는 컷은 사람도 공중 손짓을 코드 검사가 막음(재검토 2026-11-20). 사람만 나오는
    # 컷은 손뼉 됨(설계 v2 2026-11-23). 종류 역할의 "손뼉 없이"는 걸지 않음
    for line in ("지호가 손뼉을 치며 폴짝 뛴다", "예린이 손을 흔들며 배웅한다", "모두 박수를 친다"):
        assert any("공중 손짓" in p for p in checks.cut_action_problems(line, True)), line
        assert not checks.cut_action_problems(line, False), line
    assert not checks.cut_action_problems("함께 기뻐함(손뼉 없이 폴짝 뛰거나 웃음)", False)
    bad = checks.check_cuts(
        {
            **valid_theme(),
            "outroCuts": [
                *valid_theme()["outroCuts"][:5],
                # 뭉치가 함께 나오는 종료 6컷(사람만 나오는 종료 5컷은 손뼉 됨, 설계 v2)
                {**valid_theme()["outroCuts"][5], "action": "지호가 손뼉을 치며 폴짝 뛴다"},
            ],
        }
    )
    assert any(r.startswith("CUT_ACTION outroCuts6.action 공중 손짓") for r in bad), bad
    assert checks.fix_targets([r for r in bad if "공중 손짓" in r])  # 그 칸만 고쳐 씀
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
    assert prompts.FRAMES[cuts.spec("OUTRO", 6, 6).frame].image in ending  # 구도 틀(설계 H)
    face = prompts.FACE_TEXT[prompts.FRAMES["FACING_MUNGCHI"].faces]
    assert face in ending and prompts.IMAGE_RULES not in ending
    for code in ("PRANK", "FOOTPRINT"):
        animal = theme_of(code)
        farewell = prompts.cut_image_prompt(animal, "OUTRO", 5, animal["outroCuts"][4], [])
        assert prompts.FRAMES["FAREWELL"].image in farewell, code
    lost5 = prompts.cut_image_prompt(theme, "OUTRO", 5, theme["outroCuts"][4], [])
    assert prompts.FRAMES["FAREWELL"].image not in lost5


@pytest.mark.parametrize(("code", "branch"), CASES, ids=IDS)
def test_common_rules_land_exactly_where_their_scope_says(code: str, branch: str | None) -> None:
    """공통 규칙 목록(#779 설계 H): 항목마다 적용 조건의 컷에만 그림·영상 지시가 들어가고, 금지
    낱말·검토 문장도 한 곳(목록)에서 나온다. 규칙을 고칠 때 항목 하나만 고치면 되는지 확인."""
    from app.theme_draft import rules

    theme = theme_of(code) | ({"branch": branch} if branch else {})
    negative = prompts.video_negative(theme)
    for scene, i, cut, _spec in all_cuts(theme):
        flags = prompts.cut_flags(theme, scene, i)
        image = mungchi_image(theme, scene, i, cut)
        video = prompts.video_prompt(theme, scene, i, cut, [])
        for r in rules.RULES:
            if r.image:
                assert (r.image in image) == (r.image_when in flags), (r.id, scene, i)
            if r.video:
                assert (r.video in video) == (r.video_when in flags), (r.id, scene, i)
    for r in rules.RULES:
        if r.negative:
            assert (r.negative in negative) == (
                r.negative_when in {"all", *(["wild"] if prompts.wild_answer(theme) else [])}
            ), r.id
        if r.review:
            assert r.review in prompts.IMAGE_REVIEW_SYSTEM, r.id


def test_frames_do_not_conflict_with_face_rules_and_variants_are_stable() -> None:
    """구도 틀(#779 설계 H): 옆모습·등을 시키는 틀은 얼굴 규칙도 그 예외를 따름(공통 '모든 얼굴이
    잘 보이게'가 엔딩 '옆모습으로 뭉치를 봄'과 부딪혀 인물이 카메라 쪽을 봤음). 변형은 같은 테마·
    컷이면 늘 같고, 테마가 다르면 달라질 수 있음."""
    for f in prompts.FRAMES.values():
        if "from behind" in f.image:
            assert f.faces == "back", f.id
        elif "in profile" in f.image or "turned toward" in f.image:
            assert f.faces in ("side", "back"), f.id
        assert f.core and f.variants and f.camera in prompts.CAMERA_TEXT, f.id
        assert f.camera != "PUSH_SLOW" or f.id in ("OBJECT_CLOSE", "MUNGCHI_CLOSE"), f.id
    for code, branch in CASES:
        theme = theme_of(code) | ({"branch": branch} if branch else {})
        for scene, i, cut, spec in all_cuts(theme):
            if spec.run_comp:  # 길 배경(사람·뭉치 없음)이라 얼굴 규칙 없음(#779 ②안)
                continue
            frame = prompts.cut_frame(theme, scene, i)
            image = prompts.cut_image_prompt(theme, scene, i, cut, [])
            assert prompts.FACE_TEXT[frame.faces] in image, (code, scene, i)
            if frame.faces != "front":
                assert prompts.IMAGE_RULES not in image, (code, scene, i)
            assert image == prompts.cut_image_prompt(theme, scene, i, cut, [])  # 같은 변형
    chosen = {
        prompts.frame_lines({**valid_theme(), "title": f"테마 {k}"}, "OUTRO", 6)[1]
        for k in range(12)
    }
    assert len(chosen) > 1  # 테마마다 엔딩 변형이 달라질 수 있음
    # 사건 컷 수수께끼 조명·클로즈업만 천천히 다가감(수수께끼 모험물 컷신 느낌)은 틀이 정함
    # (PERSON_CLOSE는 물건 없는 종류의 사건 클로즈업 대신, 1단계 실측 2026-11-23)
    mystery = {f.id for f in prompts.FRAMES.values() if f.mystery}
    assert mystery == {"OBJECT_CLOSE", "PERSON_CLOSE", "REACTION"}


@pytest.mark.parametrize(("code", "branch"), CASES, ids=IDS)
def test_no_cut_carries_lines_that_fight_each_other(code: str, branch: str | None) -> None:
    """부딪히는 문장이 한 컷 지시에 함께 들어가지 않음(재검토 2026-11-20). 위 시험들은 '있어야 할
    문장이 있는지'만 봐서, 서로 반대인 문장이 같이 들어간 곳을 놓쳤음(끝 표정을 첫 그림에, 공중
    손짓 낱말, 밤 이야기에 오후 햇빛, 서로 보는 컷에 '모두 동물을 봄')."""
    theme = theme_of(code) | ({"branch": branch} if branch else {})
    for scene, i, cut, spec in all_cuts(theme):
        where = f"{code}/{branch} {scene}{i}"
        frame = prompts.cut_frame(theme, scene, i)
        assert frame is not None, where
        # 뭉치 표정: 첫 그림은 컷 표의 첫 입 모양(콘티 mungchiMood = 컷 끝 표정은 쓰지 않음)
        for mood in ("smile", "surprised", "determined"):
            image = mungchi_image(theme, scene, i, {**cut, "mungchiMood": mood})
            video = prompts.video_prompt(theme, scene, i, {**cut, "mungchiMood": mood}, [])
            line = f"Mungchi's expression: {prompts.MOOD_MOUTH.get(spec.mouth)}, eyes"
            assert (line in image) == spec.has_mungchi, where
            assert bool(spec.mouth) == spec.has_mungchi, where
            # 영상: 표정 변화는 움직임 줄이 말함. 움직임이 없는 달리기 컷만 첫 표정 줄
            expects = spec.has_mungchi and not spec.motion
            assert ("Mungchi's expression:" in video) == expects, where
            # 공중 손짓 낱말은 그림 지시에 없음(영상은 금지 문장에만)
            assert "wave" not in image and "clap" not in image, where
            # 조명·배웅은 시간대·가는 곳을 박지 않음(밤 이야기, 물가에 사는 동물)
            assert "afternoon" not in image and "near the bushes" not in image, where
            # '모두 그 동물을 바라봄'은 공개 컷에만
            assert "everyone watches it" not in video or frame.id == "REVEAL", where
        # 종류가 틀을 바꾸면(종료 5컷 배웅, 시작 2컷 인물 클로즈업) 영상 카메라도 그 틀을 따름
        # (1단계 실측 2026-11-23: 사람 클로즈업은 다가가지 않음)
        if spec.has_people and not spec.run_comp and not spec.two_faces:
            assert f"Camera: {prompts.CAMERA_TEXT[frame.camera]}" in video, where
        # 첫 표정은 그 컷 움직임의 시작: 놀란 입에서 시작해 웃음으로 끝남. 일자 입(무표정)은 6컷
        # 컷 표에 쓰지 않음(설계 v2 2026-11-23)
    assert cuts.spec("OUTRO", 1, 6).mouth == "surprised"
    assert all(
        "determined" not in (s.mouth, s.end_mouth)
        for specs in cuts.layout(6).values()
        for s in specs
    )
    # 뭉치 클로즈업은 시작 5·종료 1뿐이고 두 끝 표정이 다름(설계 v2 2026-11-23)
    closeups = [
        (s, i) for s in ("INTRO", "OUTRO") for i in range(1, 7) if cuts.spec(s, i, 6).two_faces
    ]
    assert closeups == [("INTRO", 5), ("OUTRO", 1)]
    assert cuts.spec("INTRO", 5, 6).end_mouth != cuts.spec("OUTRO", 1, 6).end_mouth
    assert cuts.spec("INTRO", 5, 6).effect != cuts.spec("OUTRO", 1, 6).effect


@pytest.mark.parametrize(("code", "branch"), CASES, ids=IDS)
def test_story_wide_facts_reach_every_cut_not_only_people_cuts(
    code: str, branch: str | None
) -> None:
    """테마 전체에 걸친 사실(밤 이야기)은 사람 컷뿐 아니라 뭉치 혼자 컷에도 들어감(7종류 확인
    2026-11-20: 소리 탐정 뭉치 혼자 컷 5장이 낮). 뭉치 컷은 동작 글을 받아도 첫 그림은 시작
    표정만."""
    theme = theme_of(code) | ({"branch": branch} if branch else {})
    night = families.STORY_TYPES[code].night
    assert night == (code == "SOUND")
    for scene, i, cut, spec in all_cuts(theme):
        image = prompts.cut_image_prompt(theme, scene, i, cut, [])
        video = prompts.video_prompt(theme, scene, i, cut, [])
        assert (prompts.NIGHT_SCENE in image) == night, (code, scene, i)
        assert (prompts.NIGHT_SCENE in video) == night, (code, scene, i)
        start = prompts.MOUTH_AT_START.format(mouth=prompts.MOOD_MOUTH.get(spec.mouth))
        assert (start in image) == bool(spec.has_mungchi and spec.motion), (code, scene, i)
        # 그림 검토도 같은 컷에 시작 입 모양을 받음(검토가 동작 글의 뒤 표정으로 경고하지 않게)
        mouth = prompts.start_mouth_ko(theme, scene, i)
        assert bool(mouth) == (start in image), (code, scene, i)
        if mouth:
            review = json.loads(
                prompts.image_review_user(
                    theme,
                    cut["scene"],
                    ids=(),
                    has_mungchi=True,
                    shows_target=False,
                    mungchi_mouth=mouth,
                )
            )
            assert review["mungchiMouth"] == mouth
        if start in image:  # 동작 줄 뒤(그림 모델이 동작 글의 끝 표정을 그리지 않게)
            assert image.index(start) > image.index(prompts.FIRST_MOMENT_NEW), (code, scene, i)


def test_close_ups_are_two_face_cuts_with_a_real_change() -> None:
    """뭉치 혼자 클로즈업은 표정 그림 두 장(#779 사용자 결정 2026-11-20 A안): 시작·끝 입이 다르고,
    끝 그림 지시는 입만 바꾸며, 그 밖의 컷은 Veo 그대로."""
    theme = valid_theme()
    for scene, specs in cuts.layout(6).items():
        for i, s in enumerate(specs, 1):
            assert s.two_faces == (s.frame == "MUNGCHI_CLOSE"), (scene, i)
            if not s.two_faces:
                continue
            assert s.mouth and s.end_mouth and s.mouth != s.end_mouth, (scene, i)
            text = prompts.end_face_prompt(theme, scene, i, [])
            assert prompts.MOOD_MOUTH[s.end_mouth] in text and "Change only Mungchi's mouth" in text
            assert prompts.end_mouth_ko(theme, scene, i) == prompts.MOUTH_KO[s.end_mouth]
    assert cuts.end_key("OUTRO1") == "OUTRO1END" and cuts.scene_of("OUTRO1END") == "OUTRO"
    assert cuts.scene_of("MON") == "MON"


def test_review_cores_say_what_is_visible_and_plan_has_no_air_gesture_example() -> None:
    """검토 핵심은 '그림에 보이는 것'으로만(재검토 2026-11-20). '~를 봄'은 구도가 방향을 정하는
    배웅·엔딩 틀만, 한 줄 서기는 WARN이라 핵심에 없음. 방향은 몸·얼굴로 판정."""
    gaze = {f.id for f in prompts.FRAMES.values() if "봄" in f.core}
    assert gaze == {"FAREWELL", "FACING_MUNGCHI"}
    assert all(prompts.FRAMES[k].faces == "back" for k in gaze)
    assert not any("나란히" in f.core or "한 줄" in f.core for f in prompts.FRAMES.values())
    assert "몸과 얼굴이 향한 쪽으로 판정" in prompts.IMAGE_REVIEW_SYSTEM
    # 장면 맞음(SCENE_FIT, 떨어지면 영상이 빠지는 항목)은 시선을 FAIL로 보지 않음 — 방향은 FRAME만
    assert "인물이 바라보는 쪽" not in prompts.IMAGE_REVIEW_SYSTEM
    assert "인물이 향한 방향의 차이는 WARN" in prompts.IMAGE_REVIEW_SYSTEM
    # 공개·마무리 틀의 그림 지시도 종류 역할(나른 사람에게 인사·함께 들여다봄)과 부딪히지 않게
    assert "face each other" not in prompts.FRAMES["JOY"].image + " ".join(
        prompts.FRAMES["JOY"].variants
    )
    assert "the person the story beat names" in prompts.FRAMES["REVEAL"].image
    # 사건 클로즈업: 틀 글이 얼굴 규칙·컷 표 표정(눈·입)과 같게 인물 어깨 위
    assert "from the shoulders up" in prompts.FRAMES["OBJECT_CLOSE"].image
    assert "only a person's shoulder" not in prompts.FRAMES["OBJECT_CLOSE"].image
    # 줄거리 지시: 좋은 동작 예에 공중 손짓이 없고, 금지 문장에만 나옴
    plan = prompts.PLAN_SYSTEM
    assert plan.count("손 흔들기") == 1
    assert "뭉치가 나오는 컷에서는 사람도 손 흔들기·손뼉 같은 공중 손짓을 하지 않는다" in plan
    # 예전 4컷 초안의 그림 지시는 예전 글 그대로
    old = valid_theme()
    old = {**old, "introCuts": old["introCuts"][:4], "outroCuts": old["outroCuts"][:4]}
    assert prompts.FIRST_MOMENT in prompts.cut_image_prompt(
        old, "OUTRO", 4, old["outroCuts"][3], []
    )
    # 소리 탐정의 동물도 영상 검토에서 만지면 결함, 종류 문구는 리액션(놀람)과 같은 결
    assert "소리 탐정(SOUND)의 정답이 동물이면" in prompts.VIDEO_REVIEW_SYSTEM
    assert "놀람" in families.STORY_TYPES["VEHICLE"].intro_cuts[1]


def test_frame_core_is_judged_as_its_own_item_and_flow_fails_only_other_place() -> None:
    """구도 핵심은 그림 검토의 별도 항목(FRAME)으로 판정(SCENE_FIT 안에 묻혀 엔딩 3장이 통과했음),
    엔딩 틀은 멈춤 규칙대로 앞쪽 뒷모습 방식(틀 확인 2026-11-19)."""
    from app.theme_draft import checks, rules

    assert "FRAME(items에 있을 때만)" in prompts.IMAGE_REVIEW_SYSTEM
    assert checks.image_review_ids(checks.IMAGE_REVIEW_IDS, True, False, True)[-1] == "FRAME"
    assert prompts.FRAMES["FACING_MUNGCHI"].faces == "back"
    assert "from behind" in prompts.FRAMES["FACING_MUNGCHI"].image
    # 눈가림 소품(선글라스·고글)은 뭉치 눈을 가려도 됨(사용자 결정 2026-11-19, 표정은 입으로)
    assert "EYES_VISIBLE" not in rules.BY_ID
    assert "눈가림" not in prompts.IMAGE_REVIEW_SYSTEM
    # FLOW는 다른 장소처럼 보일 때만 FAIL, 가구 배치·모양은 WARN(카메라 각도로 달라 보임)
    assert "가구의 배치·모양·개수 차이" in prompts.IMAGE_REVIEW_SYSTEM
    # 시작 2컷 문구는 물건·자리 중심(사건 클로즈업 틀과 맞춤)
    assert "빈자리" in families.LOST.intro_cuts[1]
    # 탈것: 깜짝 찾아온 사람을 보고 놀람 + 탈것·들고 온 것이 안 보임(#782와 합침, 사용자 결정
    # 2026-11-23). 1컷엔 찾아올 사람이 없고, 2컷 글에 '짐 정리'가 없음(1단계 실측: 1컷으로 끌려감)
    vehicle1, vehicle2 = families.STORY_TYPES["VEHICLE"].intro_cuts[:2]
    assert "놀람" in vehicle2 and "들고 온 것도 보이지 않음" in vehicle2
    assert "반갑게" not in vehicle2 and "정리" not in vehicle2
    assert "찾아올 사람은 아직 보이지 않음" in vehicle1
    # 소리: 소리 난 자리는 그리지 않음('소리 난 곳' 후보 값을 가리키지 않게, 사용자 결정
    # 2026-11-21), 문장은 #782 v10(이웃·가족이 들려줌, 사용자 결정 2026-11-23)
    sound2 = families.STORY_TYPES["SOUND"].intro_cuts[1]
    assert "소리 난 자리가 보이지 않음" in sound2
    assert not any(w in sound2 for w in ("담장", "지붕", "나무 위", "구석"))
    # 사건 클로즈업 할 일에 여러 종류 예시를 늘어놓지 않음(1단계 실측 2026-11-23: 그림 지시에
    # 들어가 소리 탐정 클로즈업에 예시의 '파헤친 자리'가 그려짐). 그 종류 역할 2 내용이 정함
    beat = cuts.spec("INTRO", 2, 6).beat
    assert "역할 2" in beat
    assert not any(w in beat for w in ("빈 접시", "파헤친", "창가", "짐", "소리 이야기"))
    for code in (
        "SOUND",
        "VEHICLE",
        "GIFT",
        "WHEN",
    ):  # 그 종류 역할 2에 없는 물건이 그림 지시에 안 감
        assert not any(
            w in prompts.cut_beat(theme_of(code), "INTRO", 2) for w in ("파헤친", "빈 접시")
        )


def test_reveal_cut_has_no_arrival_role_and_plan_gives_only_used_roles() -> None:
    """종료 3컷(공개)에 역할 2(도착)를 합치지 않고, 줄거리 지시에는 6컷 사람 컷이 쓰는 역할만 줌
    (대표 5종 2차: 선물 공개 컷 글이 도착 역할 '닫힌 선물 상자 앞에 모여'로 시작해 공개 틀과
    부딪힘). 앞 컷 잇기는 두 단(그림 단계 시간)."""
    for code, branch in CASES:
        theme = theme_of(code) | ({"branch": branch} if branch else {})
        t = families.STORY_TYPES[code]
        beat = prompts.cut_beat(theme, "OUTRO", 3)
        arrival = families.branch_roles(t, "OUTRO", branch)[1]
        assert arrival not in beat, (code, branch)
        rules_text = families.type_rules(t, branch)
        assert arrival not in rules_text, (code, branch)  # 종료 역할 2는 주지 않음
        assert (
            families.branch_roles(t, "INTRO", branch)[2]
            not in rules_text.split("시작 콘티 역할")[1].split("\n")[0]
        )
    # 앞 컷 잇기 깊이: 잇는 컷의 앞 컷은 잇지 않는 컷(두 단)
    for specs in cuts.layout(6).values():
        for s in specs:
            if s.follows:
                assert specs[s.follows - 1].follows == 0, s.beat
