"""#782 미션 방식(사용자 결정 2026-11-20 "세 가지 섞기"·"그날 장소 사람", 기준안 — 확인 전).

- 요일마다 그날 장소 사람(helper)이 있고, 미션이 이야기에 들어오는 길은 둘: ASK 부탁(그 사람의 일을
  도와주면 본 것을 알려 줌), INVESTIGATE 수사(그 사람이 가진 증거를 읽고 따짐). 함께 발견은 뺐다
  (사용자 결정 2026-11-20 "A+C", 40개 측정에서 함께 발견 테마 실패 9/18)
- 코드가 줄거리 전에 정함: 증거 종류에 맞는 방식만, 수사는 따지기 성취기준 + 서술·논술 날만
- 부탁 날은 증거가 문제 뒤 단서로 나오므로 대화·미션·그림·살펴보기에 미리 보여 주지 않음
- 예전 저장본(missionWay 없음)은 수사로 읽음
"""

import random
from typing import Any

from app.config import get_settings
from app.mission_draft.models import Draft
from app.theme_draft import checks, prompts
from app.theme_draft.models import GeneratedDay, ThemeDraftRequest
from tests.theme_draft.fixtures import DISCOVERY, HELPER, dialogue, mission_draft, valid_theme
from tests.theme_draft.helpers import request_body

GRADE = 3
READING = ["4국02-04"]  # 수사 후보가 되는 따지기 성취기준(INVESTIGATE_STANDARDS)


def _draft(thinking_type: str = "ANALYZE") -> Draft:
    return Draft.model_validate(mission_draft(thinking_type).model_dump())


def theme_with_way(day: str, way: str) -> dict[str, Any]:
    theme = valid_theme()
    checks.theme_day(theme, day)["missionWay"] = way
    return theme


# ---------------------------------------------------------------- 배정
def test_old_save_without_way_reads_as_investigate() -> None:
    assert checks.mission_way({}) == checks.INVESTIGATE
    assert checks.mission_way({"missionWay": "엉뚱함"}) == checks.INVESTIGATE
    assert checks.mission_way({"missionWay": checks.FOLLOW}) == checks.FOLLOW
    old = {k: v for k, v in valid_theme()["days"][0].items() if k != "helper"}
    assert GeneratedDay.model_validate(old).helper == ""


def _plan(*kinds: str) -> dict[str, dict[str, str | None]]:
    return {
        d: {"kind": k, "medium": "일지" if k == "RECORD" else None}
        for d, k in zip(checks.DAYS, kinds, strict=True)
    }


def test_way_plan_fits_evidence_and_never_repeats() -> None:
    """방식은 그날 증거 종류에 맞는 것만(수사는 목격·기록 + 따지기 성취기준·서술·논술 날),
    연달아 같은 방식이 가장 적게 증거 배정의 요일 순서를 맞춤(한 주 구성은 그대로)."""
    days = [
        ("MON", READING, "NARRATIVE"),
        ("TUE", ["4수01-05"], "NARRATIVE"),  # 읽기 성취기준 아님
        ("WED", READING, "CHOICE"),  # 서술·논술 아님
        ("THU", READING, "ESSAY"),
        ("FRI", [], "NARRATIVE"),  # 성취기준 없음
    ]
    seen: set[str] = set()
    for mix in checks.EVIDENCE_MIXES:
        for seed in range(60):
            kinds = list(mix)
            random.Random(seed).shuffle(kinds)
            before = _plan(*kinds)
            ways, plan = checks.mission_way_plan(days, before, random.Random(seed))
            order = [ways[d] for d in checks.DAYS]
            assert all(checks.way_fits(ways[d], plan[d]["kind"]) for d in checks.DAYS)
            for day in ("TUE", "WED", "FRI"):
                assert ways[day] != checks.INVESTIGATE
            # 한 주 증거 구성·매체는 그대로(요일 순서만 바뀜)
            assert sorted(s["kind"] for s in plan.values()) == sorted(mix)
            assert all((s["medium"] is not None) == (s["kind"] == "RECORD") for s in plan.values())
            seen |= set(order)
    assert seen == set(checks.MISSION_WAYS)  # 두 가지가 모두 나옴
    same = [checks.mission_way_plan(days, _plan(*mix), random.Random("씨앗")) for _ in range(2)]
    assert same[0] == same[1]
    assert not checks.way_fits(checks.INVESTIGATE, "TRACE")
    assert checks.MISSION_WAYS == (checks.FOLLOW, checks.INVESTIGATE)  # 함께 발견 없음
    assert checks.mission_way({"missionWay": "TOGETHER"}) == checks.INVESTIGATE  # 예전 값은 수사로


def test_way_plan_allows_repeat_only_when_evidence_leaves_no_choice() -> None:
    """흔적이 없는 종류(시간 탐정: 목격 4·기록 1)는 수사를 못 하는 주에 부탁이 연달아 나올 수밖에
    없음 — 그래도 증거에 안 맞는 방식은 고르지 않음."""
    days = [(d, ["4수01-05"], "NARRATIVE") for d in checks.DAYS]
    plan = _plan("SIGHTING", "SIGHTING", "RECORD", "SIGHTING", "SIGHTING")
    ways, fitted = checks.mission_way_plan(days, plan, random.Random(1))
    assert all(checks.way_fits(ways[d], fitted[d]["kind"]) for d in checks.DAYS)
    assert list(ways.values()).count(checks.FOLLOW) >= 4


def test_request_ways_are_stable_and_told_in_plan_prompt() -> None:
    request = ThemeDraftRequest.model_validate(request_body())
    ways = prompts.mission_ways_for(request)
    assert list(ways) == list(checks.DAYS)
    assert ways == prompts.mission_ways_for(request)  # 다시 생성해도 같음
    plan = prompts.evidence_plan_for(request)
    assert all(checks.way_fits(ways[d], plan[d]["kind"]) for d in checks.DAYS)  # 증거와 맞는 짝
    user = prompts.plan_user(request, [])
    assert "미션 방식 배정(코드가 정함" in user
    for day, way in ways.items():
        assert f"- {day}({prompts.DAY_KO[day]}): {prompts.WAY_KO[way]}({way})" in user
    assert "helper: 그날 장소 사람 호칭" in prompts.PLAN_SYSTEM
    # #971: 부탁 날 일 → 사람 → 쓰임 순서는 뺌, 미션 방식은 이어 가기·수사
    assert "늘 하는 사람(helper" not in prompts.PLAN_SYSTEM
    assert all(f"  - {w}" in prompts.PLAN_SYSTEM for w in ("이어 가기:", "수사:"))
    assert "다음 행동 배정(이어 가기 날만" in user and "지문 글자 수" in user
    assert "함께 발견" not in prompts.PLAN_SYSTEM and "함께 발견" not in prompts.DIALOGUE_SYSTEM


# ---------------------------------------------------------------- 돕는 사람 칸
def test_helper_is_required_and_length_checked() -> None:
    theme = valid_theme()
    assert checks.check_theme(theme, GRADE) == []
    checks.theme_day(theme, "TUE")["helper"] = ""
    assert any(r.startswith("REQUIRED") and "helper" in r for r in checks.check_theme(theme, GRADE))
    theme = valid_theme()
    checks.theme_day(theme, "TUE")["helper"] = "가" * (checks.TEXT_MAX["helper"] + 1)
    assert any(r.startswith("LENGTH") and "helper" in r for r in checks.check_theme(theme, GRADE))


def test_helper_may_speak_and_short_name_is_restored() -> None:
    def check(theme: dict, lines: list[dict[str, str]]) -> list[str]:
        return checks.check_dialogue(
            theme,
            "MON",
            {"lines": lines},
            _draft(checks.DAY_TYPE["MON"]),
            GRADE,
            get_settings().followup_example_overlap_chars,
        )

    lines = [x.model_dump() for x in dialogue().lines]
    by_helper = [{"speaker": HELPER["MON"], "text": lines[0]["text"]}, *lines[1:]]
    assert check(valid_theme(), by_helper) == []
    # 다른 날 돕는 사람은 그날 화자가 아님
    by_other = [{"speaker": HELPER["TUE"], "text": lines[0]["text"]}, *lines[1:]]
    assert [r.split(" ")[0] for r in check(valid_theme(), by_other)] == ["SPEAKER"]
    # '공원 관리인'을 '관리인'으로 줄여 쓰면 그날 돕는 사람 이름으로 되돌림
    short = {"lines": [{"speaker": "관리인", "text": lines[0]["text"]}, *lines[1:]]}
    assert checks.full_speakers(valid_theme(), short, "MON")["lines"][0]["speaker"] == HELPER["MON"]
    assert checks.full_speakers(valid_theme(), short)["lines"][0]["speaker"] == "관리인"


# ---------------------------------------------------------------- 방식대로 쓰는 재료
def test_ask_day_hides_evidence_before_mission() -> None:
    """부탁 날 증거는 문제를 마친 뒤 단서로 나오므로 대화·미션 재료에 미리 주지 않음."""
    for way in (checks.FOLLOW,):
        theme = theme_with_way("MON", way)
        user = prompts.dialogue_user(theme, "MON", _draft("ANALYZE"), GRADE, [])
        assert f"미션 방식: {prompts.WAY_KO[way]}({way})" in user
        assert f"오늘 그날 장소 사람(화자로 써도 됨): {HELPER['MON']}" in user
        assert DISCOVERY["MON"] not in user
        story = prompts.story_text(theme, "MON", GRADE)
        assert f"- 오늘 그날 장소 사람: {HELPER['MON']}" in story
        assert "오늘 찾은 증거" not in story and DISCOVERY["MON"] not in story
        assert f"오늘 미션 방식: {prompts.WAY_KO[way]}" in story


def test_investigate_day_keeps_evidence() -> None:
    theme = theme_with_way("MON", checks.INVESTIGATE)
    user = prompts.dialogue_user(theme, "MON", _draft("ANALYZE"), GRADE, [])
    assert f"오늘 찾은 증거(② 재료, 이 증거 그대로): {DISCOVERY['MON']}" in user
    story = prompts.story_text(theme, "MON", GRADE)
    # #782 설계 v12: 문제에는 지문만(지문에 없는 증언을 준다고 쓰지 않음, MISSION_TESTIMONY)
    assert "- 오늘 찾은 증거(문제 앞 대화에서 보여 줌, 문제에는 지문만" in story
    assert f"MISSION_TESTIMONY): {DISCOVERY['MON']}" in story
    assert "오늘 미션 방식: 수사" in story


def test_mission_image_draws_helper_not_evidence_on_ask_day() -> None:
    ask = prompts.mission_image_prompt(
        theme_with_way("MON", checks.FOLLOW), "MON", _draft("ANALYZE"), []
    )
    assert "Today's evidence" not in ask
    assert f"Today's person (Korean): {HELPER['MON']}" in ask
    investigate = prompts.mission_image_prompt(
        theme_with_way("MON", checks.INVESTIGATE), "MON", _draft("ANALYZE"), []
    )
    assert f"Today's evidence (Korean): {DISCOVERY['MON']}" in investigate
    assert "Today's person" not in investigate


def test_review_inputs_carry_way_and_helper() -> None:
    brief = prompts.story_brief(theme_with_way("MON", checks.FOLLOW), "MON")
    assert brief["missionWay"] == "이어 가기(FOLLOW)" and brief["helper"] == HELPER["MON"]
    assert "missionWay대로 본다" in prompts.MISSION_REVIEW_SYSTEM
    assert "helper가 있으면" in prompts.IMAGE_REVIEW_SYSTEM
    assert "helper가 있으면" in prompts.MOTION_SYSTEM
    image = prompts.image_review_user(
        valid_theme(),
        "장면",
        ids=checks.MISSION_IMAGE_REVIEW_IDS,
        has_mungchi=True,
        shows_target=False,
        question="문제",
        helper=HELPER["MON"],
    )
    assert f'"helper": "{HELPER["MON"]}"' in image


# ---------------------------------------------------------------- 방식 흐름 검사(작은 생성
# r782-ways-rd3에서 읽어 찾은 문제 4가지, 사용자 결정 2026-11-20 "이 설계대로")
def way_theme(day: str, way: str, **fields: Any) -> dict[str, Any]:
    theme = theme_with_way(day, way)
    checks.theme_day(theme, day).update(fields)
    return theme


def flow_codes(theme: dict[str, Any]) -> list[str]:
    return sorted(r.split(" ")[0] for r in checks.check_theme(theme, GRADE))


def test_scene_note_hides_evidence_on_ask_days() -> None:
    """실측: 장면 메모의 '끌림 자국'이 문제 전 대화로 샘."""
    note = "안내 담당자가 안내문을 정리하고 지호가 바닥의 자국을 살펴본다"
    bad = checks.check_theme(way_theme("TUE", checks.FOLLOW, sceneNote=note), GRADE)
    assert "EVIDENCE_EARLY" in [r.split(" ")[0] for r in bad]
    assert "TUE.sceneNote" in checks.fix_targets(bad)
    assert "EVIDENCE_EARLY" not in flow_codes(way_theme("TUE", checks.INVESTIGATE, sceneNote=note))
    rules = " ".join(
        prompts.fix_rules(way_theme("TUE", checks.FOLLOW, sceneNote=note), "TUE.sceneNote")
    )
    assert "흔적·자국·증거와 다음 행동" in rules


# #782 설계 v13: 수사 날 지문은 그때 직접 본 사람의 증언이고 그날 단서 내용(월 '젖어
# 있었어')이 들어감
TESTIMONY = (
    "공원 관리인의 일지: 그때 내가 본 보리 발자국은 젖어 있었다. 보리는 마을 길로 달려 나갔다."
)


def test_hook_must_not_ask_helpers_own_mind() -> None:
    """실측: 수사 날 카페 주인이 '주인의 생각을 추론해 볼래?'."""
    for hook in (
        "이 조각을 보고 내 생각을 추론해 볼래?",
        "접시를 살펴 관리인의 생각을 추론해 볼래?",
    ):
        theme = way_theme("MON", checks.INVESTIGATE, missionHook=hook, missionMaterial=TESTIMONY)
        bad = checks.check_theme(theme, GRADE)
        assert [r.split(" ")[0] for r in bad] == ["HOOK_SELF"], hook
        assert list(checks.fix_targets(bad)) == ["MON.missionHook"]
    ok = "관리인 일지에 적힌 글쓴이의 생각을 추론해 볼래?"  # 증거 속 사람의 생각은 됨
    ok_theme = way_theme("MON", checks.INVESTIGATE, missionHook=ok, missionMaterial=TESTIMONY)
    assert flow_codes(ok_theme) == []


def test_clue_rules_differ_by_way_in_plan_prompt() -> None:
    plan = prompts.PLAN_SYSTEM
    assert "clue는 그날 미션 방식대로 한 줄 말로 쓴다" in plan
    assert "'고마워!' 같은 앞말은 붙이지 않는다" in plan
    assert "EVIDENCE_EARLY" in plan and "HOOK_SELF" in plan and "CLUE_WAY" not in plan
    # #971: 부탁 날 약속 줄 대신 보답 약속 없음(다음 행동은 지문에 나오므로 대화가 말해도 됨)
    assert "ASK_PROMISE" not in prompts.DIALOGUE_SYSTEM
    assert "NEXT_EARLY" not in prompts.DIALOGUE_SYSTEM and "NEXT_PROMISE" in prompts.DIALOGUE_SYSTEM


# ---------------------------------------------------------------- r782-ways-rd4를 읽고 찾은 문제
def test_refit_turns_mismatched_day_into_ask() -> None:
    theme = theme_with_way("TUE", checks.INVESTIGATE)
    theme["evidencePlan"] = _plan("SIGHTING", "TRACE", "SIGHTING", "TRACE", "RECORD")
    assert checks.refit_ways(theme) == ["TUE"]  # 수사 날이 흔적이 됨 → 부탁
    assert checks.mission_way(checks.theme_day(theme, "TUE")) == checks.FOLLOW


def helper_codes(theme: dict[str, Any]) -> list[str]:
    return sorted({r.split(" ")[0] for r in checks.check_theme(theme, GRADE)})


def test_helper_differs_each_day_and_is_not_a_character() -> None:
    """실측: 등장인물(떡집 사장님)이 매일 돕는 사람이라 같은 사람이 사흘 '도와주면 알려 줄게'."""
    theme = valid_theme()
    checks.theme_day(theme, "WED")["helper"] = HELPER["MON"]  # 월요일과 같은 사람
    checks.theme_day(theme, "WED")["sceneNote"] = f"{HELPER['MON']}이 화분을 정리하는 장면"
    bad = checks.check_theme(theme, GRADE)
    assert {r.split(" ")[0] for r in bad} == {"HELPER_SAME"}
    # 그날 돕는 사람과 옛 호칭이 나오는 칸만, 그 요일만 고쳐 씀
    assert sorted(checks.fix_targets(bad)) == ["WED.helper", "WED.sceneNote"]
    # 다음 날 오늘 온 까닭에 바뀔 호칭이 있으면 그 칸도(#782 설계 v7)
    checks.theme_day(theme, "THU")["dayStep"] = f"{HELPER['MON']} 말을 듣고 골목 안쪽으로 왔어."
    targets = checks.fix_targets(checks.check_theme(theme, GRADE))
    assert sorted(targets) == ["THU.dayStep", "WED.helper", "WED.sceneNote"]
    character = valid_theme()
    checks.theme_day(character, "TUE")["helper"] = "지호"  # 등장인물
    assert helper_codes(character) == ["HELPER_SAME"]
    rules = " ".join(prompts.fix_rules(theme, "WED.helper"))
    assert HELPER["TUE"] in rules and "지호" in rules and "새 사람" in rules


def test_helper_problem_on_three_days_regenerates_plan() -> None:
    theme = valid_theme()
    for day in ("TUE", "WED", "THU"):
        checks.theme_day(theme, day)["helper"] = HELPER["MON"]
    bad = checks.check_theme(theme, GRADE)
    assert [r.split(" ")[0] for r in bad] == ["HELPER_WEEK"]
    assert not checks.fix_targets(bad)  # 칸 고쳐 쓰기 대상 아님(줄거리 다시)


def test_monday_has_no_yesterday_unless_intro_says_so() -> None:
    """실측: 첫날 대화 '어제 빈손을 알아챘다'가 시작 이야기('공연이 끝난 직후')와 어긋나 실패."""
    theme = valid_theme()
    checks.theme_day(theme, "MON")["dayStep"] = "어제 사건이 난 길로 다시 왔어."
    bad = checks.check_theme(theme, GRADE)
    assert [r.split(" ")[0] for r in bad] == ["DAY1_TIME"]
    assert list(checks.fix_targets(bad)) == ["MON.dayStep"]
    night = {**theme, "intro": "밤마다 텐트 밖에서 소리가 났어요. 구조대 뭉치가 출동해요."}
    assert "DAY1_TIME" not in helper_codes(night)
    # 대화도 같은 검사(그 요일 대화만 다시), 화~금은 '어제'가 정상
    lines = [
        {"speaker": "지호", "text": "어제 보리를 잃어버렸어."},
        {"speaker": "뭉치", "text": "찾자!"},
    ]
    lines = lines + [{"speaker": "지호", "text": "응!"}, {"speaker": "뭉치", "text": "가 보자!"}]
    for day, want in (("MON", ["DAY1_TIME"]), ("TUE", [])):
        bad = checks.check_dialogue(
            valid_theme(),
            day,
            {"lines": lines},
            _draft(checks.DAY_TYPE[day]),
            GRADE,
            get_settings().followup_example_overlap_chars,
        )
        assert [r.split(" ")[0] for r in bad] == want, day
    user = prompts.dialogue_user(valid_theme(), "MON", _draft("ANALYZE"), GRADE, [])
    assert "시작 이야기(첫날이라 여기서 이어짐, 어제 한 일 없음)" in user
    assert "오늘 온 까닭(시작 이야기의 사건에서 이어짐" in user
    assert "시작 이야기(" not in prompts.dialogue_user(
        valid_theme(), "TUE", _draft("EVALUATE"), GRADE, []
    )


def test_hook_self_needs_a_guessing_word() -> None:
    """실측 오탐: 돌아보기 날 '내 생각이 바뀐 까닭을 정리해 줄래?'(그 사람이 쓴 글 정리)는 됨."""
    ok = "내 생각이 바뀐 까닭을 문장으로 정리해 줄래?"
    assert "HOOK_SELF" not in helper_codes(way_theme("FRI", checks.FOLLOW, missionHook=ok))
    bad = "내 생각을 짐작해 볼래?"
    assert "HOOK_SELF" in helper_codes(way_theme("FRI", checks.FOLLOW, missionHook=bad))


def test_code_adjust_rewrites_hook_and_material_when_way_changes() -> None:
    """코드가 증거를 옮겨 수사 날이 흔적이 되면 부탁으로 바꾸고 그날 할 일·지문도 고쳐 씀."""
    from app.theme_draft.nodes.plan import code_adjust

    theme = checks.fill_rules_out(theme_with_way("TUE", checks.INVESTIGATE))
    theme["evidencePlan"] = _plan("TRACE", "TRACE", "SIGHTING", "SIGHTING", "RECORD")
    checks.theme_day(theme, "TUE")["evidence"] = {"kind": "TRACE", "when": "그날 오후"}
    targets = code_adjust(theme)
    assert checks.mission_way(checks.theme_day(theme, "TUE")) == checks.FOLLOW
    for key in ("missionHook", "missionMaterial"):
        assert any(r.startswith("WAY_FIX TUE") for r in targets[f"TUE.{key}"])


# ---------------------------------------------------------------- r782-ways-rd5를 읽고 찾은 문제
# (사용자 결정 2026-11-20 "서술·논술·성취기준과 잘 맞게", "단서도")
def test_investigate_only_on_judging_standards() -> None:
    """수사(증거 따지기)는 사실·의견·출처·매체 신뢰성 날만. 요약·추론 날은 지문이 일반론이 됨."""
    assert checks.INVESTIGATE_STANDARDS == {"4국02-04", "4국02-05", "6국06-02"}
    for code in ("4국02-02", "4국02-03", "6국02-01", "6국02-02"):
        days = [(d, [code], "NARRATIVE") for d in checks.DAYS]
        for seed in range(20):
            ways, _ = checks.mission_way_plan(
                days,
                _plan("SIGHTING", "SIGHTING", "RECORD", "RECORD", "TRACE"),
                random.Random(seed),
            )
            assert checks.INVESTIGATE not in ways.values(), code


def negative_theme(clue: str) -> dict[str, Any]:
    """월요일 RULE을 시험용 특징 '바닥'(모래·흙·나무·돌, 허용 값 셋 → 빠지는 값 나무)으로."""
    theme = valid_theme()
    theme["features"].append(
        {
            "name": "바닥",
            "standardCode": None,
            "values": [
                {"candidate": "놀이터", "value": "모래"},
                {"candidate": "텃밭", "value": "흙"},
                {"candidate": "창고", "value": "나무"},
                {"candidate": "정자", "value": "돌"},
            ],
        }
    )
    checks.theme_day(theme, "MON").update(
        clue=clue, condition={"kind": "RULE", "feature": "바닥", "allowed": ["모래", "흙", "돌"]}
    )
    return checks.fill_rules_out(theme)


def test_negative_clue_names_the_excluded_value() -> None:
    """허용 값이 둘 이상이면 'A나 B나 C였어' 대신 '나무는 아니었어'(#782 설계 v3, 사용자 결정
    2026-11-21: 직접 본 사람은 하나만 봄 — 늘어놓으면 CLUE_TEXT)."""
    neg = negative_theme("보리 발자국이 찍힌 바닥은 나무는 아니었어!")
    assert "CLUE_TEXT" not in helper_codes(neg)
    day = checks.theme_day(neg, "MON")
    assert day["condition"]["excluded"] == ["나무"] and checks.clue_says(day) == ["나무"]
    # 늘어놓으면 CLUE_TEXT(전에는 통과)
    listed = negative_theme("보리 발자국이 찍힌 바닥은 모래나 흙이나 돌이었어!")
    assert "CLUE_TEXT" in helper_codes(listed)
    # 부정 말 없이 빠지는 값만 쓰면 여전히 허용 밖 값
    wrong = negative_theme("보리 발자국이 찍힌 바닥은 나무였어!")
    assert "CLUE_TEXT" in helper_codes(wrong)
    # 부정형 날은 문제 전 글이 빠지는 값을 말하면 미리 말하기(CLUE_EARLY), 다음 날은 앞 요일 단서
    checks.theme_day(neg, "MON")["sceneNote"] = "보리가 나무 바닥 쪽으로 뛰어가는 장면"
    assert "CLUE_EARLY" in helper_codes(neg)
    assert checks.prev_values(neg, "TUE", "나무 바닥을 지나왔어") == ["나무"]
    rules = " ".join(prompts.fix_rules(neg, "MON.clue"))
    assert "빠지는 값 ['나무']" in rules and "부정으로" in rules
    assert "허용 밖 값 낱말" not in rules  # 빠지는 값(나무)은 부정형으로 써야 하는 낱말


def test_clue_and_material_rules_in_plan_prompt() -> None:
    plan = prompts.PLAN_SYSTEM
    assert "빠지는 값(그 특징 값 중 allowed 밖, 한두 개)을 부정으로 쓴다" in plan
    assert "부정형으로 말하는 빠지는 값만 됨" in plan
    assert "그 주 사건 이야기 글" in plan and "특정한 글 종류" in plan
    assert "말투·표현 방법 같은 배울 내용 자체는 특징이 아님" in plan
    assert "추론하기 성취기준이면" not in plan


# ---------------------------------------------------------------- r782-ways-rd6를 읽고 찾은 문제
def test_ask_discovery_is_internal_and_not_reviewed() -> None:
    """부탁 날 증거 발견 줄은 단서가 나오는 곳(문제 전에 안 보임) — 미리 말하기
    검사·글 검토에서 뺌(실측: 글 검토 ANSWER_HINT 10번 중 8번이 이 줄을 지적해 줄거리를 다시
    만들고 마감)."""
    theme = theme_with_way("MON", checks.FOLLOW)
    checks.theme_day(theme, "MON")["discovery"] = "보리 발자국 둘레가 젖음 그대로였어."
    assert "CLUE_EARLY" not in helper_codes(theme)
    inv = theme_with_way("MON", checks.INVESTIGATE)
    checks.theme_day(inv, "MON")["discovery"] = "보리 발자국 둘레가 젖음 그대로였어."
    assert "CLUE_EARLY" in helper_codes(inv)
    request = ThemeDraftRequest.model_validate(request_body())
    drafts = {d: _draft(checks.DAY_TYPE[d]) for d in checks.DAYS}
    import json

    days = json.loads(prompts.review_user(request, checks.fill_rules_out(theme), drafts, {}))[
        "days"
    ]
    assert days[0]["discovery"] == "" and days[1]["discovery"] == DISCOVERY["TUE"]
    assert "단서와 같은 내용은 결함이 아니다" in prompts.REVIEW_SYSTEM


def test_hook_must_not_name_traces_on_ask_days() -> None:
    """실측: '흔적이 남은 자리도 살필래?'처럼 할 일이 증거를 먼저 말함. 기록 낱말(영상·사진·메모)은
    매체 성취기준 날 할 일에 원래 들어가 보지 않음(40개 측정에서 44번 잘못 잡음)."""
    bad = "주민에게 전할 안전 글을 요약해 흔적이 남은 자리도 살필래?"
    theme = way_theme("THU", checks.FOLLOW, missionHook=bad)
    reasons = checks.check_theme(theme, GRADE)
    assert "EVIDENCE_EARLY" in [r.split(" ")[0] for r in reasons]
    assert "THU.missionHook" in checks.fix_targets(reasons)
    for ok in (
        "축제 안내 쪽지 문장을 같이 다듬어 줄래?",
        "골목 행사 안내의 말·글·영상을 비교해 표현 효과를 함께 정리해 줄래?",  # 매체 날
        "사진을 안전하게 나누는 새 안내를 같이 만들어 볼래?",
    ):
        assert "EVIDENCE_EARLY" not in helper_codes(way_theme("THU", checks.FOLLOW, missionHook=ok))
    # 수사 날은 증거를 같이 보는 날이라 됨
    assert "EVIDENCE_EARLY" not in helper_codes(
        way_theme("THU", checks.INVESTIGATE, missionHook=bad)
    )


# ---------------------------------------------------------------- 40개 측정 r782-final40에서
# 찾은 문제(사용자 결정 2026-11-20 "A+C")
def test_negative_clue_must_say_what_was_seen_was_not_the_value() -> None:
    """#782 설계 v8: '나무가 없었어'·'깔려 있지 않았어'·'안 지났어'처럼 본 것 없이 없었다고만 하면
    글 검토가 "찾지 못한 것만으로 뺌"으로 잡음(3·4·5차 글 검토 CLUE_LOGIC 87번 중 47번) →
    CLUE_TEXT로 '본 것이 그 값이 아니었다' 꼴로 다시 씀. (11-20에는 이 꼴을 부정형으로 받았음)"""
    for clue in (
        "보리 발자국이 찍힌 바닥은 나무가 없었어!",
        "보리 발자국이 찍힌 바닥에 나무는 깔려 있지 않았어!",
        "보리는 나무 바닥은 안 지났어!",
    ):
        bad = [r for r in checks.check_theme(negative_theme(clue), GRADE) if "CLUE_TEXT" in r]
        assert bad and "본 것 없이" in bad[0], clue
    ok = "보리 발자국이 찍힌 바닥은 나무는 아니었어!"
    assert "CLUE_TEXT" not in helper_codes(negative_theme(ok))
    assert not checks.NEG_WORDS.search("안쪽 바닥은 나무였어")
    # 값이 '…아님'이면 '…아니었어'도 같은 값
    assert checks.value_in_text("물가 아님", "손전등을 본 곳은 물가가 아니었어!")
    assert not checks.value_in_text("물가 아님", "손전등을 본 곳은 물가였어!")
