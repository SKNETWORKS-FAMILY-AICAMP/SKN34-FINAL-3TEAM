"""#782 미션이 사건과 따로 놂: 정보 없는 힌트 단서(CLUE_EMPTY·코드 수리), 미션 주 자료 = 그날 증거,
수사 연결 문장 형식, 살펴보기 한마디.

valid_theme: 월 RULE(물기 젖음: 창고·정자) → 화 STORY(사건 단서) → 수 HINT(지붕 없음) → 목 STORY →
금 RULE(땅 흙: 놀이터). 후보 놀이터(모래·지붕 없음·젖음), 텃밭(흙·없음·젖음), 창고(시멘트·있음·
마름), 정자(흙·있음·마름).
"""

import copy
from typing import Any

import pytest

from app.theme_draft import checks, prompts
from app.theme_draft.nodes.plan import code_adjust
from tests.theme_draft import fixtures
from tests.theme_draft.fixtures import day_with, feature, generated_theme, valid_theme
from tests.theme_draft.test_graph import fixes, gen_llm, review_llm, run


def hint(theme: dict[str, Any], day: str, feat: str, allowed: list[str], clue: str) -> dict:
    return day_with(
        theme, day, clue=clue, condition={"kind": "HINT", "feature": feat, "allowed": allowed}
    )


def codes(reasons: list[str]) -> list[str]:
    return sorted(r.split(" ")[0] for r in reasons)


def with_color(theme: dict[str, Any]) -> dict[str, Any]:
    """남은 후보(놀이터·텃밭)가 값을 다 채우는 특징 '깃발 색'을 더한 줄거리."""
    theme = copy.deepcopy(theme)
    theme["features"].append(
        feature("깃발 색", {"놀이터": "빨강", "텃밭": "파랑", "창고": "빨강", "정자": "파랑"})
    )
    return theme


# ---------------------------------------------------------------- 정보 없는 힌트 단서
def test_hint_listing_every_value_is_clue_empty() -> None:
    """허용 값이 특징 값 전부면 아무것도 알려 주지 않는 단서(운영 화면 '넓은 자리나 좁은 자리')."""
    theme = hint(
        valid_theme(),
        "TUE",
        "지붕",
        ["없음", "있음"],
        "보리는 지붕이 없는 곳이나 있는 곳에 있었대.",
    )
    assert "CLUE_EMPTY" in codes(checks.check_theme(theme, 3))
    assert checks.check_theme(valid_theme(), 3) == []  # 남은 후보 값만 말하는 힌트는 통과


def test_monday_hint_is_always_empty() -> None:
    """아직 빠진 후보가 없는 월요일 힌트는 어떤 특징이든 값 전부라 좁히거나 다른 특징으로 못 바꿈.
    #782 테마 짜임부터는 사건 단서로 바꿈(전에는 그대로 두어 CLUE_EMPTY로 다시 생성)."""
    theme = hint(
        valid_theme(), "MON", "물기", ["젖음", "마름"], "보리 발자국은 젖거나 마른 자리에 있었어."
    )
    assert "CLUE_EMPTY MON" in [" ".join(r.split(" ")[:2]) for r in checks.check_theme(theme, 3)]
    assert checks.repair_hints(theme) == ["MON"]
    assert checks.theme_day(theme, "MON")["condition"] == {
        "kind": "STORY",
        "feature": "",
        "allowed": [],
    }
    assert "CLUE_EMPTY" not in codes(checks.check_theme(theme, 3))


def test_repair_hints_narrows_to_remaining_values() -> None:
    """이미 빠진 창고(시멘트)의 값까지 넣은 화요일 힌트는 남은 후보 값(모래·흙)으로 좁힘."""
    theme = hint(
        valid_theme(),
        "TUE",
        "땅",
        ["모래", "흙", "시멘트"],
        "보리 발에 모래나 흙이나 시멘트가 묻었대.",
    )
    assert "CLUE_EMPTY" in codes(checks.check_theme(theme, 3))
    assert checks.repair_hints(theme) == ["TUE"]
    assert checks.theme_day(theme, "TUE")["condition"] == {
        "kind": "HINT",
        "feature": "땅",
        "allowed": ["모래", "흙"],
    }


def test_repair_hints_switches_repeated_hint_to_other_feature() -> None:
    """화요일 지붕 힌트를 남은 후보 값(없음)으로 좁히면 수요일 힌트(지붕 없음)와 같은 단서가 되어
    수요일을 아직 쓰지 않은 특징(땅: 모래·흙)으로 바꿈(#782 테마 짜임 CLUE_REPEAT)."""
    theme = hint(
        valid_theme(),
        "TUE",
        "지붕",
        ["없음", "있음"],
        "보리는 지붕이 없는 곳이나 있는 곳에 있었대.",
    )
    assert checks.repair_hints(theme) == ["TUE", "WED"]
    assert checks.theme_day(theme, "TUE")["condition"] == {
        "kind": "HINT",
        "feature": "지붕",
        "allowed": ["없음"],
    }
    assert checks.theme_day(theme, "WED")["condition"] == {
        "kind": "HINT",
        "feature": "땅",
        "allowed": ["모래", "흙"],
    }


def test_repair_hints_switches_to_informative_feature() -> None:
    """남은 후보 값이 곧 특징 값 전부(깃발 색 빨강·파랑)면 남은 후보 값이 일부뿐인 특징으로 바꿈.
    값이 적게 남는 특징(지붕: 없음 하나)을 고름. 수요일 지붕 힌트는 사건 단서로 두어 되풀이가 생기지
    않게 함(되풀이는 test_repair_hints_switches_repeated_hint_to_other_feature)."""
    theme = hint(
        with_color(valid_theme()),
        "TUE",
        "깃발 색",
        ["빨강", "파랑"],
        "보리 곁 깃발은 빨강이나 파랑이었대.",
    )
    theme = day_with(
        theme,
        "WED",
        clue="보리가 나비를 쫓아 길모퉁이를 돌았대.",
        condition={"kind": "STORY", "feature": "", "allowed": []},
    )
    assert "CLUE_EMPTY" in codes(checks.check_theme(theme, 3))
    assert checks.repair_hints(theme) == ["TUE"]
    assert checks.theme_day(theme, "TUE")["condition"] == {
        "kind": "HINT",
        "feature": "지붕",
        "allowed": ["없음"],
    }


def test_repair_hints_keeps_trace_day_on_traceable_feature() -> None:
    """흔적 날은 흔적에 남을 수 있는 특징만(kind_fits): 값이 하나 남는 지붕은 흔적이 아니라 빼고,
    흔적이 되는 물기(젖음)는 월요일과 같은 단서라(#782 CLUE_REPEAT) 빼고, 흔적이 되는 땅(모래·흙)을
    고름."""
    theme = hint(
        with_color(valid_theme()),
        "TUE",
        "깃발 색",
        ["빨강", "파랑"],
        "보리 곁 깃발은 빨강이나 파랑이었어.",
    )
    checks.theme_day(theme, "TUE")["evidence"] = {"kind": "TRACE", "when": "보리가 사라진 날 오후"}
    assert checks.repair_hints(theme) == ["TUE"]
    cond = checks.theme_day(theme, "TUE")["condition"]
    assert cond["feature"] == "땅" and cond["allowed"] == ["모래", "흙"]


# 이미 빠진 창고 값(시멘트)까지 넣어 특징 값 전부를 말하는 화요일 힌트(좁히면 금요일 땅 흙과도 다름)
def _empty_tue(theme: dict[str, Any]) -> dict[str, Any]:
    return hint(
        theme, "TUE", "땅", ["모래", "흙", "시멘트"], "보리 발에 모래나 흙이나 시멘트가 묻었대."
    )


# #782 설계 v13: 기본 요청의 화요일은 수사 날이라 지문 증언에 그날 단서 내용이 들어감. 대역 미션도
# 같은 지문을 쓰게 fixtures.MATERIAL을 바꿔 끼움(코드가 단서 조건을 좁혀도 남는 내용)
TUE_TESTIMONY = (
    "빵집 아저씨의 말: 그때 내가 본 보리 발에 묻은 건 시멘트가 아니었어. 보리 털은 비에 젖어 "
    "반짝였지."
)


def test_code_adjust_asks_only_that_clue_rewritten() -> None:
    targets = code_adjust(checks.fill_rules_out(_empty_tue(valid_theme())))
    assert list(targets) == ["TUE.clue"] and targets["TUE.clue"][0].startswith("HINT_FIX TUE ")
    assert "허용 값 ['모래', '흙']" in targets["TUE.clue"][0]


def test_graph_fixes_empty_hint_without_regenerating_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    """코드가 조건을 고치고 그날 단서만 고쳐 써서 통과(줄거리 다시 생성 없음)."""
    monkeypatch.setitem(fixtures.MATERIAL, "TUE", TUE_TESTIMONY)
    gen = gen_llm(
        theme=lambda n, d: generated_theme(_empty_tue(valid_theme())),
        fix=lambda n, d: fixes(("TUE.clue", "보리 발에 묻은 건 시멘트가 아니었대.")),
    )
    response = run(gen, review_llm())
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 1 and gen.count("GeneratedFixes") == 1
    assert "HINT_FIX TUE" in gen.users("GeneratedFixes")[0]
    assert (
        response.theme is not None
        and response.theme.days[1].clue == "보리 발에 묻은 건 시멘트가 아니었대."
    )


def test_graph_turns_unfixable_empty_hint_into_story_without_regenerating_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """월요일 힌트(빠진 후보가 아직 없음)만 비고 정답 논리는 맞는 줄거리: 좁히거나 다른 특징으로 못
    바꾸는 힌트를 코드가 사건 단서로 바꾸고 그날 단서만 고쳐 씀(#782 테마 짜임, 사용자 결정
    2026-11-19. 전에는 CLUE_EMPTY 사유를 넣어 줄거리를 다시 만듦)."""
    monkeypatch.setitem(fixtures.MATERIAL, "TUE", TUE_TESTIMONY)
    broken = hint(
        valid_theme(), "MON", "물기", ["젖음", "마름"], "보리 발자국은 젖거나 마른 자리에 있었어."
    )
    broken = day_with(
        broken,
        "TUE",
        clue="보리 털이 비에 젖어 반짝였대.",
        condition={"kind": "RULE", "feature": "물기", "allowed": ["젖음"]},
    )
    assert codes(checks.check_theme(broken, 3)) == ["CLUE_EMPTY"]
    story = "내가 본 보리 발자국이 길모퉁이 쪽으로 이어져 있었어."  # 부탁 날 흔적(CLUE_SOURCE)
    gen = gen_llm(
        theme=lambda n, d: generated_theme(broken),
        fix=lambda n, d: fixes(("MON.clue", story)),
    )
    response = run(gen, review_llm())
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 1 and gen.count("GeneratedFixes") == 1
    user = gen.users("GeneratedFixes")[0]
    assert "path: MON.clue" in user and "HINT_FIX MON" in user and "사건 단서로 바꿈" in user
    assert "사건 단서다" in user  # 사건 단서 고쳐 쓰기 규칙(fix_rules)
    assert response.theme is not None
    mon = response.theme.days[0]
    assert (mon.clue, mon.rules_out, mon.clue_feature) == (story, [], None)


def test_plan_prompt_forbids_empty_hint_and_clue_time() -> None:
    assert (
        "CLUE_EMPTY" in prompts.PLAN_SYSTEM
        and "아무것도 알려 주지 않는 단서" in prompts.PLAN_SYSTEM
    )
    assert "clue에는 시각을 쓰지 않는다" in prompts.PLAN_SYSTEM


# ---------------------------------------------------------------- 미션 주 자료·수사 연결 문장
def test_mission_hook_is_helper_line_by_way() -> None:
    """#782 미션 방식(사용자 결정 2026-11-20): 수사 연결 문장은 그날 돕는 사람의 부탁·증거를 같이
    보자는 말(전에는 늘 증거의 한 부분)."""
    plan = prompts.PLAN_SYSTEM
    assert "helper가 하는 부탁·증거를 같이 보자는 말 한 줄" in plan
    assert "찾은 증거에서 그날 단서 특징 값이 아닌 한 부분" not in plan
    assert (
        "형식은 '<찾은 증거>를 풀려면" not in plan
        and "증거 자체를 살피라고 하지 않는다" not in plan
    )
    rules = " ".join(prompts.fix_rules(valid_theme(), "THU.missionHook"))
    # #782 테마 짜임: 수사 연결 문장은 대화 재료라 정해진 말 꼴('같이 <활동>해 볼래?')을 두지 않음
    assert "그날 활동을 함께 말함" in rules and "같이 <활동>해 볼래?" not in rules
    assert "증거를 같이 읽고 따져 보자는 말" in rules  # 예전 저장본·수사 날
    ask = day_with(valid_theme(), "THU", missionWay=checks.ASK)
    ask_rules = " ".join(prompts.fix_rules(ask, "THU.missionHook"))
    assert "돕는 사람의 부탁 한 줄" in ask_rules and "무엇을 알려 줄지는 말하지" in ask_rules
    assert "풀려면 그날 배울 것이 필요하다" not in rules
    hook = prompts.hook_fix_user(valid_theme(), {"THU": ("문제", [])})
    assert "사실대로" in hook and "풀려면 오늘 문제의 활동이 필요하다" not in hook


def test_mission_material_follows_way_and_story_link_checks_it() -> None:
    """수사 날(예전 저장본 포함)은 돕는 사람이 가진 증거가 주 자료, 부탁 날은 그 사람의
    일(사건 증거가 아니어도 됨)."""
    extra = prompts.mission_extra(valid_theme(), "TUE", 3, [])
    assert "오늘 미션 방식: 수사. 문제의 주 자료는 오늘 돕는 사람이 가진 증거" in extra
    ask = prompts.mission_extra(day_with(valid_theme(), "TUE", missionWay=checks.ASK), "TUE", 3, [])
    assert "오늘 미션 방식: 부탁. 문제는 오늘 돕는 사람(빵집 아저씨)의 일로 쓴다" in ask
    assert "사건 증거인 척 지어내지 않는다" in ask and "오늘 찾은 증거" not in ask
    review = prompts.MISSION_REVIEW_SYSTEM
    assert "STORY_LINK: story가 주어지면 missionWay대로 본다" in review
    assert "증거가 아닌 장면의 물건·상황만 다루면 WARN" in review
    assert "그 사람의 일이 사건 증거가 아니어도 됨" in review


def test_spot_line_points_to_what_to_look_at() -> None:
    assert "증거는 찾았다는 말" not in prompts.MOTION_SYSTEM
    assert "학생이 볼 부분·모습이나 확인할 점" in prompts.MOTION_SYSTEM
    assert "'찾았어!'·'살펴볼까?'처럼" in prompts.MOTION_SYSTEM


# ---------------------------------------------------------------- 미션 지문(missionMaterial,
# 줄거리가 정함)
def test_material_with_clue_value_or_candidate_is_field_fixed() -> None:
    """미션 지문은 문제 전에 학생이 읽어 그날 단서 결론·후보 이름을 막고 그 칸만 고쳐 씀."""
    early = day_with(valid_theme(), "FRI", missionMaterial="일지: 흙 바닥의 발자국 사이 30cm.")
    bad = checks.check_theme(early, 3)
    assert codes(bad) == ["CLUE_EARLY"] and list(checks.fix_targets(bad)) == ["FRI.missionMaterial"]
    named = day_with(valid_theme(), "TUE", missionMaterial="할머니의 말: 보리가 창고 쪽으로 갔어.")
    bad = checks.check_theme(named, 3)
    assert codes(bad) == ["ANSWER_LEAK"] and list(checks.fix_targets(bad)) == [
        "TUE.missionMaterial"
    ]
    long = day_with(valid_theme(), "MON", missionMaterial="가" * 151)
    assert codes(checks.check_theme(long, 3)) == ["LENGTH"]


def test_material_is_internal_and_goes_to_mission_and_reviews() -> None:
    theme = checks.fill_rules_out(valid_theme())
    material = theme["days"][4]["missionMaterial"]
    assert "missionMaterial" not in checks.public_theme(theme)["days"][4]  # 응답 계약 그대로
    extra = prompts.mission_extra(theme, "FRI", 3, [])
    assert f"오늘 문제의 지문(줄거리가 정한 그날 일의 자료): {material}" in extra
    assert "그 글을 question 안에 그대로 넣고" in extra
    assert prompts.story_brief(theme, "FRI")["missionMaterial"] == material
    assert (
        "missionMaterial" in prompts.PLAN_SYSTEM
        and "그때 찾는 대상·사건에 관한" in prompts.PLAN_SYSTEM
    )
    rules = " ".join(prompts.fix_rules(theme, "FRI.missionMaterial"))
    assert "['흙']" in rules and "그때 찾는 대상·사건에 관한 내용으로" in rules
    ask = day_with(theme, "FRI", missionWay=checks.ASK)
    assert "사건 증거인 척 지어내지 않" in " ".join(prompts.fix_rules(ask, "FRI.missionMaterial"))


def test_old_theme_without_material_still_makes_mission() -> None:
    """예전 저장본(부분 다시 생성 base)은 지문 칸이 없어 지문 줄·그대로 쓰기 규칙 없이 만든다."""
    theme = checks.fill_rules_out(valid_theme())
    for d in theme["days"]:
        del d["missionMaterial"]
    extra = prompts.mission_extra(theme, "THU", 3, [])
    assert "오늘 문제의 지문(" not in extra and "오늘 미션 방식: 수사" in extra
    assert "missionMaterial" not in prompts.story_brief(theme, "THU")


def test_hook_names_the_part_but_not_the_answer() -> None:
    """수사 연결 문장이 고르기 문제의 답 자료를 미리 말해 글 검토 ANSWER_HINT(실측 auto5b)."""
    assert "그 안에서 학생이 고르거나 답할 것(계산 결과, 중심 생각, 고를 자료)은 말하지 않는다" in (
        prompts.PLAN_SYSTEM
    )


# ---------------------------------------------------------------- 미션이 지문을 그대로 쓰는지(코드
# 검사)
def mission_codes(day: str, **overrides: Any) -> list[str]:
    from app.mission_draft.models import Draft, MissionDraftRequest
    from tests.theme_draft.fixtures import DAY_TYPES, mission_draft
    from tests.theme_draft.helpers import request_body

    theme = checks.fill_rules_out(valid_theme())
    req = MissionDraftRequest.model_validate(
        {**request_body()["missions"][list(DAY_TYPES).index(day)], "gradeMin": 3, "gradeMax": 3}
    )
    draft = Draft.model_validate(mission_draft(DAY_TYPES[day], **overrides).model_dump())
    return codes(checks.material_problems(theme, req, draft))


def test_mission_must_use_material_as_is() -> None:
    """지문을 쓰지 않으면 그 요일 미션만 다시. 지문 밖 글 덧붙임은 코드로 막지 않음(막아 보니
    같은 위반을 되풀이해 초안이 통째로 실패해 STORY_LINK 경고로 둠, 실측 40건)."""
    material = valid_theme()["days"][1]["missionMaterial"]
    assert mission_codes("TUE") == []
    # 조사·문장부호가 조금 달라도 지문으로 봄
    assert (
        mission_codes("TUE", question=material.replace("지나갔어.", "지나갔어!") + " 따져 보자.")
        == []
    )
    assert mission_codes("TUE", question="그림책 속 고양이와 내 경험을 비교해 보자.") == [
        "MATERIAL_MISSING"
    ]
    story = "“길을 잃은 아이가 친구의 조언을 듣고 다시 길을 찾았어요.”"
    assert mission_codes("TUE", question=f"{material} 그날 읽던 이야기: {story} 견줘 보자.") == []


def test_math_answer_must_not_be_a_number_in_material() -> None:
    """지문의 수(30·45·60cm)가 그대로 최종 답이면 문제 글에 답이 보여 LEAK이 되풀이돼 따로 알림."""
    from tests.theme_draft.fixtures import GeneratedAnswerKey

    key = GeneratedAnswerKey(choiceIds=None, assignments=None, finalAnswer="60cm")
    assert "MATERIAL_ANSWER" in mission_codes("THU", answerKey=key)
    assert checks.material_numbers("첫째 30cm, 둘째 4.5m, 셋째 2/7") == ["30", "4.5", "2/7"]
    extra = prompts.mission_extra(valid_theme(), "THU", 3, [])
    assert "지문에 나온 수(최종 답이 되면 안 됨, 이 수로 계산해 새 값을 구함): 30, 45, 60" in extra


def test_material_rules_from_final_failures() -> None:
    """확정 코드 40건 실패 원인: 수학 지문 조건 부족·모순, 지문이 수사 뒤 회고, 문학 성취기준인데
    목격담."""
    plan = prompts.PLAN_SYSTEM
    assert "필요한 조건(개수·모양·방향·배치·단위)을 빠짐없이" in plan
    assert "수사를 마친 뒤의 회고·나중에 알게 된 일" in plan
    assert "특정한 글 종류(문학 작품·시·이야기·안내문·광고·면담 기록 등)" in plan
    # #782 미션 방식: 부탁 날 지문은 돕는 사람의 일 자료라 사건 글이 아니어도 됨
    assert "수사 날은 helper가 가진 증거의 내용이다" in plan
    rules = " ".join(prompts.fix_rules(valid_theme(), "MON.missionMaterial"))
    assert "수사를 마친 뒤의 회고 금지" in rules


# ---------------------------------------------------------------- 할 수 없는 활동 이름(ACT_NAME,
# 사용자 결정 2026-11-19)과 웹 '오늘 장면' 대비 검사
def test_act_names_catch_commands_not_material_words() -> None:
    """실측에서 시킨 말은 잡고, 자료로 나온 말·생각 부분(검색어 만들기)은 잡지 않는다."""
    caught = {
        "같이 발표 글 써 볼래?": ["발표"],
        "친구들에게 알릴 발표 글을 두세 문장으로 써 봐.": ["발표"],
        "흙길 흔적에 신발 자국 두 갈래도 있어. 같이 묶어 발표해 볼래?": ["발표"],
        "어울리는 목소리와 몸짓을 괄호에 넣어 한 문장으로 써 줘.": ["목소리·몸짓 넣어 쓰기"],
        "두 원을 컴퍼스로 그릴 때 구할 것과 그리는 순서를 써 줘.": ["그리기"],
        "이 자료를 꺾은선그래프로 나타내고 차이를 구해.": ["그래프로 나타내기"],
        "뜻에 맞게 끊어 읽을 곳에 /를 넣어 봐.": ["소리 내어·끊어 읽기"],
        "자료를 찾으려면 검색해 봐야 해.": ["검색하기"],
        "두 의견을 비교해 토의에 보탤 글을 써 보자.": ["토의·토론 글"],
    }
    for text, names in caught.items():
        assert checks.act_names(text) == names, text
    passed = [
        "사장님이 본 고양이 움직임을 두 문장으로 정리해 예린이에게 알려 줘.",
        "면담 기록을 읽고 이어서 물을 말을 써 봐.",  # 자료로 나온 면담
        "더 잘 찾을 새 검색어를 만들어 쓰고 까닭을 설명해 줘.",  # 6국06-01의 생각 부분
        "그래프로 나타낸 자료를 보고 가장 많은 날을 찾아 써.",  # 주어진 그래프 읽기
        "반지름이 몇 cm여야 하는지 구하고 까닭을 써.",
        "연못 가에서 들은 소리를 정리해 봐.",
    ]
    for text in passed:
        assert checks.act_names(text) == [], text


def act_mission(question: str, material: str | None = None) -> list[str]:
    from app.mission_draft.models import Draft, MissionDraftRequest
    from tests.theme_draft.fixtures import DAY_TYPES, mission_draft
    from tests.theme_draft.helpers import request_body

    theme = valid_theme()
    if material is not None:
        theme = day_with(theme, "TUE", missionMaterial=material)
    req = MissionDraftRequest.model_validate(
        {**request_body()["missions"][list(DAY_TYPES).index("TUE")], "gradeMin": 3, "gradeMax": 3}
    )
    draft = Draft.model_validate(mission_draft(DAY_TYPES["TUE"], question=question).model_dump())
    return checks.mission_act_names(theme, req, draft)


def test_mission_with_act_name_is_regenerated_but_material_words_are_story() -> None:
    material = valid_theme()["days"][1]["missionMaterial"]
    assert act_mission(f"{material} 이웃에게 전할 발표 글을 두 문장으로 써 봐.") == ["발표"]
    assert act_mission(f"{material} 할머니가 본 모습을 두 문장으로 정리해 줘.") == []
    # 지문(이야기 속 사실)의 '발표할'은 시키는 말이 아님
    story = "지호의 메모: 보리는 내일 발표할 그림 자료 옆을 지나 마을 길로 달려 나갔다."
    assert act_mission(f"{story} 보리가 한 일을 차례대로 정리해 봐.", material=story) == []


def test_hook_act_name_and_clue_value_are_field_fixed() -> None:
    """수사 연결 문장(오늘 장면에서 학생이 읽는 대화 마지막 줄): 할 수 없는 활동 이름·그날 단서
    결론이면 그 칸만 고쳐 씀."""
    acted = day_with(
        valid_theme(), "MON", missionHook="지호 일지에 보리 얘기도 있어. 같이 발표 글 써 볼래?"
    )
    bad = checks.check_theme(acted, 3)
    assert codes(bad) == ["ACT_NAME"]
    assert list(checks.fix_targets(bad)) == ["MON.missionHook"]
    early = day_with(valid_theme(), "MON", missionHook="일지에 젖음 표시도 있어. 같이 살펴볼래?")
    bad = checks.check_theme(early, 3)
    assert codes(bad) == ["CLUE_EARLY"]
    assert list(checks.fix_targets(bad)) == ["MON.missionHook"]


def test_rewritten_hook_with_act_name_is_dropped() -> None:
    from app.mission_draft.models import Draft
    from tests.theme_draft.fixtures import mission_draft

    draft = Draft.model_validate(mission_draft("ANALYZE").model_dump())
    theme = valid_theme()
    assert "ACT_NAME" in codes(
        checks.hook_problems(theme, "MON", "일지에 보리 얘기도 있어. 같이 발표해 볼래?", draft, 12)
    )
    assert (
        checks.hook_problems(theme, "MON", "일지에 보리 얘기도 있어. 같이 정리해 볼래?", draft, 12)
        == []
    )


def test_prompts_ask_thinking_part_not_activity_name() -> None:
    assert "그 이름으로 시키지 않는다" in prompts.TEXT_ONLY
    assert "끊어 읽을 곳·띄어 읽기 표시로" not in prompts.TEXT_ONLY  # 11-11 괄호를 바꿈
    assert prompts.HOOK_ACT_RULE in prompts.PLAN_SYSTEM
    assert prompts.HOOK_ACT_RULE in prompts.fix_rules(valid_theme(), "MON.missionHook")
