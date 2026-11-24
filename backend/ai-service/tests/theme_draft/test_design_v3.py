"""#782 설계 v3(사용자 결정 2026-11-21 "다 그렇게 진행해"): 틀리면 안 되는 부분은 코드가 정한다.

2차 40개 측정(r782-final40v2) 통과 31개를 다 읽은 결함 293건 중 종류째로 막을 수 있는 것:
- 단서 꼴: 허용 값이 둘 이상이면 빠지는 값을 부정으로('A나 B' 금지, 지시문이 시켰던 것) — CLUE_TEXT·
  CONDITION
- 단서 출처: 부탁 날은 돕는 사람이 본 것·가진 기록(전해 들은 '~였대' 금지, 흔적 날은 본 흔적) —
  CLUE_SOURCE, 두 번 고쳐도 걸리면 코드 틀 문장(clue_template)
- 오늘 온 까닭: 코드가 씀(fill_day_steps), 대화 첫 줄은 그 문장
- 돕는 사람: 국어 부탁 날은 성취기준 영역의 일 틀(호칭 둘·아이 답의 쓰임) — HELPER_SAME·USE_MISSING
- 주인공이 이미 아는 것: 선물·길·출처 찾기 물건은 관리실에 맡겨 둠, 비밀 재료는 아직 안 맛봄, 소리는
  희미하게 들음, 출처 찾기 동물은 동물 자체 특징 금지(FEATURE_KNOWN)
- 그래프 성취기준: 글로 나타내기·해석하기
"""

import copy
from typing import Any

from app.mission_draft.models import Draft
from app.theme_draft import checks, families, prompts
from app.theme_draft.models import ThemeDraftRequest
from tests.theme_draft.fixtures import NEXT, day_with, generated_theme, mission_draft, valid_theme
from tests.theme_draft.helpers import request_body
from tests.theme_draft.test_graph import fixes, gen_llm, review_llm, run

GRADE = 3


def codes(theme: dict[str, Any]) -> list[str]:
    return sorted({r.split(" ")[0] for r in checks.check_theme(theme, GRADE)})


def ask(theme: dict[str, Any], day: str, **fields: Any) -> dict[str, Any]:
    theme = copy.deepcopy(theme)
    checks.theme_day(theme, day).update(missionWay=checks.FOLLOW, **fields)
    return theme


# ---------------------------------------------------------------- 단서 꼴
def test_two_allowed_values_must_be_said_as_negative() -> None:
    """금요일 땅(모래·흙·시멘트)을 허용 값 둘로: 늘어놓으면 CLUE_TEXT, 빠지는 값 부정은 통과."""
    two = {"kind": "RULE", "feature": "땅", "allowed": ["모래", "흙"]}
    listed = day_with(
        valid_theme(), "FRI", condition=two, clue="일지에 보리 발에 모래나 흙이 묻었다고 적혔어."
    )
    assert "CLUE_TEXT" in codes(listed)
    neg = day_with(
        valid_theme(),
        "FRI",
        condition=two,
        clue="일지에 보리 발에 묻은 건 시멘트가 아니었다고 적혔어.",
    )
    assert "CLUE_TEXT" not in codes(neg)
    assert checks.theme_day(neg, "FRI")["condition"]["excluded"] == ["시멘트"]
    assert checks.NEG_MIN_ALLOWED == 2


def test_condition_with_three_excluded_values_is_a_logic_problem() -> None:
    """빠지는 값이 셋 이상이면 늘어놓을 수밖에 없어 조건 꼴 문제(CONDITION — repair_logic이 이 꼴을
    고르지 않음). 빠지는 값이 없는 꼴(특징 값 전부)은 CLUE_EMPTY가 맡아 여기서 보지 않음."""
    theme = valid_theme()
    theme["candidates"] = [*theme["candidates"], "연못"]
    for f in theme["features"]:
        f["values"].append({"candidate": "연못", "value": f["values"][0]["value"]})
    flags = ["빨강", "파랑", "노랑", "초록", "보라"]
    theme["features"].append(
        {
            "name": "깃발",
            "standardCode": None,
            "values": [
                {"candidate": c, "value": v}
                for c, v in zip(theme["candidates"], flags, strict=True)
            ],
        }
    )
    cands, answer = theme["candidates"], theme["answer"]
    days = copy.deepcopy(theme["days"])

    def form(allowed: list[str]) -> list[str]:
        days[2]["condition"] = {"kind": "HINT", "feature": "깃발", "allowed": allowed}
        return [r for r in checks.check_logic(theme, cands, answer, days) if "단서 조건은" in r]

    assert form(["빨강"]) == []  # 값 하나
    assert form(["빨강", "파랑", "노랑"]) == []  # 빠지는 값 둘(부정형)
    assert form(flags) == []  # 특징 값 전부(CLUE_EMPTY 몫)
    found = form(["빨강", "파랑"])  # 빠지는 값 셋
    assert found and found[0].startswith("CONDITION WED")


# ---------------------------------------------------------------- 단서 출처
def test_ask_day_clue_must_come_from_the_helper() -> None:
    hearsay = ask(valid_theme(), "WED", clue="보리는 지붕이 없는 곳으로 갔대.")
    assert "CLUE_SOURCE" in codes(hearsay)
    assert checks.fix_targets(checks.check_theme(hearsay, GRADE)) == {
        "WED.clue": [r for r in checks.check_theme(hearsay, GRADE) if r.startswith("CLUE_SOURCE")]
    }
    direct = ask(valid_theme(), "WED", clue="내가 봤는데 보리는 지붕이 없는 곳으로 갔어.")
    assert "CLUE_SOURCE" not in codes(direct)
    # 흔적 날은 돕는 사람이 본 흔적이라는 말
    trace = ask(valid_theme(), "MON", clue="보리 발자국이 젖어 있었어.")
    assert "CLUE_SOURCE" in codes(trace)
    assert "CLUE_SOURCE" not in codes(
        ask(valid_theme(), "MON", clue="내가 본 보리 발자국은 젖어 있었어.")
    )
    # 수사 날은 따진 사실이라 보지 않음
    assert "CLUE_SOURCE" not in codes(
        day_with(valid_theme(), "WED", clue="보리는 지붕이 없는 곳으로 갔대.")
    )
    # 낱말 끝의 '대'(무대·침대)는 전해 들은 말이 아님
    assert not checks.HEARSAY_END.search("보리 발자국은 무대 앞에 있었어")


def test_clue_template_passes_clue_checks() -> None:
    """두 번 고쳐도 걸리면 쓰는 코드 틀 문장: 꼴·출처·대상 낱말·글자 수를 모두 지킴."""
    for day in ("MON", "WED", "FRI"):
        theme = ask(valid_theme(), day)
        d = checks.theme_day(theme, day)
        text = checks.clue_template(theme, d)
        assert text and len(text) <= checks.day_text_max(d, "clue"), text
        d["clue"] = text
        bad = [r for r in checks.check_theme(theme, GRADE) if f" {day} clue" in r]
        assert bad == [], (day, text, bad)
    # 수사 날은 '증거를 따져 보니'(출처 없이 꼴만), 기록 날은 배정 매체 낱말
    inv = valid_theme()
    for day in ("MON", "FRI"):
        d = checks.theme_day(inv, day)
        text = checks.clue_template(inv, d)
        assert text and "따져 보니" in text, text
        d["clue"] = text
        assert not [r for r in checks.check_theme(inv, GRADE) if f" {day} clue" in r], text
    # 사건 단서: 수사 날은 틀 없음, 부탁 날은 출처만 고침(내용은 그대로)
    assert checks.clue_template(valid_theme(), checks.theme_day(valid_theme(), "TUE")) is None
    story = ask(valid_theme(), "TUE", clue="보리가 공을 물고 골목 쪽으로 달려갔대.")
    assert checks.clue_template(story, checks.theme_day(story, "TUE")) == (
        "보리가 공을 물고 골목 쪽으로 달려갔어."
    )
    trace = ask(valid_theme(), "THU", clue="보리 발자국이 골목 안쪽에 이어졌대.")
    trace_day = checks.theme_day(trace, "THU")
    assert trace_day["evidence"]["kind"] == "TRACE"
    assert checks.clue_template(trace, trace_day) == "내가 보니 보리 발자국이 골목 안쪽에 이어졌어."


def test_clue_template_for_shop_day_says_buying() -> None:
    d = {
        "day": "TUE",
        "missionWay": checks.FOLLOW,
        "evidence": {"kind": "SIGHTING"},
        "condition": {"kind": "RULE", "feature": "선물을 산 가게", "allowed": ["서점"]},
    }
    theme = {"storyType": "GIFT", "target": "생일에 받은 리본 상자", "days": [d]}
    text = checks.clue_template(theme, d)
    assert text and checks.BUY_WORDS.search(text) and "선물" in text and "'서점'" in text


def test_second_fix_uses_template_instead_of_asking_again() -> None:
    """모델이 두 번 다 전해 들은 말로 고쳐 쓰면 두 번째는 코드 틀 문장(같은 칸을 세 번 맡기지
    않음)."""
    hearsay = "보리는 지붕이 없는 곳으로 갔대."
    gen = gen_llm(
        theme=lambda n, d: generated_theme(day_with(valid_theme(), "WED", clue=hearsay)),
        fix=lambda n, d: fixes(("WED.clue", hearsay)),
    )
    response = run(gen, review_llm())
    assert response.failure is None
    # #782 설계 v4: 전해 들은 말 끝은 코드가 먼저 직접 말로 다듬어 고쳐 쓰기 없이 통과
    assert gen.count("GeneratedFixes") == 0
    assert response.theme is not None
    # #971: 응답 단서는 다음 행동 이름표 뒤에 그 사람의 말
    assert response.theme.days[2].clue == f"{NEXT['WED']}: 보리는 지붕이 없는 곳으로 갔어."


# ---------------------------------------------------------------- 오늘 온 까닭
def test_day_step_code_sentence_only_when_blank_and_passes_its_checks() -> None:
    """코드 문장(day_step_text)은 빈 칸·두 번 고쳐도 걸릴 때·첫 줄로 못 쓸 때만 씀(#782 설계 v7:
    평소엔 모델이 '오늘 여기 온 까닭'으로). 코드 문장은 오늘 온 까닭 검사를 모두 통과."""
    blank = ask(valid_theme(), "MON")
    for d in blank["days"]:
        d["dayStep"] = ""
    theme = checks.finalize_texts(blank)
    days = theme["days"]
    assert days[0]["dayStep"].endswith("조사를 시작했어.") and "어제" not in days[0]["dayStep"]
    # 화~금은 요일마다 다른 꼴, 돕는 사람 이름 없음(지어낼 일이 없음)
    later = [d["dayStep"] for d in days[1:]]
    assert len(set(later[:3])) == 3
    assert all(h not in s for s in later for h in (d["helper"] for d in days))
    assert all(len(d["dayStep"]) <= checks.TEXT_MAX["dayStep"] for d in days)
    assert not checks.day_step_problems(theme)
    assert not [p for d in days for p in checks.first_line_problems(theme, d["day"], d["dayStep"])]
    # 너무 길면 짧은 꼴
    long = copy.deepcopy(theme)
    long["days"][1]["place"] = "아주아주 긴 이름의 마을 공원 놀이터 앞 쉼터 의자 옆"
    short = checks.day_step_text(long, 1)
    assert "아주아주" not in short and len(short) <= checks.TEXT_MAX["dayStep"]
    # 장소 이름에 그날 단서 값(지붕 '없음')이 들어 있으면 장소를 뺀 꼴(CLUE_EARLY 안 걸림)
    named = copy.deepcopy(theme)
    named["days"][2]["place"] = "지붕 없음 쉼터"
    step = checks.day_step_text(named, 2)
    assert "없음" not in step and step.endswith("봤어.")
    # 모델이 쓴 오늘 온 까닭은 코드가 덮어쓰지 않음
    kept = checks.finalize_texts(valid_theme())
    assert checks.theme_day(kept, "TUE")["dayStep"] == valid_theme()["days"][1]["dayStep"]
    same = copy.deepcopy(theme)
    same["days"][2]["helper"] = same["days"][0]["helper"]
    assert not [r for r in checks.helper_problems(same) if " dayStep " in r]


def test_dialogue_prompt_gets_fixed_first_line() -> None:
    theme = checks.finalize_texts(ask(valid_theme(), "TUE"))
    plain = Draft.model_validate(mission_draft("EVALUATE").model_dump())
    user = prompts.dialogue_user(theme, "TUE", plain, GRADE, [])
    step = checks.theme_day(theme, "TUE")["dayStep"]
    assert f"첫 줄(코드가 넣음, 되풀이하지 않음): 지호: {step}" in user
    assert "너는 그 뒤 3~4줄" in user
    assert "첫 줄(① 오늘 온 까닭)은 코드가 첫 등장인물의 말로 넣는다" in prompts.DIALOGUE_SYSTEM


# ---------------------------------------------------------------- 돕는 사람 일 틀
KOREAN = {
    "ANALYZE": ("4국05-02", "작품 감상"),
    "EVALUATE": ("4국02-04", "사실과 의견"),
    "CREATE": ("4국03-03", "의견 글"),
    "SOLVE": ("4수04-01", "그래프"),
    "REFLECT": ("4국05-05", "즐겨 감상"),
}


def korean_request() -> ThemeDraftRequest:
    body = request_body()
    for m in body["missions"]:
        code, statement = KOREAN[m["thinkingType"]]
        m["standards"] = [{"code": code, "statement": statement}]
    return ThemeDraftRequest.model_validate(body)


# ---------------------------------------------------------------- 주인공이 이미 아는 것
def test_kept_target_and_intro_rules() -> None:
    def theme_of(code: str, branch: str | None = None) -> dict[str, Any]:
        return {"storyType": code, "branch": branch}

    assert families.kept_target(theme_of("GIFT")) and families.kept_target(theme_of("ROUTE"))
    assert families.kept_target(theme_of("ORIGIN", "물건")) and families.kept_target(
        theme_of("ORIGIN")
    )
    assert not families.kept_target(theme_of("ORIGIN", "동물"))
    assert not families.kept_target(theme_of("SECRET_INGREDIENT"))
    assert "관리실 선반에 맡겨진" in families.GIFT.intro_cuts[1] and "관리실" in families.GIFT.rules
    assert (
        "관리실" in families.ROUTE.intro_cuts[1]
        and "아직 맛보지 않음" in families.SECRET_INGREDIENT.intro_cuts[1]
    )
    # #782 설계 v10: 아이는 소리를 직접 듣지 않음(#779의 '창가에서 귀 기울임' 줄과 달라져 병합 때
    # 이 줄로 맞춤). 소리 난 자리는 여전히 보이지 않음
    assert "소리 난 자리가 보이지 않음" in families.SOUND.intro_cuts[1]
    assert "직접 듣지 않음" in families.SOUND.intro_cuts[1]
    assert "INTRO_HEARD" in families.SOUND.rules
    # 종류 규칙 예시에 전해 들은 말투가 없음
    for t in families.STORY_TYPES.values():
        assert "보였대" not in t.rules and "났대" not in t.rules and "봤대" not in t.rules, t.code


def test_origin_animal_cannot_use_the_animal_itself_as_feature() -> None:
    theme = {**valid_theme(), "storyType": "ORIGIN", "branch": "동물"}
    theme["features"] = [
        *theme["features"],
        {
            "name": "목줄 색",
            "standardCode": None,
            "values": [
                {"candidate": c, "value": v}
                for c, v in zip(theme["candidates"], ["빨강", "파랑", "노랑", "초록"], strict=True)
            ],
        },
    ]
    assert [r.split(" ")[0] for r in checks.known_feature_problems(theme)] == ["FEATURE_KNOWN"]
    assert checks.known_feature_problems({**theme, "branch": "물건"}) == []
    assert not checks.fix_targets(checks.known_feature_problems(theme))  # 줄거리 다시
