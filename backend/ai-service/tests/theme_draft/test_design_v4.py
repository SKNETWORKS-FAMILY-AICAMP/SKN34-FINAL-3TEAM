"""#782 설계 v4(사용자 결정 2026-11-22 "둘 다 그렇게 진행해"): 3차 측정의 치명 결함 6건과 구현 실수.

- 출처: 부탁 날 단서는 코드가 먼저 다듬음(normalize_clue_source — 전해 들은 말 끝·'내 {매체}'·
  '내가 보니'), 남은 것만 CLUE_SOURCE(남의 기록, '본 흔적'인데 소리)
- 시작 이야기: 시간 탐정은 때를 가리키는 말 금지(TIME_WORD), 소리 탐정 '밤마다'(SOUND_NIGHT·대상 글
  다듬기), 맡겨 둔 대상의 다른 맡긴 곳(KEPT_PLACE)
- 구현 실수: 대화 6줄(B2), 월요일 오늘 온 까닭의 대상 글(B3), 예전 저장본 대화(B4). 단서만 고쳐
  쓰는 길의 틀 문장(B1)은 test_graph
- 출처 찾기 '물건'은 분실물 선반(쪽지 없음)
"""

import copy
from typing import Any

from app.theme_draft import checks, families, prompts
from tests.theme_draft.fixtures import day_with, dialogue, generated_theme, valid_theme
from tests.theme_draft.test_families_sound import sound_theme
from tests.theme_draft.test_graph import fixes, gen_llm, review_llm, run

GRADE = 3


def ask(theme: dict[str, Any], day: str, **fields: Any) -> dict[str, Any]:
    theme = copy.deepcopy(theme)
    checks.theme_day(theme, day).update(missionWay=checks.ASK, **fields)
    return theme


def codes(theme: dict[str, Any]) -> list[str]:
    return sorted({r.split(" ")[0] for r in checks.check_theme(theme, GRADE)})


# ---------------------------------------------------------------- 출처: 코드가 먼저 다듬음
def test_normalize_fixes_hearsay_record_owner_and_trace_link() -> None:
    theme = ask(valid_theme(), "WED", clue="보리는 지붕이 없는 곳으로 갔대.")
    theme = ask(theme, "MON", clue="보리 발자국이 젖어 있었어.")  # 흔적 날, 연결 없음
    theme = ask(theme, "FRI", clue="일지에 보리 발바닥에 흙이 묻어 있었다고 적혔어.")  # 기록 날
    theme["evidencePlan"] = {"FRI": {"kind": "RECORD", "medium": "일지"}}
    checks.normalize_clue_source(theme)
    assert checks.theme_day(theme, "WED")["clue"] == "보리는 지붕이 없는 곳으로 갔어."
    assert checks.theme_day(theme, "MON")["clue"] == "내가 보니 보리 발자국이 젖어 있었어."
    assert checks.theme_day(theme, "FRI")["clue"].startswith("내 일지에 ")
    before = copy.deepcopy(theme)
    checks.normalize_clue_source(theme)  # 여러 번 불러도 같음
    assert theme == before
    # 수사 날은 다듬지 않음
    inv = day_with(valid_theme(), "WED", clue="보리는 지붕이 없는 곳으로 갔대.")
    checks.normalize_clue_source(inv)
    assert checks.theme_day(inv, "WED")["clue"].endswith("갔대.")


def test_normalize_trace_sense_says_how_it_was_known() -> None:
    d = {"day": "FRI", "missionWay": checks.ASK, "evidence": {"kind": "TRACE"}, "clue": ""}
    theme = {"storyType": "GIFT", "days": [d]}
    for clue, lead in (
        ("상자에서 흙 소리가 났어!", "내가 흔들어 보니 "),
        ("상자 안쪽에 꽃향이 배어 있었어!", "내가 맡아 보니 "),
        ("떡에서 고소한 맛이 났어!", "내가 맛보니 "),
    ):
        d["clue"] = clue
        checks.normalize_clue_source(theme)
        assert d["clue"] == lead + clue
    # 글자 수를 넘으면 다듬지 않음(CLUE_SOURCE가 잡아 고쳐 쓰기)
    d["clue"] = "가" * 41  # 흔적 날 상한 46자 — 앞말 6자를 붙이면 넘음
    checks.normalize_clue_source(theme)
    assert d["clue"] == "가" * 41


def test_clue_source_catches_others_record_and_seen_sound() -> None:
    theme = ask(valid_theme(), "FRI", clue="받은 뒤 쓴 일지에는 흙이 묻어 있었다고 적혀 있어!")
    theme["evidencePlan"] = {"FRI": {"kind": "RECORD", "medium": "일지"}}
    assert any(
        r.startswith("CLUE_SOURCE FRI") and "자신의 기록" in r
        for r in checks.check_theme(theme, GRADE)
    )
    sound = {
        "day": "FRI",
        "missionWay": checks.ASK,
        "evidence": {"kind": "TRACE"},
        "clue": "내가 본 상자 흔적은 흔들면 흙 소리가 난다는 거야!",
    }
    bad = checks.clue_source_problems({"days": [sound]}, sound)
    assert bad and "눈으로 본 것이 아님" in bad[0] and "흔들어 보니" in bad[0]
    sound["clue"] = "내가 흔들어 보니 상자에서 흙 소리가 났어!"
    assert checks.clue_source_problems({"days": [sound]}, sound) == []


# ---------------------------------------------------------------- 시작 이야기
def test_sound_night_only_when_nights_split_candidates() -> None:
    theme = sound_theme()
    nights = checks.feature_table(theme)[0].get("소리 나는 밤") or {}
    split = {**theme, "introStory": "밤마다 이상한 소리가 들렸어요. 소리 박사 뭉치가 출동해요."}
    found = [r for r in checks.check_theme(split, GRADE) if r.startswith("SOUND_NIGHT")]
    assert bool(found) == (len(set(nights.values())) > 1)
    assert checks.fix_targets(found) == ({"intro": found} if found else {})
    # 대상 글은 코드가 '밤에'로
    assert (
        checks.normalize_sound_target({**theme, "target": "할머니 댁에서 밤마다 들린 소리"})[
            "target"
        ]
        == "할머니 댁에서 밤에 들린 소리"
    )
    assert "밤마다 궁금한" not in families.SOUND.rules and "SOUND_NIGHT" in families.SOUND.rules


def test_kept_target_cannot_be_left_elsewhere() -> None:
    from tests.theme_draft.test_families_in_hand import gift_theme

    bad_place = day_with(
        gift_theme(), "THU", clue="일지에는 선물 상자를 준비실에 맡겼다고 적혀 있어!"
    )
    found = [r for r in checks.check_theme(bad_place, GRADE) if r.startswith("KEPT_PLACE")]
    assert found and list(checks.fix_targets(found)) == ["THU.clue"]
    ok = day_with(gift_theme(), "THU", clue="일지에는 선물 상자를 관리실에 맡겼다고 적혀 있어!")
    assert not [r for r in checks.check_theme(ok, GRADE) if r.startswith("KEPT_PLACE")]
    # 맡겨 두지 않는 종류는 보지 않음
    assert not [
        r
        for r in checks.check_theme(
            day_with(valid_theme(), "THU", sceneNote="준비실에 맡겼다"), GRADE
        )
        if r.startswith("KEPT_PLACE")
    ]


def test_origin_object_is_lost_and_found_without_note() -> None:
    cut = families.ORIGIN.intro_cuts[1]
    assert "분실물 선반" in cut and "열어 보세요" not in cut
    assert "분실물 선반" in families.ORIGIN.rules
    assert "KEPT_PLACE" in families.GIFT.rules and "KEPT_PLACE" in families.ROUTE.rules


# ---------------------------------------------------------------- 구현 실수
def test_first_line_trims_model_lines_to_grade_limit() -> None:
    """B2: 모델이 5줄을 다 쓰면 첫 줄을 붙여 6줄 → 모델의 앞쪽 줄을 지워 5줄, 마지막 뭉치는
    그대로."""
    theme = checks.finalize_texts(valid_theme())
    model = [{"speaker": "지호", "text": f"줄 {i}"} for i in range(4)] + [
        {"speaker": "뭉치", "text": "같이 해 보자!"}
    ]
    lines = checks.with_first_line(theme, "TUE", model, GRADE)
    hi = checks.DIALOGUE_LINES[GRADE][1]
    assert len(lines) == hi and lines[-1]["speaker"] == "뭉치"
    assert lines[0]["text"] == checks.theme_day(theme, "TUE")["dayStep"]
    assert lines[1]["text"] == "줄 1"  # 모델의 첫 줄(오늘 온 까닭 되풀이)이 지워짐
    short = checks.with_first_line(theme, "TUE", model[2:], GRADE)
    assert len(short) == 4  # 상한 안이면 지우지 않음


def test_monday_step_does_not_show_model_target() -> None:
    """B3: 코드 문장의 월요일 오늘 온 까닭에 모델이 쓴 대상 글을 넣지 않음."""
    theme = {**valid_theme(), "target": "문 앞에 놓여 있던 꽃다발"}
    mon = checks.day_step_text(theme, 0)
    assert "꽃다발" not in mon and mon.endswith("조사를 시작했어.")


def test_plan_prompt_tells_record_owner_and_trace_sense() -> None:
    plan = prompts.PLAN_SYSTEM
    assert "'내 {매체}'로 쓰고" in plan and "'내가 흔들어 보니·맡아 보니·맛보니'" in plan


def test_other_persons_hearing_is_not_softened_but_rewritten() -> None:
    """'관리인이 들은 소리는 …였대'·'윤슬이 들은 소리는'(주인공): 끝말만 바꾸면 남의 말이 그대로라
    다듬지 않고 CLUE_SOURCE로 다시 씀(저장된 2·3차 통과 59개에서 4건, 모두 실제 남의 말)."""
    theme = ask(valid_theme(), "WED", clue="관리인이 들은 소리는 지붕이 없는 곳에서 났대!")
    checks.normalize_clue_source(theme)
    assert checks.theme_day(theme, "WED")["clue"].endswith("났대!")
    bad = [r for r in checks.check_theme(theme, GRADE) if r.startswith("CLUE_SOURCE WED")]
    assert any("다른 사람('관리인')" in r for r in bad)
    assert checks.other_source("내가 본 보리 발자국은 젖어 있었어") is None
    assert checks.other_source("꽃다발을 든 사람이 넓은 길로 갔어") is None


# ---------------------------------------------------------------- 다시 쓰는 길(그래프 끝까지)
def test_graph_second_fix_uses_template_when_normalize_cannot() -> None:
    """코드 다듬기로 못 고치는 남의 기록('받은 뒤 쓴 일지')을 모델이 두 번 다 그대로 쓰면, 두 번째
    고쳐 쓰기는 모델을 부르지 않고 코드 틀 문장(fix_theme)."""
    others = "받은 뒤 쓴 일지에는 보리 발바닥에 흙이 묻었다고 적혀 있어."
    gen = gen_llm(
        theme=lambda n, d: generated_theme(day_with(valid_theme(), "FRI", clue=others)),
        fix=lambda n, d: fixes(("FRI.clue", others)),
    )
    response = run(gen, review_llm())
    assert response.failure is None
    assert gen.count("GeneratedFixes") == 1 and gen.count("GeneratedTheme") == 1
    assert response.theme is not None
    fri = response.theme.days[4].clue
    assert fri.startswith("내 일지에") and "'흙'" in fri


def test_graph_dialogue_with_five_model_lines_keeps_the_day() -> None:
    """B2: 모델이 5줄을 다 써도 첫 줄을 붙인 뒤 상한(5줄)에 맞춰 그날 대화가 빠지지 않음."""

    def five(n: int, d: str | None) -> Any:
        return dialogue(d, lines=[*dialogue(d).lines[:1], *dialogue(d).lines])

    response = run(gen_llm(dlg=five), review_llm())
    assert response.failure is None
    assert not [w for w in response.warnings if w.stage == "DIALOGUE"]
    assert all(len(x.lines) == 5 and x.lines[-1].speaker == "뭉치" for x in response.dialogues)
