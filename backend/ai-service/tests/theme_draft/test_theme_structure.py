"""#782 테마 짜임(사용자 결정 2026-11-19, 기준안 — 확인 전).

- 줄거리가 요일마다 오늘 온 까닭(dayStep)을 씀: 그날·앞 요일 단서 결과를 말하지 않음, 비면 REQUIRED
- 대화는 모델이 처음부터 끝까지(4~5줄), 마지막 줄은 뭉치, 앞 요일 단서 결과는 PREV_CLUE
- 서술·논술 예시 답은 학년 문장 수 상한(EXAMPLE_LONG, 예시 답만 고쳐 쓰기)
- 예전 저장본(부분 다시 생성 재료)은 dayStep이 없어도 읽힘
- 후보를 빼지 않는 날은 사건 단서(STORY: 후보 이름·특징 값 없이 사건이 어떻게 벌어졌는지), 앞 요일과
  같은 단서는 CLUE_REPEAT, 마지막 틀린 후보는 금요일에 빠짐
"""

from typing import Any

from app.config import get_settings
from app.mission_draft.models import Draft, MissionDraftRequest
from app.theme_draft import checks, prompts
from app.theme_draft.models import GeneratedDay, GeneratedExampleFix
from tests.theme_draft.fixtures import STEP, dialogue, mission_draft, valid_theme
from tests.theme_draft.helpers import STANDARDS
from tests.theme_draft.test_graph import gen_llm, review_llm, run

GRADE = 3


def codes(reasons: list[str]) -> list[str]:
    return sorted(r.split(" ")[0] for r in reasons)


def theme_with_step(day: str, step: str) -> dict[str, Any]:
    theme = valid_theme()
    checks.theme_day(theme, day)["dayStep"] = step
    return theme


def step_reasons(theme: dict[str, Any]) -> list[str]:
    return [r for r in checks.check_theme(theme, GRADE) if "dayStep" in r]


# ---------------------------------------------------------------- 오늘 온 까닭
def test_day_step_is_required_and_fixable_field() -> None:
    assert step_reasons(valid_theme()) == []
    theme = theme_with_step("WED", " ")
    assert step_reasons(theme) == ["REQUIRED WED.dayStep"]
    assert checks.fix_targets(step_reasons(theme)) == {"WED.dayStep": step_reasons(theme)}
    assert checks.TEXT_MAX["dayStep"] == checks.LINE_MAX
    long = theme_with_step("WED", "가" * 41)
    assert "LENGTH WED.dayStep 41자 > 40" in checks.check_theme(long, GRADE)


def test_day_step_must_not_tell_today_or_earlier_clue() -> None:
    """어제 한 일만 잇기(문제는 순서 없이 풀 수 있어 앞 요일 단서를 못 얻은 학생이 있음)."""
    today = theme_with_step("FRI", "문구점 사장님 말대로 흙 묻은 발자국을 따라 왔어.")
    assert step_reasons(today) == ["CLUE_EARLY FRI dayStep에 그날 단서 결론(허용 값 ['흙'])"]
    earlier = theme_with_step("THU", "꽃집 할머니 말에 지붕이 없음을 알고 골목으로 왔어.")
    assert step_reasons(earlier) == ["PREV_CLUE THU dayStep에 앞 요일 단서 결과(허용 값 ['없음'])"]
    assert set(checks.fix_targets(step_reasons(earlier))) == {"THU.dayStep"}
    # 뒤 요일 값은 괜찮음
    assert step_reasons(theme_with_step("MON", "흙길부터 살펴보러 왔어.")) == []


def test_prev_values_skip_own_day_and_later_days() -> None:
    theme = valid_theme()
    assert checks.prev_values(theme, "MON", "젖음 없음 흙") == []
    assert checks.prev_values(theme, "THU", "젖음 없음 흙") == ["젖음", "없음"]


def test_day_step_rules_in_plan_fix_and_dialogue_prompts() -> None:
    # #782 설계 v7: 모델이 오늘 여기 온 까닭을 쓰고 지어냄·자기 이름을 코드가 봄
    assert "- dayStep: 오늘 이 장소에 온 까닭 한 줄" in prompts.PLAN_SYSTEM
    assert "DAY_STEP_MADE" in prompts.PLAN_SYSTEM and "SELF_NAME" in prompts.PLAN_SYSTEM
    assert "DAY_STEP_LINK" not in prompts.PLAN_SYSTEM
    rules = " ".join(prompts.fix_rules(valid_theme(), "FRI.dayStep"))
    assert "앞 요일 단서 결과 낱말 ['젖음', '없음']" in rules and "['흙']" in rules
    user = prompts.dialogue_user(valid_theme(), "TUE", _draft("EVALUATE"), GRADE, [])
    assert f"오늘 온 까닭(오늘 여기 온 까닭, ① 재료): {STEP['TUE']}" in user
    assert "줄 수: 4~5줄" in user
    # 쓰지 말 낱말에 앞 요일 단서 값도
    assert "젖음" in prompts.avoid_words(valid_theme(), "WED")


def test_old_saved_day_without_step_still_loads_and_dialogue_uses_code_step() -> None:
    """부분 다시 생성은 예전 저장본 내부 칸을 다시 읽음 — dayStep이 없어도 읽히고 대화 첫 줄은
    그 자리에서 만든 코드 문장(#782 설계 v4 B4, 전에는 '(없음 …)' 장면 메모)."""
    old = {k: v for k, v in valid_theme()["days"][0].items() if k != "dayStep"}
    assert GeneratedDay.model_validate(old).dayStep == ""
    theme = valid_theme()
    del checks.theme_day(theme, "MON")["dayStep"]
    user = prompts.dialogue_user(theme, "MON", _draft("ANALYZE"), GRADE, [])
    assert "(없음" not in user
    step = checks.day_step_of(theme, "MON")
    assert step.endswith("조사를 시작했어.") and f"지호: {step}" in user
    lines = checks.with_first_line(theme, "MON", [{"speaker": "뭉치", "text": "가 보자!"}], GRADE)
    assert lines[0] == {"speaker": "지호", "text": step}


# ---------------------------------------------------------------- 사건 단서·되풀이·금요일 마감
def test_story_day_removes_no_one_and_has_no_feature() -> None:
    """사건 단서 날(valid_theme 화·목)은 rulesOut이 비고 응답 clueFeature는 null, 검사는 통과."""
    theme = checks.fill_rules_out(valid_theme())
    story = [d for d in theme["days"] if checks.is_story(d["condition"])]
    assert [d["day"] for d in story] == ["TUE", "THU"]
    assert all(d["rulesOut"] == [] for d in story)
    public = checks.public_theme(theme)
    assert [d["clueFeature"] for d in public["days"] if d["day"] in ("TUE", "THU")] == [None, None]
    assert checks.check_theme(valid_theme(), GRADE) == []
    # 두 사건 단서는 clue_key가 같아도 CLUE_REPEAT가 아님(check_logic이 사건 단서는 비교하지 않음)
    assert checks.clue_key(story[0]["condition"]) == checks.clue_key(story[1]["condition"])


def test_story_clue_with_candidate_or_value_is_story_value() -> None:
    hits = checks.story_value_hits
    theme = valid_theme()
    table, _ = checks.feature_table(theme)
    assert hits(theme, table, "보리 발자국이 골목 안쪽으로 이어졌어.") == []
    assert hits(theme, table, "보리가 창고 쪽으로 갔대.") == ["창고"]
    assert hits(theme, table, "보리 발자국이 흙길로 이어졌어.") == ["흙"]  # 어느 특징 값이든
    checks.theme_day(theme, "THU")["clue"] = "보리 발자국이 정자 쪽으로 이어졌어."
    assert checks.check_theme(theme, GRADE) == [
        "STORY_VALUE THU clue 사건 단서에 후보 이름·특징 값 ['정자'](후보를 가르지 않는 사건 "
        "이야기로)"
    ]
    assert checks.fill_rules_out(theme)["days"][3]["rulesOut"] == []  # 이름을 말해도 빼지 않음


def test_last_wrong_candidate_on_thursday_is_logic() -> None:
    """마지막 틀린 후보는 금요일에 빠짐(목요일에 끝나면 LOGIC, 전에는 통과)."""
    theme = valid_theme()
    checks.theme_day(theme, "THU").update(
        clue="보리 발바닥에 흙이 묻어 있었어.",
        condition={"kind": "RULE", "feature": "땅", "allowed": ["흙"]},
    )
    checks.theme_day(theme, "FRI").update(
        clue="일지에 보리가 골목 안쪽으로 갔다고 적혔어.",
        condition={"kind": "STORY", "feature": "", "allowed": []},
    )
    assert checks.check_theme(theme, GRADE) == [
        "LOGIC 마지막 틀린 후보가 THU에 빠짐(금요일이어야 함)"
    ]
    assert checks.LAST_ELIMINATION_MIN == checks.DAYS.index("FRI")


def test_hint_same_as_earlier_day_is_clue_repeat() -> None:
    theme = valid_theme()
    checks.theme_day(theme, "THU").update(
        clue="보리 발자국이 지붕이 없는 길로 이어졌어.",
        condition={"kind": "HINT", "feature": "지붕", "allowed": ["없음"]},
    )
    assert checks.check_theme(theme, GRADE) == [
        "CLUE_REPEAT THU 앞 요일과 같은 단서(특징 '지붕', 허용 값 ['없음']) — 다른 특징이나 새 "
        "값으로"
    ]
    # 같은 특징·같은 허용 값이면 순서·종류가 달라도 같은 단서
    rule = {"kind": "RULE", "feature": "지붕", "allowed": ["없음"]}
    assert checks.clue_key(rule) == checks.clue_key({**rule, "kind": "HINT"})


def test_repair_hints_turns_hint_without_other_feature_into_story() -> None:
    """정보 없는 힌트·앞 요일과 같은 힌트를 바꿀 다른 특징이 없으면(남은 후보가 다른 특징 값을 다
    채우거나 이미 쓴 단서뿐) 사건 단서로 바꿈(#782 테마 짜임, 전에는 그대로 두어 다시 생성)."""
    theme = valid_theme()
    # 땅: 창고도 모래라 남은 놀이터(모래)·텃밭(흙)이 땅 값을 다 채움. 지붕 없음은 화요일, 물기
    # 젖음은 월요일이 이미 씀 → 수요일 물기 젖음 힌트를 바꿀 특징이 없음
    land = next(f for f in theme["features"] if f["name"] == "땅")
    next(v for v in land["values"] if v["candidate"] == "창고")["value"] = "모래"
    checks.theme_day(theme, "TUE").update(
        clue="보리는 지붕이 없는 곳으로 갔대.",
        condition={"kind": "HINT", "feature": "지붕", "allowed": ["없음"]},
    )
    checks.theme_day(theme, "WED").update(
        clue="보리 털이 비에 젖어 있었대.",
        condition={"kind": "HINT", "feature": "물기", "allowed": ["젖음"]},
    )
    assert "CLUE_REPEAT WED" in [" ".join(r.split(" ")[:2]) for r in checks.check_theme(theme, 3)]
    assert checks.repair_hints(theme) == ["WED"]
    assert checks.theme_day(theme, "WED")["condition"] == {
        "kind": "STORY",
        "feature": "",
        "allowed": [],
    }
    assert checks.theme_day(theme, "TUE")["condition"]["feature"] == "지붕"  # 되풀이가 아니면 둠
    assert checks.repair_hints(theme) == []  # 고친 뒤에는 더 바꿀 것이 없음


def test_story_clue_fix_rules_and_mission_line() -> None:
    """사건 단서 날 단서 고쳐 쓰기 규칙과 미션 요청 줄(특징 대신 사건)."""
    rules = " ".join(prompts.fix_rules(valid_theme(), "TUE.clue"))
    assert "사건 단서다" in rules and "STORY_VALUE" in rules
    extra = prompts.mission_extra(valid_theme(), "THU", GRADE, [])
    assert "오늘 단서는 사건 단서다" in extra and "오늘 단서가 다루는 특징" not in extra
    assert "STORY(사건 단서)" in prompts.PLAN_SYSTEM and "CLUE_REPEAT" in prompts.PLAN_SYSTEM
    assert "금요일(FRI) 단서에서 빠져" in prompts.PLAN_SYSTEM


# ---------------------------------------------------------------- 대화
def _draft(thinking_type: str = "ANALYZE", **kw: Any) -> Draft:
    return Draft.model_validate(mission_draft(thinking_type, **kw).model_dump())


def _check_dialogue(day: str, lines: list[dict[str, str]]) -> list[str]:
    return checks.check_dialogue(
        valid_theme(),
        day,
        {"lines": lines},
        _draft(checks.DAY_TYPE[day]),
        GRADE,
        get_settings().followup_example_overlap_chars,
    )


def test_dialogue_last_line_is_mungchi() -> None:
    lines = [x.model_dump() for x in dialogue().lines]
    assert _check_dialogue("MON", lines) == []
    last_jiho = [*lines[:-1], {"speaker": "지호", "text": "같이 살펴볼래?"}]
    assert codes(_check_dialogue("MON", last_jiho)) == ["LAST_SPEAKER"]


def test_dialogue_prompt_has_no_fixed_lines() -> None:
    system = prompts.DIALOGUE_SYSTEM
    # #782 설계 v3: 첫 줄(오늘 온 까닭)만 코드, 나머지는 모델
    assert "첫 줄(① 오늘 온 까닭)은 코드가 첫 등장인물의 말로 넣는다" in system
    assert "코드가 그대로 넣는다" not in system
    assert "앞 요일 단서가 무엇이었는지 말하지 않는다" in system


# ---------------------------------------------------------------- 단서 글
def test_clue_rule_is_a_found_scene_with_value_word() -> None:
    plan = prompts.PLAN_SYSTEM
    assert "clue는 그날 미션 방식대로 한 줄 말로 쓴다" in plan  # #782 미션 방식별 단서 꼴
    assert "코드가 첫 단서에는 그때의 시각을" not in plan


# ---------------------------------------------------------------- 예시 답 길이
def _request(thinking_type: str = "ANALYZE", input_type: str = "NARRATIVE") -> MissionDraftRequest:
    code, statement, _ = STANDARDS[thinking_type]
    return MissionDraftRequest.model_validate(
        {
            "gradeMin": GRADE,
            "gradeMax": GRADE,
            "thinkingType": thinking_type,
            "inputType": input_type,
            "standards": [{"code": code, "statement": statement}],
            "elementCodes": [{"code": f"{thinking_type}_X", "label": "요소", "description": ""}],
        }
    )


def test_example_answer_sentence_limit_by_grade_only_for_written_answers() -> None:
    # #782 설계 v7(사용자 결정 2026-11-22 "예시 답은 5문장으로")
    assert checks.EXAMPLE_SENTENCES == {3: 5, 4: 5, 5: 5, 6: 5}
    assert checks.sentence_count("하나다. 둘이다! 셋일까? 넷이다.") == 4
    long = "가는 길이다. " * 6
    s = get_settings()

    def run_check(thinking_type: str, input_type: str, example: str) -> list[str]:
        return checks.check_mission(
            valid_theme(),
            _request(thinking_type, input_type),
            _draft(thinking_type, exampleAnswer=example),
            GRADE,
            s.theme_question_max_chars,
            s.followup_example_overlap_chars,
        )

    assert "EXAMPLE_LONG" in codes(run_check("ANALYZE", "NARRATIVE", long))
    assert "EXAMPLE_LONG" not in codes(run_check("ANALYZE", "NARRATIVE", "가는 길이다. " * 5))


def test_long_example_is_fixed_alone_with_max_sentences() -> None:
    """예시 답이 길면 예시 답만 고쳐 쓰고(EXAMPLE_ONLY) 고쳐 쓰기 요청에 문장 수 상한을 줌."""
    long = "보리는 길을 따라 달려갔다. " * 6
    short = "보리는 비가 그쳐 신나서 달려갔어."

    def draft(n: int, d: str | None) -> Any:
        if d == "MON":
            return mission_draft("ANALYZE", exampleAnswer=long)
        return mission_draft(checks.DAY_TYPE[d or "MON"])

    gen = gen_llm(
        draft=draft,
        example=lambda n, d: GeneratedExampleFix(exampleAnswer=short, finalAnswer=None),
    )
    response = run(gen, review_llm())
    assert response.failure is None
    assert gen.count("GeneratedDraft", "MON") == 1 and gen.count("GeneratedExampleFix") == 1
    assert '"maxSentences": 5' in gen.users("GeneratedExampleFix")[0]
    mon = next(m for m in response.missions if m.day == "MON")
    assert mon.draft.example_answer == short


def test_story_value_is_clue_fix_and_story_day_rules_have_no_empty_values() -> None:
    """사건 단서에 값이 섞이면 그 단서만 고쳐 쓰고, 사건 단서 날 다른 칸의 고쳐 쓰기 규칙에 빈
    특징·허용 값이 들어가지 않음."""
    reason = "STORY_VALUE THU clue 사건 단서에 후보 이름·특징 값 ['정자'](사건 이야기로)"
    assert checks.fix_targets([reason]) == {"THU.clue": [reason]}
    theme = valid_theme()
    for key in ("sceneNote", "missionMaterial", "dayStep", "discovery"):
        rules = " ".join(prompts.fix_rules(theme, f"THU.{key}"))
        assert "특징 ''" not in rules and "낱말 []" not in rules, key
        assert prompts.STORY_DAY_HIDE in rules, key
