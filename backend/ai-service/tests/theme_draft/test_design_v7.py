"""#782 설계 v7(사용자 결정 2026-11-22 "응 그렇게 진행해 예시 답은 5문장으로"): 5차 측정 뒤.

- 오늘 온 까닭: 모델이 '오늘 여기 온 까닭'으로 쓰고 어제 일은 들은 것만(DAY_STEP_MADE), 대화
  첫 줄 화자의 자기 이름(SELF_NAME), 첫 줄로 못 쓰면 코드 문장(대화를 헛되이 다시 만들지 않음)
- 잃어버린 것·보물 쪽지 시작 이야기에 몇 시를 안 씀(INTRO_CLOCK, v6 EVENT_TIME 오탐을 바꿈)
- 지문 속 시키는 말(ACT_NAME missionMaterial), 맡겨지기 전에·내가 맡김(KEPT_PLACE), 비밀 재료의
  아직 안 열린 잔치(EVENT_LATER), 사건 단서의 아이 자신(STORY_SELF), 예시 답 초3·4 5문장
"""

import copy
from typing import Any

from app.theme_draft import checks, families, prompts
from tests.theme_draft.fixtures import day_with, generated_theme, valid_theme
from tests.theme_draft.test_families_in_hand import gift_theme
from tests.theme_draft.test_graph import fixes, gen_llm, review_llm, run
from tests.theme_draft.test_theme_structure import _draft, _request

GRADE = 3


def codes(theme: dict[str, Any]) -> list[str]:
    return sorted({r.split(" ")[0] for r in checks.check_theme(theme, GRADE)})


def reasons(theme: dict[str, Any], code: str) -> list[str]:
    return [r for r in checks.check_theme(theme, GRADE) if r.startswith(code)]


# ---------------------------------------------------------------- 오늘 온 까닭
def test_day_step_must_not_make_up_what_yesterday_helper_did() -> None:
    """5차: 화~금 92줄 중 들은 것만 말한 줄 10 — 나머지는 어제 사람의 부탁·소개·지시를 지어냄."""
    made = day_with(valid_theme(), "TUE", dayStep="공원 관리인이 부탁한 화분 일을 도우러 왔어.")
    bad = reasons(made, "DAY_STEP_MADE")
    assert bad and "부탁" in bad[0] and list(checks.fix_targets(bad)) == ["TUE.dayStep"]
    for text in (
        "공원 관리인이 소개한 빵집으로 왔어.",
        "공원 관리인이 빵집도 살펴보라 해서 왔어.",
        "공원 관리인이 건넨 메모를 들고 왔어.",
        "공원 관리인이 알려 준 빵집 아저씨를 만나러 왔어.",
    ):
        assert "DAY_STEP_MADE" in codes(day_with(valid_theme(), "TUE", dayStep=text)), text
    # 오늘 여기 온 까닭·어제 들은 것은 됨
    for text in (
        "보리가 빵집 앞을 지났을지 몰라 와 봤어.",
        "공원 관리인 말을 듣고 빵집 앞까지 왔어.",
        "어제 들은 걸 떠올리며 빵집 앞으로 와 봤어.",
    ):
        assert "DAY_STEP_MADE" not in codes(day_with(valid_theme(), "TUE", dayStep=text)), text
    # 장소·돕는 사람 호칭의 낱말은 보지 않음('기록 보관실'·'영상 기록가')
    named = copy.deepcopy(valid_theme())
    checks.theme_day(named, "TUE").update(place="기록 보관실", dayStep="기록 보관실로 와 봤어.")
    checks.theme_day(named, "MON")["helper"] = "영상 기록가"
    assert "DAY_STEP_MADE" not in codes(named)
    # 어제·오늘이 아닌 다른 날 돕는 사람(꽃집 할머니는 수요일)
    other = day_with(valid_theme(), "TUE", dayStep="꽃집 할머니 말을 듣고 빵집 앞까지 왔어.")
    assert any("다른 날 돕는 사람 '꽃집 할머니'" in r for r in reasons(other, "DAY_STEP_MADE"))
    # 월요일은 시작 이야기에서 이어지므로 보지 않음(쪽지 부탁은 시작 이야기에 있는 일)
    mon = day_with(valid_theme(), "MON", dayStep="쪽지에 적힌 부탁을 따라 공원에 왔어.")
    assert "DAY_STEP_MADE" not in codes(mon)


def test_day_step_must_not_name_the_first_speaker() -> None:
    """5차: 월요일 '윤슬이 잃어버린 모형 화석을 찾으러 왔어'를 윤슬이 말해 대화 SELF_NAME 31번."""
    theme = day_with(valid_theme(), "MON", dayStep="지호가 잃어버린 보리를 찾으러 왔어.")
    bad = reasons(theme, "SELF_NAME")
    assert bad and list(checks.fix_targets(bad)) == ["MON.dayStep"]
    # 이름 앞이 한글이면 다른 낱말('다가온'의 '가온')
    gaon = {"characters": [{"name": "가온"}], "days": []}
    assert not checks.self_named(gaon, "축제가 다가온 날 공원에 왔어.")
    assert checks.self_named(gaon, "가온이 잃어버린 손전등을 찾으러 왔어.")


def test_first_line_falls_back_to_code_sentence_so_dialogue_is_not_retried() -> None:
    """예전 저장본처럼 첫 줄로 못 쓰는 까닭이 남아 있어도 대화 첫 줄은 코드 문장, 지시문도 같은
    줄."""
    theme = checks.finalize_texts(
        day_with(valid_theme(), "MON", dayStep="지호가 보리를 찾으러 왔어.")
    )
    first = checks.first_line_text(theme, "MON")
    assert first == checks.day_step_text(theme, 0) and first.endswith("조사를 시작했어.")
    lines = checks.with_first_line(theme, "MON", [{"speaker": "뭉치", "text": "같이 보자!"}], GRADE)
    assert lines[0] == {"speaker": "지호", "text": first}
    user = prompts.dialogue_user(theme, "MON", _draft("ANALYZE"), GRADE, [])
    assert first in user and "지호가 보리를" not in user
    # 첫 줄로 쓸 수 있으면 모델 글 그대로
    ok = checks.finalize_texts(valid_theme())
    assert checks.first_line_text(ok, "TUE") == checks.theme_day(ok, "TUE")["dayStep"]


def test_graph_second_fix_of_day_step_uses_code_sentence_and_keeps_dialogue() -> None:
    """모델이 두 번 다 자기 이름을 쓰면 두 번째는 코드 문장, 월요일 대화는 빠지지 않음."""
    named = "지호가 보리를 찾으러 공원에 왔어."
    gen = gen_llm(
        theme=lambda n, d: generated_theme(day_with(valid_theme(), "MON", dayStep=named)),
        fix=lambda n, d: fixes(("MON.dayStep", named)),
    )
    response = run(gen, review_llm())
    assert response.failure is None
    assert gen.count("GeneratedFixes") == 1 and gen.count("GeneratedTheme") == 1
    assert response.dialogues[0].day == "MON"
    assert response.dialogues[0].lines[0].text.endswith("조사를 시작했어.")
    assert not [w for w in response.warnings if w.stage == "DIALOGUE"]


def test_day_step_prompts_tell_today_reason() -> None:
    plan = prompts.PLAN_SYSTEM
    assert "오늘 장소·그곳 사람이 사건과 어떻게 닿는지" in plan and "DAY_STEP_MADE" in plan
    rules = " ".join(prompts.fix_rules(valid_theme(), "WED.dayStep"))
    assert "DAY_STEP_MADE" in rules and "지호" in rules and "SELF_NAME" in rules


# ---------------------------------------------------------------- 시작 이야기 시각
def test_lost_intro_has_no_clock_time() -> None:
    base = {**valid_theme(), "storyType": "LOST"}
    clock = {**base, "intro": "오후 3시 20분, 지호는 보리가 없어진 걸 알았어요."}
    bad = reasons(clock, "INTRO_CLOCK")
    assert bad and "3시 20분" in bad[0] and list(checks.fix_targets(bad)) == ["intro"]
    assert "INTRO_CLOCK" not in codes({**base, "intro": "오후, 지호는 보리가 없어진 걸 알았어요."})
    assert "INTRO_CLOCK" not in codes({**base, "intro": "3시간 동안 지호는 보리를 찾았어요."})
    # 증거 칸의 시각은 됨, 다른 종류는 보지 않음
    assert "INTRO_CLOCK" not in codes(
        day_with(base, "MON", missionMaterial="이웃의 말: 오후 2시에 보리가 골목에 있었어요.")
    )
    assert not checks.intro_clock_problems({**clock, "storyType": "SOUND"})
    assert "INTRO_CLOCK" in families.LOST.rules and "INTRO_CLOCK" in families.TREASURE.rules


# ---------------------------------------------------------------- 지문 속 시키는 말
def test_material_must_not_order_an_activity() -> None:
    """5차 hand4b·way3: 지문 '이 자료를 그래프로 나타내 보자'를 미션 검사가 지문이라 빼서 못
    잡음."""
    order = "꽃 그림 6명, 잎 그림 3명이었어요. 이 자료를 그래프로 나타내 보자."
    theme = day_with(valid_theme(), "MON", missionMaterial=order)
    bad = reasons(theme, "ACT_NAME")
    assert bad and list(checks.fix_targets(bad)) == ["MON.missionMaterial"]
    fact = day_with(
        valid_theme(), "MON", missionMaterial="게시판에 그래프로 나타낸 표가 붙어 있어."
    )
    assert "ACT_NAME" not in codes(fact)
    # 미션 검사: 지문 문장이 문제 글에 그대로 있어도 시키는 문장은 지우지 않음
    draft = _draft("ANALYZE", question=f"관리인이 메모했어. {order} 무엇을 알 수 있을까?")
    assert checks.mission_act_names(theme, _request("ANALYZE"), draft) == ["그래프로 나타내기"]


# ---------------------------------------------------------------- 맡겨 둔 물건
def test_helper_cannot_say_they_entrusted_the_object() -> None:
    """5차 hand6b: 월요일 '선생님이 맡기는 걸 봤어' ↔ 수요일 돕는 사람 '내가 맡기기 전에'."""
    theme = day_with(gift_theme(), "WED", clue="내가 맡기기 전에 본 선물 상자는 가벼웠어.")
    assert any(r.startswith("KEPT_PLACE WED") for r in checks.check_theme(theme, GRADE))
    ok = day_with(gift_theme(), "WED", clue="맡겨지기 전에 내가 본 선물 상자는 가벼웠어.")
    assert not [r for r in checks.check_theme(ok, GRADE) if r.startswith("KEPT_PLACE WED")]
    assert "맡겨지기 전에" in families.GIFT.rules and "맡기기 전에 내가" not in families.GIFT.rules


# ---------------------------------------------------------------- 비밀 재료
def test_secret_food_event_has_not_happened_yet() -> None:
    """5차 hand5: 토요일 대회 떡인데 월요일에 '내가 대회에서 눈으로 직접 본 할머니 떡'."""
    food = {**gift_theme(), "storyType": "SECRET_INGREDIENT", "target": "할머니의 떡"}
    bad_day = day_with(food, "MON", clue="내가 대회에서 본 할머니 떡은 잿빛이 아니었어!")
    bad = [r for r in checks.check_theme(bad_day, GRADE) if r.startswith("EVENT_LATER")]
    assert bad and list(checks.fix_targets(bad)) == ["MON.clue"]
    assert not checks.event_later_problems(
        day_with(food, "MON", clue="떡을 만들 때 내가 본 색은 잿빛이 아니었어!")
    )
    assert not checks.event_later_problems(day_with(gift_theme(), "MON", clue="대회에서 봤어."))
    rules = families.SECRET_INGREDIENT.rules
    assert "토요일 잔치에 낼" in rules and "대회에 낸" not in rules and "EVENT_LATER" in rules


# ---------------------------------------------------------------- 사건 단서의 아이 자신
def test_story_clue_is_not_the_child_own_action() -> None:
    """5차 snd4: 사건 단서 '내 영상에는 소리가 난 뒤 윤슬이 잠시 귀 기울이는 모습이 담겼어!'."""
    theme = day_with(valid_theme(), "TUE", clue="내 영상에는 지호가 공원을 뛰어가는 모습이 담겼어!")
    bad = reasons(theme, "STORY_SELF")
    assert bad and list(checks.fix_targets(bad)) == ["TUE.clue"]
    assert "STORY_SELF" not in codes(valid_theme())
