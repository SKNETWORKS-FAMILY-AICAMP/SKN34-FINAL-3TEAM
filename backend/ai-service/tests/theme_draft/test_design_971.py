"""#971(사용자 결정 2026-11-24 "나·A", 같은 날 아침 재설계 "애초에 다 이상한데"): 부탁 날 → 이어
가기 날.

- 미션 지문은 그 주 사건 이야기, 한 문제에 성취기준 활동 하나(번호로 나누지 않음 NUMBERED_ASK,
  생각 유형 요소는 한 문장에 THINK_ASK). 다음 행동(갈 곳·만날 사람·쓴 글을 받을 사람)은 지문 속
  사건의 한 부분으로 나오고(MATERIAL_NEXT) 단서는 거기서 나옴. 응답 단서 앞에 다음 행동
  이름표(labeled_clue). 답으로 고르게 하던 검사(nextOthers·MATERIAL_CHOICE·NEXT_TOLD·NEXT_EARLY·
  EXAMPLE_NEXT·EXAMPLE_CHOICE·NEXT_ASKED·READER_EARLY·USE_MISSING)는 뺌
- 다음 행동 종류는 코드가 정함(next_kind_for), 칸은 모델이 씀(nextTarget)
- 줄거리 검사 NEXT_SOURCE·MATERIAL_NEXT·REQUIRED nextTarget, 단서 말투 CLUE_PLAIN, 대화 검사
  NEXT_PROMISE·SELF_NAME
- 지문·문제 글 학년별 상한(MATERIAL_MAX, theme_question_max_chars)
- 예전 부탁 날('ASK')은 이어 가기로 읽고, 다음 행동 칸이 없으면 부분 다시 생성에서 미션을 막음
"""

import copy
from typing import Any

from app.config import get_settings
from app.mission_draft.models import Draft, MissionDraftRequest
from app.theme_draft import checks, prompts, regen
from app.theme_draft.models import GeneratedDay, ThemeDraftRequest
from app.theme_draft.nodes.mission import EXAMPLE_ONLY
from app.theme_draft.nodes.plan import SOFT_THEME
from tests.theme_draft.fixtures import (
    DAY_TYPES,
    HELPER,
    MATERIAL,
    NEXT,
    mission_draft,
    valid_theme,
)
from tests.theme_draft.helpers import request_body

GRADE = 3
KINDS = {"MON": checks.PLACE, "WED": checks.PERSON, "THU": checks.PLACE, "FRI": checks.PERSON}


def follow_theme(**fields: dict[str, Any]) -> dict[str, Any]:
    """기본 요청 배정대로 이어 가기 날·다음 행동 종류를 넣은 줄거리(화요일은 수사)."""
    theme = checks.fill_rules_out(valid_theme())
    for d in theme["days"]:
        if d["day"] in KINDS:
            d.update(missionWay=checks.FOLLOW, nextKind=KINDS[d["day"]])
        else:
            d.update(missionWay=checks.INVESTIGATE, nextTarget="")
    for day, changes in fields.items():
        checks.theme_day(theme, day).update(changes)
    return theme


def codes(bad: list[str]) -> list[str]:
    return [r.split(" ")[0] for r in bad]


def theme_codes(theme: dict[str, Any]) -> list[str]:
    return codes(checks.check_theme(theme, GRADE))


# ---------------------------------------------------------------- 1. 방식·다음 행동 종류
def test_old_ask_reads_as_follow_and_kind_is_set_by_code() -> None:
    assert checks.mission_way({"missionWay": "ASK"}) == checks.FOLLOW
    assert checks.mission_way({}) == checks.INVESTIGATE  # 예전 저장본은 수사 그대로
    assert checks.next_kind_for(["4국03-04"], "TRACE") == checks.READER  # 쓰기 성취기준
    assert checks.next_kind_for(["4국02-02"], "TRACE") == checks.PLACE
    assert checks.next_kind_for(["4수01-03"], "SIGHTING") == checks.PERSON
    assert checks.next_kind_for(["4국05-01"], "RECORD") == checks.PERSON
    # 칸이 없는 예전 저장본·수사 날은 다음 행동 없음(검사·지시 안 함)
    assert checks.next_kind({"missionWay": "ASK"}) is None
    assert checks.next_kind({"missionWay": checks.INVESTIGATE, "nextKind": "PLACE"}) is None


def test_request_kinds_are_told_in_plan_prompt_with_material_limit() -> None:
    request = ThemeDraftRequest.model_validate(request_body())
    kinds = prompts.next_kinds_for(request)
    assert kinds == KINDS  # 화요일(수사)은 없음
    user = prompts.plan_user(request, [])
    assert "다음 행동 배정(이어 가기 날만, 코드가 정함" in user
    assert "- MON(월): 갈 곳(PLACE)" in user and "- WED(수): 만날 사람(PERSON)" in user
    assert f"지문 글자 수(missionMaterial, 공백 포함): {checks.MATERIAL_MAX[3]}자 이내" in user
    assert "국어 부탁 날 그날 성취기준의 일" not in user  # 부탁 날 일 틀은 뺌


# ---------------------------------------------------------------- 2. 줄거리 검사
def test_follow_theme_passes_and_next_target_is_required() -> None:
    assert checks.check_theme(follow_theme(), GRADE) == []
    bad = checks.check_theme(follow_theme(MON={"nextTarget": ""}), GRADE)
    assert bad == ["REQUIRED MON.nextTarget"]
    assert checks.fix_targets(bad) == {"MON.nextTarget": bad}


def test_next_source_rejects_cast_helper_candidate_value_and_same_place() -> None:
    cases = {
        "지호": "등장인물",  # 이야기 속 사람
        HELPER["WED"]: "그날 장소 사람과 같음",
        "창고 앞 아이": "후보 이름",  # 후보 '창고'
        "흙밭 아이": "특징 값 낱말",  # 특징 값 '흙'
    }
    for target, why in cases.items():
        bad = checks.check_theme(follow_theme(WED={"nextTarget": target}), GRADE)
        hit = [r for r in bad if r.startswith("NEXT_SOURCE WED")]
        assert hit and why in hit[0], (target, bad)
        assert "WED.nextTarget" in checks.fix_targets(hit)
    # 갈 곳이 그날 장소 이름뿐이면 새로 갈 곳이 아님
    same = follow_theme(MON={"nextTarget": "마을 길", "missionMaterial": MATERIAL["MON"]})
    assert "그날 장소 이름과 같음" in " ".join(checks.check_theme(same, GRADE))


def test_material_must_name_next_and_step_hook_may_name_it() -> None:
    """다음 행동은 지문 속 사건의 한 부분(MATERIAL_NEXT). 아침 재설계부터 오늘 온 까닭·할 일이
    말해도 됨(NEXT_EARLY 뺌 — 지문에 이미 나옴)."""
    bad = checks.check_theme(follow_theme(WED={"nextTarget": "우체부 아저씨"}), GRADE)
    assert "MATERIAL_NEXT" in codes(bad)
    assert "WED.missionMaterial" in checks.fix_targets(bad)
    said = follow_theme(
        MON={"dayStep": "빈 공터부터 살펴보러 왔어.", "missionHook": "공터 쪽 글을 같이 읽어 볼래?"}
    )
    assert "NEXT_EARLY" not in theme_codes(said)
    # 장소 이름에 이미 있는 말은 다음 행동 낱말로 보지 않음('떡집 뒷문'이면 '뒷문'만)
    d = {"place": "골목 떡집", "nextTarget": "떡집 뒷문을 본 이웃"}
    assert checks.next_words(d["nextTarget"], d["place"]) == ["뒷문"]
    assert checks.mentions_next(d, "떡집에 왔어") == []
    assert checks.mentions_next(d, "뒷문 쪽으로 가 보자") == ["뒷문"]


def test_material_is_shorter_by_grade() -> None:
    long = (
        MATERIAL["MON"] + " 바람이 불어 나뭇잎이 길 위로 흩어졌고 지호는 한참 동안 보리를 불렀다."
    )
    theme = follow_theme(MON={"missionMaterial": long})
    assert len(long) <= checks.TEXT_MAX["missionMaterial"]  # 예전 상한(150자) 안
    theme["grade"] = 3
    bad = [
        r for r in checks.check_theme(theme, GRADE) if r.startswith("LENGTH MON.missionMaterial")
    ]
    assert bad and bad[0].endswith(f"> {checks.MATERIAL_MAX[3]}")
    assert checks.text_max("MON.missionMaterial", theme) == checks.MATERIAL_MAX[3]
    del theme["grade"]  # 학년을 적지 않은 예전 저장본은 150자
    assert not [r for r in checks.check_theme(theme, GRADE) if r.startswith("LENGTH MON.")]
    assert get_settings().theme_question_max_chars == {3: 240, 4: 240, 5: 280, 6: 280}


# ---------------------------------------------------------------- 3. 단서 출처·이름표
def test_clue_is_labeled_with_next_target_only_on_follow_days() -> None:
    theme = follow_theme()
    public = checks.public_theme(theme)
    by_day = {d["day"]: d["clue"] for d in public["days"]}
    for day, d in ((x["day"], x) for x in theme["days"]):
        expected = f"{NEXT[day]}: {d['clue']}" if day in KINDS else d["clue"]
        assert by_day[day] == expected
    review = prompts.review_user(
        ThemeDraftRequest.model_validate(request_body()),
        theme,
        {d: Draft.model_validate(mission_draft(DAY_TYPES[d]).model_dump()) for d in DAY_TYPES},
        {},
    )
    assert f"{NEXT['WED']}: " in review and '"nextTarget"' in review


def test_place_day_clue_needs_no_first_person() -> None:
    """갈 곳 날은 그 자리에서 찾은 흔적이라 '내가 본'이 없어도 되고 코드도 붙이지 않음."""
    found = "흙길에 보리 발자국이 젖은 채 찍혀 있었어."
    theme = follow_theme(MON={"clue": found})
    assert not checks.clue_source_problems(theme, checks.theme_day(theme, "MON"))
    checks.normalize_clue_source(theme)
    assert checks.theme_day(theme, "MON")["clue"] == found
    # 만날 사람 날 흔적은 그 사람이 본 흔적이어야 함
    person = follow_theme(WED={"clue": found, "evidence": {"kind": "TRACE", "when": "그때"}})
    assert checks.clue_source_problems(person, checks.theme_day(person, "WED"))


# ---------------------------------------------------------------- 4. 미션·대화 검사
def mission_reasons(theme: dict[str, Any], day: str, **draft: Any) -> list[str]:
    s = get_settings()
    body = request_body()["missions"][list(DAY_TYPES).index(day)]
    request = MissionDraftRequest.model_validate({**body, "gradeMin": 3, "gradeMax": 3})
    d = Draft.model_validate(mission_draft(DAY_TYPES[day], **draft).model_dump())
    return checks.check_mission(
        theme, request, d, GRADE, s.theme_question_max_chars, s.followup_example_overlap_chars
    )


def test_numbered_question_is_one_activity() -> None:
    """한 문제에 활동 하나(20테마 측정 통과 문제 35개 중 15개가 ①②로 나뉨) — 예시 답이 다음
    행동을 말하지 않아도 됨(고르기 문제가 아님)."""
    theme = follow_theme()
    two = mission_reasons(
        theme,
        "MON",
        question=f"{MATERIAL['MON']}\n① 중요한 내용을 간추려 보세요.\n② 그 까닭을 써 보세요.",
    )
    assert "NUMBERED_ASK" in codes(two)
    one = mission_reasons(
        theme, "MON", question=f"{MATERIAL['MON']} 중요한 내용을 간추리고 그 까닭도 써 보세요."
    )
    assert "NUMBERED_ASK" not in codes(one)
    free = mission_reasons(theme, "MON", exampleAnswer="보리는 신나서 멀리 달려갔어.")
    assert not {"EXAMPLE_NEXT", "EXAMPLE_CHOICE", "NEXT_ASKED"} & set(codes(free))
    # 그래프 성취기준은 나타내기·해석하기를 번호로 둠(검사에서 뺌)
    assert checks.NUMBERED_ASK.search("① 눈금 ② 칸 수") and "4수04-01" in checks.GRAPH_STANDARDS
    assert EXAMPLE_ONLY == ("MISSION_REVIEW EXAMPLE_COMPLETE ", "EXAMPLE_LONG ")  # 미완성·길이만


def test_thinking_type_elements_go_in_one_sentence() -> None:
    """생각 유형마다 꼭 넣는 요소 둘을 한 문장 질문에(사용자 2026-11-24 "생각 유형도")."""
    theme = follow_theme()
    assert set(prompts.THINK_ASK) == {"ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT"}
    for day, kind in DAY_TYPES.items():
        story = prompts.story_text(theme, day, GRADE)
        if kind in prompts.THINK_ASK:
            assert prompts.THINK_ASK[kind] in story, day
        assert "번호(①·②)로 문제를 나누지 않는다" in story


def test_reader_day_writes_to_the_person_in_material() -> None:
    """쓴 글을 읽을 사람 날(아침 재설계): 지문 속 그때 그 자리에 있던 사람에게 보내는 글 — 게시판
    같은 가는 곳(helperUse)은 쓰지 않고, 읽을 사람은 지문에 나와야 함(전에는 '게시판을 본 이웃'이
    갑자기 나와 아이 글과 단서가 따로 놂)."""
    reader = {"nextKind": checks.READER, "nextTarget": "꽃집 할머니", "helperUse": ""}
    theme = follow_theme(
        FRI={**reader, "missionMaterial": MATERIAL["FRI"] + " 꽃집 할머니도 그때 가게 곁에 있었다."}
    )
    bad = [r for r in checks.check_theme(theme, GRADE) if "FRI" in r]
    assert not [r for r in bad if r.startswith(("REQUIRED", "NEXT_EARLY", "MATERIAL_NEXT"))], bad
    assert checks.day_use(theme, "FRI") == ("", [])
    assert "USE_MISSING" not in codes(mission_reasons(theme, "FRI"))
    missing = follow_theme(FRI=reader)
    assert any(r.startswith("MATERIAL_NEXT FRI") for r in checks.check_theme(missing, GRADE))
    assert "지문 속 '꽃집 할머니'에게 보낼 글" in prompts.story_text(theme, "FRI", GRADE)


def test_dialogue_may_say_next_but_not_promise_or_self_name() -> None:
    theme = follow_theme()
    s = get_settings()
    draft = Draft.model_validate(mission_draft("ANALYZE").model_dump())

    def dialogue_codes(third: str) -> list[str]:
        lines = [
            {"speaker": "지호", "text": "보리를 찾으러 여기까지 왔어."},
            {"speaker": "뭉치", "text": "여기 뭔가 있을 것 같아!"},
            {"speaker": HELPER["MON"], "text": third},
            {"speaker": "뭉치", "text": "이 글을 같이 읽어 보자!"},
        ]
        out = checks.check_dialogue(
            theme, "MON", {"lines": lines}, draft, GRADE, s.followup_example_overlap_chars
        )
        return codes(out)

    assert not {"NEXT_EARLY", "NEXT_PROMISE"} & set(dialogue_codes("이 일지를 같이 읽어 볼래?"))
    assert "NEXT_EARLY" not in dialogue_codes("공터 쪽에서 쓴 일지야.")  # 지문에 이미 나옴
    assert "NEXT_PROMISE" in dialogue_codes("같이 읽어 주면 그때 본 걸 알려 줄게.")
    # 20테마 측정 '내가 들려줄 시장 소식꾼의 말이 있어'(자기를 호칭으로 부름)
    assert "SELF_NAME" in dialogue_codes(f"내가 들려줄 {HELPER['MON']}의 말이 있어.")
    assert "SELF_NAME" not in dialogue_codes("내가 쓴 일지야.")
    # 수사 날은 보답 약속을 보지 않음
    tue = checks.check_dialogue(
        theme,
        "TUE",
        {
            "lines": [
                {"speaker": "지호", "text": "왔어."},
                {"speaker": "뭉치", "text": "알려 줄게!"},
            ]
        },
        draft,
        GRADE,
        s.followup_example_overlap_chars,
    )
    assert "NEXT_PROMISE" not in codes(tue)


# ---------------------------------------------------------------- 5. 지시문이 같은 말
GONE = (
    "nextOthers",
    "MATERIAL_CHOICE",
    "NEXT_TOLD",
    "NEXT_EARLY",
    "READER_EARLY",
    "EXAMPLE_NEXT",
    "EXAMPLE_CHOICE",
    "NEXT_ASKED",
)


def test_prompts_say_the_same_follow_rules() -> None:
    theme = follow_theme()
    plan = prompts.PLAN_SYSTEM
    assert "  - 이어 가기:" in plan and "  - 부탁:" not in plan
    for words in ("MATERIAL_NEXT", "NEXT_SOURCE", "MATERIAL_RECORD", "CLUE_PLAIN"):
        assert words in plan, words
    systems = (
        plan,
        prompts.DIALOGUE_SYSTEM,
        prompts.REVIEW_SYSTEM,
        prompts.MISSION_REVIEW_SYSTEM,
        prompts.FOLLOW_JUDGE_SYSTEM,
    )
    for gone in GONE:  # 고르기 틀 검사는 지시문에도 없음
        assert not [i for i, text in enumerate(systems) if gone in text], gone
    assert "보답을 약속하지 않는다" in plan and "보답을 약속하지 않는다" in prompts.DIALOGUE_SYSTEM
    assert "SELF_NAME" in prompts.DIALOGUE_SYSTEM
    story = prompts.story_text(theme, "MON", GRADE)
    assert f"- 오늘 다음 행동(갈 곳): {NEXT['MON']}" in story
    assert "한 문제에 성취기준 활동 하나만" in story and "NUMBERED_ASK" in story
    assert not [g for g in GONE if g in story]
    math = prompts.story_text(theme, "THU", GRADE)
    assert "구한 값으로 고를 범위" not in math and "고르게 하거나" in math
    user = prompts.dialogue_user(
        theme, "MON", Draft.model_validate(mission_draft("ANALYZE").model_dump()), GRADE, []
    )
    assert "대화에 쓰지 않음 — 낱말도 쓰지 않음" not in user
    assert "약속" not in user.split("금지어")[0].replace("보답 약속", "")
    rule = prompts.way_clue_rule(theme, checks.theme_day(theme, "MON"))
    assert "그 자리에서 찾은 흔적" in rule
    assert "만난 사람(" in prompts.way_clue_rule(theme, checks.theme_day(theme, "WED"))
    for path in ("MON.nextTarget", "MON.missionMaterial", "MON.missionHook", "MON.dayStep"):
        assert prompts.fix_rules(theme, path), path
        assert not [g for g in GONE if g in " ".join(prompts.fix_rules(theme, path))], path
    assert "MATERIAL_NEXT" in " ".join(prompts.fix_rules(theme, "MON.missionMaterial"))
    assert "NEXT_SOURCE" in " ".join(prompts.fix_rules(theme, "WED.nextTarget"))
    review = prompts.MISSION_REVIEW_SYSTEM
    assert "이어 가기 날은 문제의 주 자료가 그 주 사건 이야기 지문" in review
    assert prompts.story_brief(theme, "MON")["nextTarget"] == f"갈 곳: {NEXT['MON']}"


# ---------------------------------------------------------------- 6. 예전 저장본
def test_partial_regen_blocks_old_ask_mission_days_only() -> None:
    theme = valid_theme()
    for d in theme["days"]:
        d["missionWay"] = "ASK"
    assert regen.old_follow_days(theme, ["MON", "TUE"]) == ["MON", "TUE"]
    new = follow_theme()
    assert regen.old_follow_days(new, list(checks.DAYS)) == []
    # 예전 부탁 날도 그림만 다시는 막지 않음(미션 요일만 봄)
    assert regen.old_follow_days(theme, []) == []


def test_refit_sets_kind_when_way_or_evidence_changes() -> None:
    theme = follow_theme()
    theme["dayFrames"] = {
        d: {"codes": [request_body()["missions"][i]["standards"][0]["code"]]}
        for i, d in enumerate(checks.DAYS)
    }
    tue = checks.theme_day(theme, "TUE")
    theme["evidencePlan"] = {"TUE": {"kind": "TRACE", "medium": None}}
    changed = checks.refit_ways(theme)
    assert "TUE" in changed and tue["missionWay"] == checks.FOLLOW and tue["nextKind"] == "PLACE"
    wed = checks.theme_day(theme, "WED")
    theme["evidencePlan"]["WED"] = {"kind": "TRACE", "medium": None}
    assert "WED" in checks.refit_ways(copy.deepcopy(theme)) or wed["nextKind"] == "PLACE"


# ---------------------------------------------------------------- 7. 작은 확인 1차를 읽고 고친 것
def test_choice_fields_and_checks_are_gone() -> None:
    """아침 재설계: 견줄 곳 칸(nextOthers)·고르기 검사를 뺌 — 지문이 '빈 공터로 가 보자'처럼 써도
    사건 이야기 안이면 검사하지 않음(글 검토 NEXT_FIT이 자연스러움을 봄)."""
    assert "nextOthers" not in GeneratedDay.model_fields
    assert checks.FIX_PATH.match("MON.nextOthers") is None
    told = follow_theme(MON={"missionMaterial": MATERIAL["MON"] + " 빈 공터로 가 보자."})
    assert not {"NEXT_TOLD", "MATERIAL_CHOICE", "REQUIRED"} & set(theme_codes(told))


def test_material_answer_on_follow_day_fixes_the_material() -> None:
    """지문의 고를 범위에 답 수가 들어가면('4구간은 순찰원' — 답 4) 미션을 다시 만들어도 못 고쳐
    지문 고쳐 쓰기('[지문]')로."""
    theme = follow_theme(THU={"missionMaterial": MATERIAL["THU"] + " 135cm 자리는 발자국 끝이다."})
    final = {"answerKey": {"choiceIds": None, "assignments": None, "finalAnswer": "135cm"}}
    bad = [r for r in mission_reasons(theme, "THU", **final) if r.startswith("MATERIAL_ANSWER")]
    assert bad and "[지문]" in bad[0]
    # 예전 저장본(다음 행동 칸 없음)은 그대로 미션 다시 만들기
    old = checks.fill_rules_out(valid_theme())
    checks.theme_day(old, "THU")["missionMaterial"] = checks.theme_day(theme, "THU")[
        "missionMaterial"
    ]
    bad = [r for r in mission_reasons(old, "THU", **final) if r.startswith("MATERIAL_ANSWER")]
    assert bad and "[지문]" not in bad[0]


# ---------------------------------------------------------------- 8. 작은 확인 2차를 읽고 고친 것
def test_clue_plain_and_stacked_source() -> None:
    """단서 말투(사용자 2026-11-24 "단서 말투도 알아듣게"): 겹친 출처 말은 코드가 덜어 내고, 특징
    이름의 어려운 말은 그 단서만 고쳐 씀(CLUE_PLAIN, 상한 뒤에도 남으면 넘어감)."""
    stacked = "내가 그때 눈으로 직접 본 보리 곁 바닥 재질은 흙이 아니었어!"
    theme = follow_theme(WED={"clue": stacked})
    d = checks.theme_day(theme, "WED")
    checks.normalize_clue_source(theme)
    assert "눈으로" not in d["clue"] and "직접" not in d["clue"] and "내가 그때 본" in d["clue"]
    hit = checks.clue_plain_problems(theme, d)
    assert hit and "재질" in hit[0]
    reason = f"CLUE_PLAIN WED clue {hit[0]}"
    assert checks.fix_targets([reason]) == {"WED.clue": [reason]}
    plain = follow_theme()
    assert not checks.clue_plain_problems(plain, checks.theme_day(plain, "WED"))
    assert SOFT_THEME == ("CLUE_PLAIN ", "DAY_STEP_SAME ")


def test_same_next_target_on_two_days() -> None:
    twice = follow_theme(FRI={"nextTarget": NEXT["WED"]})
    assert "다른 요일과 같은 다음 행동" in " ".join(checks.check_theme(twice, GRADE))


# ---------------------------------------------------------------- 9. 5테마 확인(r971-b5) 뒤
def test_ask_outside_material_is_short() -> None:
    """번호를 막자 한 문장에 할 일 4~5개(auto4 화) → 지문 밖 시키는 말 상한(ASK_LONG)."""
    theme = follow_theme()
    long_ask = (
        "이 글을 읽으며 이어질 일을 묻는 질문을 만들고, 그 질문으로 짐작한 일과 글에서 찾은 말, "
        "다른 짐작을 쓴 뒤 내가 글 속 말을 바탕으로 생각했는지 돌아보세요."
    )
    bad = mission_reasons(theme, "MON", question=f"{MATERIAL['MON']} {long_ask}")
    assert "ASK_LONG" in codes(bad)
    ok = mission_reasons(
        theme, "MON", question=f"{MATERIAL['MON']} 중요한 내용을 간추리고 그 까닭도 써 보세요."
    )
    assert "ASK_LONG" not in codes(ok)
    assert checks.ASK_MAX == {3: 70, 4: 70, 5: 80, 6: 80} and checks.ASK_MAX_GRAPH == 120
    assert f"{checks.ASK_MAX[GRADE]}자 이내(코드 검사 ASK_LONG)" in prompts.story_text(
        theme, "MON", GRADE
    )


def test_helper_speaks_on_follow_days() -> None:
    """new6b 금: 지문은 봉사자가 썼는데 대화는 다른 사람이 꺼냄(HELPER_SILENT)."""
    theme = follow_theme()
    s = get_settings()
    draft = Draft.model_validate(mission_draft("ANALYZE").model_dump())
    lines = [
        {"speaker": "지호", "text": "보리를 찾으러 여기까지 왔어."},
        {"speaker": "뭉치", "text": "여기 뭔가 있을 것 같아!"},
        {"speaker": "지호", "text": "이 일지를 같이 읽어 볼래?"},
        {"speaker": "뭉치", "text": "이 글을 같이 읽어 보자!"},
    ]
    got = checks.check_dialogue(
        theme, "MON", {"lines": lines}, draft, GRADE, s.followup_example_overlap_chars
    )
    assert "HELPER_SILENT" in codes(got)
    assert (
        "HELPER_SILENT" in prompts.DIALOGUE_SYSTEM
        and "읽어 주기만 하는 줄" in prompts.DIALOGUE_SYSTEM
    )


def test_day_step_same_pattern_in_a_week() -> None:
    """auto4 다섯 날 '나는 ~ 살펴보려 해' → 셋째 날부터 고쳐 씀, 상한 뒤엔 넘어감(코드 문장
    아님)."""
    steps = {
        "MON": "나는 이름표 소식을 듣고 안내소부터 살펴보려 해.",
        "TUE": "나는 정원을 돌며 이곳도 둘러보려 해.",
        "WED": "나는 나무 이야기를 나누러 이곳도 살펴보려 해.",
        "THU": "나는 숲길 사람 수를 살피러 이곳도 둘러보려 해.",
        "FRI": "이름표가 바람에 날아갔을까? 낙엽 쉼터도 가 보자!",
    }
    theme = follow_theme(**{d: {"dayStep": t} for d, t in steps.items()})
    got = [r for r in checks.day_step_problems(theme) if r.startswith("DAY_STEP_SAME")]
    assert sorted(r.split(" ")[1] for r in got) == ["THU", "WED"]
    assert set(checks.fix_targets(got)) == {"WED.dayStep", "THU.dayStep"}
    assert "DAY_STEP_SAME" in prompts.PLAN_SYSTEM
    assert "DAY_STEP_SAME " in SOFT_THEME


def test_ask_counts_only_request_sentences() -> None:
    """r971-c5 hand3: 국어사전 성취기준의 사전 뜻 풀이까지 세어 세 번 모두 걸려 테마 실패 → 시키는
    문장만 세고, 마지막 시도에 그것만 남으면 경고로(SOFT_MISSION)."""
    from app.theme_draft.nodes.mission import SOFT_MISSION

    question = (
        "사전 뜻: 고르다=여럿 중 정하다, 닦다=문질러 깨끗이 하다, 끌다=잡아당겨 옮기다.\n"
        f"{MATERIAL['MON']}\n낱말을 하는 일에 따라 나누고 그 까닭도 써 보세요."
    )
    assert (
        checks.ask_text(question, MATERIAL["MON"])
        == "낱말을 하는 일에 따라 나누고 그 까닭도 써 보세요."
    )
    assert "ASK_LONG" not in codes(mission_reasons(follow_theme(), "MON", question=question))
    assert SOFT_MISSION == ("ASK_LONG ",)
