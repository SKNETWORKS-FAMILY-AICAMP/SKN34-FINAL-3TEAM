"""#782 설계 v9(사용자 결정 2026-11-22 "응 고치고 7차 측정까지 해줘"): 6차 측정 치명·억지·실패 사유.

6차 r782-final40v6의 치명 3건·억지 13일·실패 8건을 사유별로 나눠, 규칙이 사는 세 곳(줄거리·미션
지시문, 코드 검사, 글·미션 검토 지시문)을 같이 고친다.
"""

import copy
from typing import Any

from app.theme_draft import checks, prompts
from app.theme_draft.nodes.plan import keep_filled
from tests.theme_draft.fixtures import day_with, valid_theme

GRADE = 3


def reasons(theme: dict[str, Any], grade: int = GRADE) -> list[str]:
    return checks.check_theme(theme, grade)


# ---------------------------------------------------------------- A. 돌아보기 날 일 틀
def test_reflect_day_uses_standard_area_frame() -> None:
    """6차 억지 13일 중 6일이 금요일 '처음 온 아이들에게 줄 경험 모음' 틀."""
    assert "REFLECT" not in checks.HELPER_FRAMES
    assert checks.frame_area(["4국05-03"], "REFLECT") == "05"
    assert checks.frame_area(["6국02-05"], "REFLECT") == "02"
    assert checks.frame_area(["4수01-10"], "REFLECT") is None
    assert "처음 온 아이들에게 들려줄" not in prompts.PLAN_SYSTEM


# ---------------------------------------------------------------- B. 수학 부탁 날 쓰임
def test_math_ask_day_says_where_the_answer_is_used() -> None:
    """6차 억지 13일 중 6일이 목요일 수학 '구한 값을 어디에 쓰는지 안 나옴'(세 곳)."""
    assert "수학 부탁 날은 구한 값을 그 사람이 어디에 쓰는지" in prompts.PLAN_SYSTEM
    assert "수학 부탁 날 문제가 구한 값을" in prompts.MISSION_REVIEW_SYSTEM
    theme = day_with(valid_theme(), "THU", missionWay=checks.ASK, helper="떡집 사장님")
    rules = " ".join(prompts.fix_rules(theme, "THU.missionHook"))
    assert "어디에 쓰는지" in rules


# ---------------------------------------------------------------- C. 부탁 날 지문이 기록
def test_ask_material_that_is_helpers_record_is_rewritten() -> None:
    """6차 치명 way6 화: 지문이 '내 메모에는 이렇게 적혀 있어…'라 미션 전에 단서가 보임."""
    bad_text = "내 메모에는 이렇게 적혀 있어. 책을 든 사람이 반납함 앞에서 잠깐 멈췄다."
    theme = day_with(valid_theme(), "TUE", missionWay=checks.ASK, missionMaterial=bad_text)
    hit = [r for r in reasons(theme) if r.startswith("MATERIAL_RECORD TUE")]
    assert hit
    assert checks.fix_targets(hit) == {"TUE.missionMaterial": hit}
    for ok in (
        "반납한 책은 표지를 닦아 서가에 꽂아요. 기록장에 날짜를 적어요.",
        "오늘 쓸 쌀가루는 0.245 kg, 콩가루는 0.130 kg입니다.",
    ):
        theme = day_with(valid_theme(), "TUE", missionWay=checks.ASK, missionMaterial=ok)
        assert not [r for r in reasons(theme) if r.startswith("MATERIAL_RECORD")], ok
    # 수사 날 지문은 그 사람이 가진 증거라 기록이 맞음
    theme = day_with(valid_theme(), "TUE", missionWay=checks.INVESTIGATE, missionMaterial=bad_text)
    assert not [r for r in reasons(theme) if r.startswith("MATERIAL_RECORD")]
    assert "MATERIAL_RECORD" in prompts.PLAN_SYSTEM
    assert "돕는 사람 자신의 기록" in prompts.REVIEW_SYSTEM
    ask = day_with(valid_theme(), "MON", missionWay=checks.ASK)
    assert "자신의 기록" in " ".join(prompts.fix_rules(ask, "MON.missionMaterial"))


# ---------------------------------------------------------------- D. 수사 날 기록 단서
def test_investigate_record_clue_does_not_quote_the_record() -> None:
    """5·6차 snd3 수: 지문 메모에 없는 말을 '내 메모에는 ~라고 적혀 있어'로 옮김."""
    day = {
        "day": "WED",
        "missionWay": checks.INVESTIGATE,
        "evidence": {"kind": "RECORD", "when": "그때"},
        "clue": "내 메모에는 한곳에서 나는 소리라고 적혀 있어!",
    }
    bad = checks.clue_source_problems(valid_theme(), day)
    assert bad and "따져 보니" in bad[0]
    day["clue"] = "메모를 따져 보니 소리는 한곳에서 났어!"
    assert not checks.clue_source_problems(valid_theme(), day)
    day["evidence"] = {"kind": "SIGHTING", "when": "그때"}
    day["clue"] = "내 메모에는 한곳에서 나는 소리라고 적혀 있어!"
    assert not checks.clue_source_problems(valid_theme(), day)  # 기록 날만
    assert "메모를 따져 보니" in prompts.PLAN_SYSTEM
    assert "지문(그 기록)에 없는 말" in prompts.REVIEW_SYSTEM


# ---------------------------------------------------------------- E. 약속 문구
def test_promise_follows_the_days_sense_not_story_type() -> None:
    """6차 snd3b: 소리 탐정이라 늘 '들은 걸'이었는데 단서는 본 등불 색(글 검토 CLUE_LOGIC)."""
    theme = copy.deepcopy(valid_theme())
    d = checks.theme_day(theme, "MON")
    d["evidence"] = {"kind": "SIGHTING", "when": "그때"}
    d["condition"] = {"kind": "STORY", "feature": "", "allowed": []}
    d["clue"] = "그때 등불이 파란색으로 깜빡였어!"
    assert prompts.ask_promise(theme, d) == "도와주면 그때 본 걸 알려 줄게"
    d["clue"] = "그 소리는 한 번만 짧게 났어!"
    assert prompts.ask_promise(theme, d) == "도와주면 그때 내가 들은 소리를 알려 줄게"
    d["condition"] = {"kind": "RULE", "feature": "남은 냄새", "allowed": ["꽃"]}
    assert prompts.ask_promise(theme, d) == "도와주면 그때 내가 맡은 냄새를 알려 줄게"
    assert checks.ASK_PROMISE_CASE.search("도와주면 내가 들은 소리를 알려 줄게")
    assert checks.ASK_PROMISE_CASE.search("도와주면 내가 맡은 냄새를 알려 줄게")


# ---------------------------------------------------------------- F. 긴 대화 줄 쉼표에서 나눔
def test_one_sentence_long_line_is_split_at_comma() -> None:
    """6차 new6b 수: 한 문장 40자 넘는 부탁 줄을 못 나눠 세 번 LINE_LENGTH로 대화가 빠짐."""
    long = "가루와 저울을 정리하는데 할 일이 남았어, 세 가루 무게를 소수로 읽고 함께 계산해 줄래?"
    assert len(long) > checks.LINE_MAX
    lines = [{"speaker": "직원", "text": long}, {"speaker": "뭉치", "text": "같이 해 보자!"}]
    out = checks.split_long_lines(lines, GRADE)
    assert len(out) == 3 and all(len(x["text"]) <= checks.LINE_MAX for x in out)
    assert out[0]["speaker"] == out[1]["speaker"] == "직원"
    no_comma = "쉼표 없이 아주 긴 한 문장이라서 둘로 나눌 자리가 하나도 없는 줄이야"
    assert checks.comma_split(no_comma) == []


# ---------------------------------------------------------------- G. 초3 분수 덧셈·뺄셈
def test_grade3_fraction_addition_is_caught_in_mission_and_plan() -> None:
    """6차 new3b·snd3b: '5/7-2/7'·'1/4통+2/4통'을 글 검토가 GRADE_VOCAB로 잡음(실패 2건)."""
    assert checks.math_ahead(["5/7-2/7=3/7"], 3) == ["분수의 덧셈·뺄셈"]
    assert checks.math_ahead(["1/4통+2/4통=3/4통"], 3) == ["분수의 덧셈·뺄셈"]
    assert checks.math_ahead(["5/7-2/7=3/7"], 4) == []
    assert checks.math_ahead(["분모가 같은 분수 2/7과 5/7의 크기를 비교해"], 3) == []
    theme = day_with(
        valid_theme(),
        "THU",
        missionMaterial="물통에 1/4통이 남아 있었고 2/4통을 더 채웠어요. 1/4+2/4를 구해요.",
    )
    theme["dayFrames"] = {"THU": {"codes": ["4수01-10"]}}
    hit = [r for r in reasons(theme) if r.startswith("GRADE_MATH THU")]
    assert hit and checks.fix_targets(hit) == {"THU.missionMaterial": hit}
    theme["dayFrames"] = {"THU": {"codes": ["4국02-03"]}}  # 수학 날만
    assert not [r for r in reasons(theme) if r.startswith("GRADE_MATH THU")]


# ---------------------------------------------------------------- H. 다시 만든 줄거리의 빈 위 칸
def test_regenerated_plan_keeps_previous_top_fields() -> None:
    """6차 way4b: 마지막 다시 생성에서 모델이 위 칸을 비워 REQUIRED로 실패."""
    previous = valid_theme()
    previous["introStory"] = "모델이 쓴 시작 이야기"
    new = copy.deepcopy(previous)
    for k in ("title", "world", "intro", "outro"):
        new[k] = ""
    filled = keep_filled(new, previous)
    assert {"title", "world", "intro", "outro"} <= set(filled)
    assert new["title"] == previous["title"] and new["intro"] == "모델이 쓴 시작 이야기"
    other = copy.deepcopy(previous)
    other["target"] = "다른 대상"
    other["title"] = other["intro"] = ""
    filled = keep_filled(other, previous)
    assert "title" in filled and "intro" not in filled  # 대상이 바뀌면 이야기는 안 옮김
    assert keep_filled(copy.deepcopy(previous), None) == []


# ---------------------------------------------------------------- I·J. 지시문만(코드로는 너무 넓음)
def test_story_clue_and_feature_word_rules_reach_plan_and_review() -> None:
    """6차 치명 new4 목(시작 이야기에서 본 부스러기를 단서로), 글 검토 CLUE_LOGIC 2건(특징 앞말)."""
    assert "아이가 이미 본 모습" in prompts.PLAN_SYSTEM
    assert "시작 이야기에서 아이가 이미 본 모습" in prompts.REVIEW_SYSTEM
    assert "'발자국 발 수'면 발자국" in prompts.PLAN_SYSTEM
