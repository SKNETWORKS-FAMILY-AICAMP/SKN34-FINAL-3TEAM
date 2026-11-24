"""#782 설계 v5·v6(사용자 결정 2026-11-22 "가로 하고"·"가만 하자 … 사람검수항목은 최대한
없게").

- v5: 오늘 온 까닭은 다시 모델이 씀(v7에서 어제 돕는 사람 이름 필수 DAY_STEP_LINK는 빼고
  지어냄 검사로 바꿈 — test_design_v7)
- v6(4차 측정 치명 결함 6건): 아이가 본 발자국은 흐릿하게(SEEN_TRACE), 맡겨 둔 대상 자체의
  흔적은 맡겨지기 전에 본 것(KEPT_TRACE·코드 다듬기 '맡겨지기 전에', v7에서 '맡기기'를 바꿈),
  남이 맡아 뒀다는 말(KEPT_PLACE). 사건 시각(EVENT_TIME)은 v7 INTRO_CLOCK으로 바꿈
"""

import copy
from typing import Any

from app.theme_draft import checks, families
from tests.theme_draft.fixtures import valid_theme
from tests.theme_draft.test_families import animal_theme
from tests.theme_draft.test_families_in_hand import gift_theme

GRADE = 3


def codes(theme: dict[str, Any]) -> list[str]:
    return sorted({r.split(" ")[0] for r in checks.check_theme(theme, GRADE)})


def ask(theme: dict[str, Any], day: str, **fields: Any) -> dict[str, Any]:
    theme = copy.deepcopy(theme)
    checks.theme_day(theme, day).update(missionWay=checks.FOLLOW, **fields)
    return theme


# ---------------------------------------------------------------- v6 아이가 본 발자국
def test_seen_footprint_must_be_blurred() -> None:
    theme = {**animal_theme("FOOTPRINT"), "intro": "지호가 모래밭에서 동물 발자국을 발견했어요."}
    bad = [r for r in checks.check_theme(theme, GRADE) if r.startswith("SEEN_TRACE")]
    assert bad and list(checks.fix_targets(bad)) == ["intro"]
    blurred = {**theme, "intro": "지호가 모래밭에서 반쯤 지워진 동물 발자국을 발견했어요."}
    assert "SEEN_TRACE" not in codes(blurred)
    assert "SEEN_TRACE" in families.FOOTPRINT.rules
    # 동물 종류가 아니면 보지 않음
    assert not checks.seen_trace_problems({**valid_theme(), "intro": "발자국을 봤어요."})


# ---------------------------------------------------------------- v6 맡겨 둔 대상 자체의 흔적
def test_kept_object_trace_is_seen_before_it_was_kept() -> None:
    theme = ask(gift_theme(), "MON", clue="상자를 들어 보니 묵직한 상자였어.")
    assert checks.object_self_trace(theme, checks.theme_day(theme, "MON"))  # 상자 무게
    bad = [r for r in checks.check_theme(theme, GRADE) if r.startswith("KEPT_TRACE")]
    assert bad and list(checks.fix_targets(bad)) == ["MON.clue"]
    ok = ask(gift_theme(), "MON", clue="배달할 때 내가 들어 보니 묵직한 상자였어.")
    assert "KEPT_TRACE" not in codes(ok)
    # 코드 다듬기: '내가 ~'로 시작하면 앞에 '맡겨지기 전에'(v7: 말한 사람이 맡긴 사람이 안 되게)
    soft = ask(gift_theme(), "MON", clue="내가 들어 보니 묵직한 상자였어.")
    checks.normalize_clue_source(soft)
    assert checks.theme_day(soft, "MON")["clue"] == "맡겨지기 전에 내가 들어 보니 묵직한 상자였어."
    assert not [r for r in checks.check_theme(soft, GRADE) if r.startswith("KEPT_")]
    # 틀 문장도 맡겨지기 전
    template = checks.clue_template(theme, checks.theme_day(theme, "MON"))
    assert template and template.startswith("맡겨지기 전 내가 본")
    # 곁에 두는 종류(비밀 재료)는 보지 않음
    food = {**theme, "storyType": "SECRET_INGREDIENT"}
    assert not checks.object_self_trace(food, checks.theme_day(food, "MON"))


def test_route_trace_on_the_road_is_not_object_trace() -> None:
    """길에 남은 흔적('수레 바퀴 자국은 아스팔트 바닥에')은 대상 자체가 아님."""
    route = ask(
        {**gift_theme(), "storyType": "ROUTE", "target": "배달된 꽃다발"},
        "MON",
        clue="내가 본 꽃다발 수레 바퀴 자국은 아스팔트 바닥에 남은 건 아니었어!",
        condition={"kind": "RULE", "feature": "길바닥 재질", "allowed": ["흙"]},
    )
    assert not checks.object_self_trace(route, checks.theme_day(route, "MON"))
    # 대상에 묻은 것을 말하면 특징 이름이 '바닥'이어도 대상 자체(4차 hand5b)
    glove = ask(
        {
            **gift_theme(),
            "storyType": "ORIGIN",
            "branch": "물건",
            "target": "운동장에 떨어져 있던 털장갑",
        },
        "MON",
        clue="내가 보니 털장갑 밑면의 흙은 마른 땅에서 묻었어!",
        condition={"kind": "RULE", "feature": "바닥 물기", "allowed": ["마른"]},
    )
    assert checks.object_self_trace(glove, checks.theme_day(glove, "MON"))


def test_helper_cannot_say_they_kept_the_object() -> None:
    theme = ask(gift_theme(), "TUE", clue="내가 맡아 둔 선물 상자는 서점에서 계산했어.")
    assert any(r.startswith("KEPT_PLACE TUE") for r in checks.check_theme(theme, GRADE))
    office = copy.deepcopy(theme)
    checks.theme_day(office, "TUE")["helper"] = "아파트 관리실 직원"
    assert not [
        r for r in checks.check_theme(office, GRADE) if r.startswith("KEPT_PLACE TUE clue 대상은")
    ]
