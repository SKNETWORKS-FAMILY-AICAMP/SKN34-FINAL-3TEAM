"""#782 설계 v10 C(2절 치명 결함 네 뿌리, 5절 '아이가 아는 것은 시작 이야기만이 아님'·'수사 날 미션
그림').

- 2.1 아이가 이미 아는 것: 소리 탐정 INTRO_HEARD, 출처 찾기 물건 INTRO_FOUND(시작 이야기·오늘 온
  까닭은 칸 고쳐 쓰기, 대화의 첫 등장인물 줄은 그 요일 대화 다시), 탈것 찾기는 지시문·검토만,
  사건 단서의 시작 이야기 모습(intro_seen_clue)은 함수만(check_theme에 넣지 않음)
- 2.2 수사 날 두 증언 비교는 설계 v11에서 v9로 되돌림(지문에 단서 결론 금지 CLUE_EARLY 그대로)
- 2.3 아직 일어나지 않은 일(EVENT_LATER, 종류 무관)
- 2.4 시간 탐정의 그 일을 한 사람(WHEN_DOER), 단서의 '시각·몇 시'(TIME_WORD)
"""

import copy
from typing import Any

from app.config import get_settings
from app.theme_draft import checks, families, prompts
from tests.theme_draft.fixtures import day_with, valid_theme
from tests.theme_draft.helpers import DAY_TYPES
from tests.theme_draft.test_families_in_hand import gift_theme
from tests.theme_draft.test_families_sound import sound_theme
from tests.theme_draft.test_families_when_how import when_theme
from tests.theme_draft.test_theme_structure import _draft, _request

GRADE = 3


def reasons(theme: dict[str, Any], code: str) -> list[str]:
    return [r for r in checks.check_theme(theme, GRADE) if r.startswith(code + " ")]


def dialogue_reasons(theme: dict[str, Any], day: str, lines: list[dict[str, str]]) -> list[str]:
    return checks.check_dialogue(
        theme,
        day,
        {"lines": lines},
        _draft(checks.DAY_TYPE[day]),
        GRADE,
        get_settings().followup_example_overlap_chars,
    )


def mission_reasons(theme: dict[str, Any], day: str, **draft: Any) -> list[str]:
    s = get_settings()
    return checks.check_mission(
        theme,
        _request(DAY_TYPES[day]),
        _draft(DAY_TYPES[day], **draft),
        GRADE,
        s.mission_draft_question_max_chars,
        s.followup_example_overlap_chars,
    )


# ---------------------------------------------------------------- 2.1 소리 탐정 INTRO_HEARD
def test_sound_intro_child_hearing_is_field_fixed() -> None:
    theme = {
        **sound_theme(),
        "intro": "지호는 잠결에 이상한 소리를 들었어요. 소리 박사 뭉치가 출동해요.",
    }
    bad = reasons(theme, "INTRO_HEARD")
    assert bad and "'들었'" in bad[0] and checks.fix_targets(bad) == {"intro": bad}
    for text in (
        "지호는 잠자리에 누웠는데 창밖에서 소리가 들려왔어요.",  # 소리가 주어, 아이 이름이 앞에
        "지호는 밤에 이상한 소리에 잠에서 깼어요.",
    ):
        assert reasons({**sound_theme(), "intro": text}, "INTRO_HEARD"), text
    # 전해 들은 꼴·남의 말·다른 사람이 들은 것·잠자리에 들었(잠)은 됨
    for text in (
        "지호는 할머니에게 밤에 이상한 소리가 났다는 이야기를 전해 들었어요.",
        "할머니가 지호에게 밤에 소리가 들렸다고 말했어요.",
        "이웃 할머니는 밤에 이상한 소리를 들었어요. 지호는 궁금했어요.",
        "지호는 일찍 잠자리에 들었어요. 이웃들은 밤에 이상한 소리가 난다고 했어요.",
    ):
        assert not reasons({**sound_theme(), "intro": text}, "INTRO_HEARD"), text
    # 다른 종류는 보지 않음
    assert not checks.child_known(valid_theme(), "지호는 잠결에 소리를 들었어요.", False)


def test_sound_day_step_and_dialogue_child_hearing() -> None:
    """5절: 오늘 온 까닭(칸 고쳐 쓰기)과 대화의 첫 등장인물 줄(그 요일 대화 다시)도."""
    heard = day_with(sound_theme(), "TUE", dayStep="어젯밤 그 소리를 듣고 마당 끝까지 와 봤어.")
    bad = reasons(heard, "INTRO_HEARD")
    assert bad and checks.fix_targets(bad) == {"TUE.dayStep": bad}
    for ok in ("할머니 말을 듣고 마당 끝까지 와 봤어.", "이웃이 소리를 들었대서 마당 끝으로 왔어."):
        assert not reasons(day_with(sound_theme(), "TUE", dayStep=ok), "INTRO_HEARD"), ok
    # 첫 줄로 못 쓰면 코드 문장(대화를 헛되이 다시 만들지 않음), 코드 문장은 검사를 통과
    theme = checks.finalize_texts(heard)
    first = checks.first_line_text(theme, "TUE")
    assert first == checks.day_step_text(theme, 1)
    assert all(
        not checks.child_known(theme, checks.day_step_text(theme, i), True) for i in range(5)
    )
    # 대화: 첫 등장인물 줄만, 전해 들은 말·다른 화자는 됨
    base = [
        {"speaker": "뭉치", "text": "여기서 무슨 일이 있었을까?"},
        {"speaker": "꽃집 할머니", "text": "내가 그 소리를 들었지."},
        {"speaker": "뭉치", "text": "같이 살펴보자!"},
    ]
    said = [{"speaker": "지호", "text": "어젯밤 나도 그 소리를 들었어."}, *base]
    bad = [r for r in dialogue_reasons(sound_theme(), "WED", said) if r.startswith("INTRO_HEARD")]
    assert (
        bad
        and bad[0].startswith("INTRO_HEARD WED 대화에서 지호의 말")
        and not checks.fix_targets(bad)
    )
    told = [{"speaker": "지호", "text": "할머니께 전해 들었어."}, *base]
    assert not [r for r in dialogue_reasons(sound_theme(), "WED", told) if "INTRO_HEARD" in r]


def test_sound_rules_in_three_places() -> None:
    rules = families.SOUND.rules
    assert "INTRO_HEARD" in rules and "잠결에 멀리서 희미하게" not in rules
    assert (
        "이웃·가족" in families.SOUND.intro_cuts[1]
        and "귀 기울임" not in families.SOUND.intro_cuts[1]
    )
    assert "소리를 직접 듣지 않고 이웃·가족에게 전해 들은 것이" in prompts.REVIEW_SYSTEM
    theme = sound_theme()
    assert "INTRO_HEARD" in " ".join(prompts.fix_rules(theme, "intro"))
    assert "INTRO_HEARD" in " ".join(prompts.fix_rules(theme, "TUE.dayStep"))


# ---------------------------------------------------------------- 2.1 출처 찾기 물건 INTRO_FOUND
def origin_theme(branch: str = "물건") -> dict[str, Any]:
    return {**valid_theme(), "storyType": "ORIGIN", "branch": branch, "target": "털장갑"}


def test_origin_object_child_picking_up_is_field_fixed() -> None:
    picked = {
        **origin_theme(),
        "intro": "지호는 운동장에서 털장갑을 주웠어요. 탐정 뭉치가 출동해요.",
    }
    bad = reasons(picked, "INTRO_FOUND")
    assert bad and checks.fix_targets(bad) == {"intro": bad}
    step = day_with(origin_theme(), "MON", dayStep="내가 주운 털장갑의 주인을 찾으러 왔어.")
    bad = reasons(step, "INTRO_FOUND")
    assert bad and checks.fix_targets(bad) == {"MON.dayStep": bad}
    # 다른 사람이 주움·주운 사람을 찾음은 됨, 동물 갈래는 보지 않음
    for text in (
        "관리실 아저씨가 운동장에서 주운 털장갑을 분실물 선반에 맡겨 두었어요.",
        "지호는 아저씨가 주운 털장갑 이야기를 들었어요.",
    ):
        assert not reasons({**origin_theme(), "intro": text}, "INTRO_FOUND"), text
    assert not checks.child_known(origin_theme(), "털장갑을 주운 사람을 만나러 왔어.", True)
    assert not checks.child_known(origin_theme("동물"), "지호는 강아지를 주웠어요.", False)
    lines = [
        {"speaker": "지호", "text": "이 털장갑은 내가 주워 맡겼어."},
        {"speaker": "뭉치", "text": "같이 살펴보자!"},
    ]
    assert any(
        r.startswith("INTRO_FOUND MON 대화") for r in dialogue_reasons(origin_theme(), "MON", lines)
    )


def test_origin_and_vehicle_rules() -> None:
    assert "INTRO_FOUND" in families.ORIGIN.rules and "관리실 직원·선생님" in families.ORIGIN.rules
    cut = families.ORIGIN.intro_cuts[1]
    assert "손대지 않고" in cut and "분실물 선반" in cut
    assert "아이가 그 물건을 직접 줍거나 손에 쥐고" in prompts.REVIEW_SYSTEM
    assert "INTRO_FOUND" in " ".join(prompts.fix_rules(origin_theme(), "intro"))
    # 탈것 찾기: 코드 검사 없이 지시문·콘티·글 검토
    assert "도착하는 모습과 들고 온 것을 보지 못했다" in families.VEHICLE.rules
    assert "들고 온 것도 보이지 않음" in families.VEHICLE.intro_cuts[1]
    assert "도착하는 모습과 들고 온 것을 보지 못했다" in prompts.REVIEW_SYSTEM


# ---------------------------------------------------------------- 2.1 사건 단서의 시작 이야기 모습
def test_intro_seen_clue_is_exported_but_not_wired() -> None:
    """6차 new4: 사건 단서가 시작 이야기에서 아이가 본 모습. 오탐을 재기 전이라 check_theme 밖."""
    seen = {
        **valid_theme(),
        "intro": "지호는 보리가 공을 물고 골목 쪽으로 달려가는 걸 봤어요. 그 뒤 보리가 사라졌어요.",
    }
    words = checks.intro_seen_clue(seen, "TUE")  # 화요일 사건 단서 '공을 물고 골목 쪽으로 달려갔대'
    assert len(words) >= checks.INTRO_SEEN_MIN and "골목" in words
    assert checks.intro_seen_clue(valid_theme(), "TUE") == []  # 겹침 없음
    assert checks.intro_seen_clue(seen, "MON") == []  # 특징 단서 날은 보지 않음
    assert not [r for r in checks.check_theme(seen, GRADE) if "INTRO_SEEN" in r]


# ------------------------------------------------------- 2.2 수사 날 지문(설계 v13: 증언 하나)
def test_investigate_material_carries_the_clue_as_one_testimony() -> None:
    """설계 v13: v11(지문에 단서 결론 금지)은 단서가 지문에 없는 사실을 말해 글 검토 CLUE_LOGIC으로
    줄거리를 다시 만듦 → 증언 하나에 그날 단서 내용을 넣음(v10의 두 말 견주기는 다시 넣지 않음)."""
    material = "할머니의 일지: 그 밤 소리는 쓰레기통 둘레에서 났다."
    theme = day_with(sound_theme(), "FRI", missionWay=checks.INVESTIGATE, missionMaterial=material)
    assert not any("FRI missionMaterial" in r for r in reasons(theme, "CLUE_EARLY"))
    rules = " ".join(prompts.fix_rules(theme, "FRI.missionMaterial"))
    assert "증언에 그날 단서 내용" in rules and "두 말을 견주는" not in rules
    assert "두 말을 견주" not in prompts.PLAN_SYSTEM + prompts.REVIEW_SYSTEM


# ---------------------------------------------------------------- 2.3 아직 일어나지 않은 일
def food_theme() -> dict[str, Any]:
    return {
        **gift_theme(),
        "storyType": "SECRET_INGREDIENT",
        "target": "할머니의 떡",
        "intro": "토요일 마을 떡 대회에 낼 할머니의 떡에 비밀 재료가 들어갔어요.",
    }


STAR_INTRO = (
    "저녁 별 보기 모임 직전, 지호는 아끼는 별자리 손전등이 없어진 걸 알아챘다. 숲 순찰대 뭉치는 "
    "캠핑장으로 출동해 지호와 함께 마지막으로 머문 곳을 찾기로 했다."
)


def test_future_events_are_read_from_the_intro() -> None:
    assert checks.future_events(food_theme()) == ["마을 떡 대회"]
    star = {**valid_theme(), "intro": STAR_INTRO}
    assert checks.future_events(star) == ["별 보기 모임"] and checks.event_keys(star) == ["모임"]
    many = {
        **valid_theme(),
        "intro": "다음 주 학교 발표회를 앞둔 보리가 사라졌어요. 주말 캠핑도 있어요.",
    }
    assert checks.future_events(many) == ["학교 발표회", "캠핑"]
    assert checks.future_events(valid_theme()) == []


def test_event_later_clue_and_material_are_field_fixed() -> None:
    """5차 hand5 '대회에서 눈으로 직접 본', 7차 hand5 '대회장 안으로 간 시각'."""
    for key, text in (
        ("clue", "내가 대회에서 눈으로 직접 본 할머니 떡은 잿빛이 아니었어!"),
        ("clue", "내 일지엔 그날 할머니의 떡이 대회장 안으로 간 시각이 적혀 있어!"),
        ("missionMaterial", "떡집 사장님의 말: 대회 날 떡 상자를 들고 무대 옆을 지나갔어요."),
    ):
        bad = reasons(day_with(food_theme(), "MON", **{key: text}), "EVENT_LATER")
        assert bad and checks.fix_targets(bad) == {f"MON.{key}": bad}, text
    # 앞일 뜻·날짜·곳 이름은 됨
    for text in (
        "대회에 낼 떡을 만들 때 내가 본 색은 잿빛이 아니었어!",
        "대회 준비로 바쁜 할머니 떡은 잿빛이 아니었어!",
        "대회 날짜를 적던 내가 본 떡은 잿빛이 아니었어!",
        "대회장 앞 골목에서 내가 본 떡은 잿빛이 아니었어!",
    ):
        assert not checks.event_later_hits(food_theme(), text), text
    # 앞으로의 행사가 없는 테마는 보지 않음(비밀 재료는 토요일 잔치·대회를 늘 앞일로)
    assert not checks.event_later_problems(day_with(gift_theme(), "MON", clue="대회에서 봤어."))
    assert checks.event_later_problems(
        day_with(
            {**food_theme(), "intro": "할머니가 떡을 만들었어요."}, "MON", clue="대회에서 봤어."
        )
    )


def test_event_later_in_mission_regenerates_that_mission() -> None:
    """7차 auto4b 금: 시작 '별 보기 모임 직전' ↔ 문제 '별빛 캠핑을 마친 네 마음'(행사 낱말이 달라도
    '마친·끝난'은 잡음). '모임의 가족 수'는 열렸다는 뜻이 아니라 잡지 않음."""
    star = {**valid_theme(), "intro": STAR_INTRO}
    bad = mission_reasons(
        star, "FRI", exampleAnswer="별빛 캠핑을 마친 네 마음을 돌아보면 처음엔 걱정했지만 즐거웠어."
    )
    assert [r for r in bad if r.startswith("EVENT_LATER")]
    assert checks.event_later_hits(star, "별 보기 모임에서 센 가족 수")
    assert not checks.event_later_hits(star, "별 보기 모임의 가족 수는 월요일 6팀이에요.")
    assert not checks.event_later_hits(star, "캠핑장 매점 앞에서 봤어.")
    assert not checks.event_later_hits(star, "모임 준비를 하던 안내원")
    assert "EVENT_LATER" in prompts.PLAN_SYSTEM and "EVENT_LATER" in prompts.REVIEW_SYSTEM
    assert "앞으로 열릴 행사(별 보기 모임)" in prompts.mission_extra(star, "FRI", GRADE, [])
    assert "EVENT_LATER" not in prompts.mission_extra(valid_theme(), "FRI", GRADE, [])


# ---------------------------------------------------------------- 2.4 시간 탐정
def test_when_doer_in_outro_regenerates_the_plan() -> None:
    theme = copy.deepcopy(when_theme())
    theme["characters"] = [*theme["characters"], {"name": "민아", "look": "빨간 모자를 쓴 이웃"}]
    met = {**theme, "outro": "뭉치와 지호는 민아를 찾아가 물을 준 때를 확인했어요."}
    bad = reasons(met, "WHEN_DOER")
    assert bad and checks.fix_targets(bad) == {}  # 칸 하나로 못 고침(줄거리 다시)
    asked = {**theme, "outro": "뭉치와 지호는 민아에게 물어 물 준 때를 알았어요."}
    assert reasons(asked, "WHEN_DOER")
    # 함께 간 등장인물·처음 나오는 사람은 됨, 다른 종류는 보지 않음
    together = {**theme, "outro": "지호와 민아는 화단지기 할아버지를 찾아가 확인했어요."}
    assert not reasons(together, "WHEN_DOER")
    assert not checks.when_doer_problems({**met, "storyType": "LOST"})
    assert "WHEN_DOER" in families.WHEN.rules and "처음 나온다" in families.WHEN.outro_rule
    assert "나와도 된다" not in families.WHEN.outro_rule
    assert "등장인물이 그 일을 한 사람이면 결함" in prompts.REVIEW_SYSTEM


def test_when_clue_saying_the_time_was_written_is_time_word() -> None:
    clue = "물을 줄 때 켜진 가로등이 보였고 그 시각도 봤어."
    bad = [
        r for r in reasons(day_with(when_theme(), "MON", clue=clue), "TIME_WORD") if "MON.clue" in r
    ]
    assert bad and checks.fix_targets(bad) == {"MON.clue": bad}
    assert reasons(day_with(when_theme(), "MON", clue="물을 줄 때 몇 시였는지 봤어."), "TIME_WORD")
    ok = "물을 줄 때 켜진 가로등이 몇 시간째 빛났어."
    assert not [
        r for r in reasons(day_with(when_theme(), "MON", clue=ok), "TIME_WORD") if "MON.clue" in r
    ]
    other = day_with(valid_theme(), "MON", clue="내가 본 보리 발자국은 젖어 있었고 그 시각도 봤어.")
    assert not reasons(other, "TIME_WORD")  # 시간 탐정만
    assert "'시각'·'몇 시'" in families.WHEN.rules
