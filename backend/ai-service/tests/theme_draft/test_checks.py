"""테마 글 검사(checks.py) 표 시험. 결함 하나를 넣으면 정확히 그 사유 코드만 나와야 한다."""

import copy
from collections.abc import Callable
from typing import Any

import pytest

from app.config import get_settings
from app.mission_draft.models import Draft, MissionDraftRequest
from app.theme_draft import checks
from app.theme_draft.models import GeneratedDay, ThemeDraftRequest
from tests.theme_draft.fixtures import (
    day_with,
    dialogue,
    feature,
    mission_draft,
    story_review,
    theme_with,
    valid_theme,
)
from tests.theme_draft.helpers import STANDARDS, request_body

CODES = {code for code, _, _ in STANDARDS.values()}
GRADE = 3


def codes(reasons: list[str]) -> list[str]:
    """사유의 검사 코드(요일이 있으면 '코드 요일')."""
    out = []
    for r in reasons:
        head, _, rest = r.partition(" ")
        day = rest.split(" ", 1)[0]
        out.append(f"{head} {day}" if day in checks.DAYS else head)
    return sorted(out)


def themed(**kw: Any) -> Callable[[], dict]:
    return lambda: theme_with(**kw)


def on_day(d: str, **kw: Any) -> Callable[[], dict]:
    return lambda: day_with(valid_theme(), d, **kw)


def edit(fn: Callable[[dict], None]) -> Callable[[], dict]:
    def build() -> dict:
        theme = valid_theme()
        fn(theme)
        return theme

    return build


def cond(d: str, **kw: Any) -> Callable[[], dict]:
    def build() -> dict:
        theme = valid_theme()
        target = next(x for x in theme["days"] if x["day"] == d)
        target["condition"] = {**target["condition"], **kw}
        return theme

    return build


def _rename(theme: dict, old: str, new: str) -> None:
    theme["candidates"] = [new if c == old else c for c in theme["candidates"]]
    for f in theme["features"]:
        for v in f["values"]:
            if v["candidate"] == old:
                v["candidate"] = new


def _answer_out(theme: dict) -> None:
    # 목요일 조건을 모래로: 정답(흙)이 빠지고 놀이터는 어떤 RULE로도 빠지지 않음
    thu = theme["days"][3]
    thu["condition"]["allowed"] = ["모래"]
    thu["clue"] = "보리 발바닥에 모래가 묻어 있었어."


def _stale_rule(theme: dict) -> None:
    # 금요일 RULE(지붕 없음): 창고·정자는 수요일에 이미 빠짐
    fri = theme["days"][4]
    fri.update(
        clue="보리는 지붕이 없는 데서 놀았어.",
        condition={"kind": "RULE", "feature": "지붕", "allowed": ["없음"]},
    )


def _early_finish(theme: dict) -> None:
    # 화 RULE(지붕 없음: 창고·정자) → 수 RULE(땅 흙: 놀이터) → 목 HINT: 마지막 틀린 후보가 수요일에
    # 빠짐
    days = theme["days"]
    days[1].update(
        clue="보리는 지붕이 없는 곳으로 갔대.",
        condition={"kind": "RULE", "feature": "지붕", "allowed": ["없음"]},
    )
    days[2].update(
        clue="보리 발바닥에 흙이 묻어 있었어.",
        condition={"kind": "RULE", "feature": "땅", "allowed": ["흙"]},
    )
    days[3].update(
        clue="보리 털이 아직 젖어 있었대.",
        condition={"kind": "HINT", "feature": "물기", "allowed": ["젖음"]},
    )


def _never_out(theme: dict) -> None:
    # 수요일을 HINT로: 정자가 어떤 RULE로도 빠지지 않음(목요일 RULE은 놀이터·창고)
    wed = theme["days"][2]
    wed.update(
        clue="보리 털이 젖어 있었대.",
        condition={"kind": "HINT", "feature": "물기", "allowed": ["젖음"]},
    )


def _inventor6(theme: dict) -> None:
    # 화요일 HINT(땅 흙): 남은 놀이터·창고를 빼는 내용인데 HINT라고 적음
    tue = theme["days"][1]
    tue.update(
        clue="보리 발에 흙이 조금 있었대.",
        condition={"kind": "HINT", "feature": "땅", "allowed": ["흙"]},
    )


def _narrow_hint(theme: dict) -> None:
    # 화요일 RULE(땅 흙: 놀이터·창고) 뒤 수요일 HINT(지붕 없음): 남은 텃밭·정자 중 정자를 빼는 HINT
    theme["days"][1].update(
        clue="보리 발에 흙이 묻었대.",
        condition={"kind": "RULE", "feature": "땅", "allowed": ["흙"]},
    )
    theme["days"][2].update(
        clue="보리는 지붕이 없는 곳으로 갔대.",
        condition={"kind": "HINT", "feature": "지붕", "allowed": ["없음"]},
    )
    theme["days"][3].update(
        clue="보리는 지붕이 없는 데로 갔어.",
        condition={"kind": "RULE", "feature": "지붕", "allowed": ["없음"]},
    )


def _beach5(theme: dict) -> None:
    # 월요일 HINT(땅: 모래·흙·시멘트, 네 후보 모두 맞음)인데 문장은 흙만 말해 표보다 좁음
    mon = theme["days"][0]
    mon["condition"] = {"kind": "HINT", "feature": "땅", "allowed": ["모래", "시멘트", "흙"]}
    mon["clue"] = "보리 발자국에 흙이 묻어 있었어."


THEME_CASES: list[tuple[str, Callable[[], dict], list[str]]] = [
    ("valid", valid_theme, []),
    ("title empty", themed(title=" "), ["REQUIRED"]),
    ("target empty", themed(target=""), ["REQUIRED"]),
    ("title too long", themed(title="가" * 21), ["LENGTH"]),
    ("intro too long", themed(intro="가" * 201), ["LENGTH"]),
    ("no characters", themed(characters=[]), ["CHARACTERS"]),
    (
        "four characters",
        themed(characters=[{"name": f"아이{i}", "look": "모습"} for i in range(4)]),
        ["CHARACTERS"],
    ),
    ("character without look", themed(characters=[{"name": "지호", "look": ""}]), ["CHARACTERS"]),
    ("mungchi as character", themed(characters=[{"name": "뭉치", "look": "솜"}]), ["CHARACTERS"]),
    ("candidate color word", edit(lambda t: _rename(t, "창고", "빨간창고")), ["CANDIDATES"]),
    ("candidate one char", edit(lambda t: _rename(t, "창고", "곳")), ["CANDIDATES"]),
    ("days out of order", edit(lambda t: t["days"].reverse()), ["DAYS"]),
    ("wrong thinking type", on_day("MON", thinkingType="SOLVE"), ["DAYS MON"]),
    ("clue empty", on_day("TUE", clue=""), ["CLUE_TEXT TUE", "REQUIRED"]),
    ("clue too long", on_day("MON", clue="보리 발자국이 젖어 있었어" + "가" * 30), ["LENGTH"]),
    ("place too long", on_day("MON", place="가" * 21), ["LENGTH"]),
    ("clue types repeat", on_day("TUE", clueType="발자국"), ["CLUE_TYPE"]),
    ("answer in title", themed(title="텃밭의 비밀"), ["ANSWER_LEAK"]),
    ("answer in big question", themed(bigQuestion="보리는 텃밭에 있을까?"), ["ANSWER_LEAK"]),
    ("answer in scene", on_day("TUE", sceneNote="텃밭 옆을 지나는 장면"), ["ANSWER_LEAK"]),
    ("answer in outro is fine", themed(outro="보리는 텃밭에 있었어요."), []),
    ("unsafe word", themed(world="흉기가 있는 마을"), ["UNSAFE"]),
    ("kana leaks", themed(world="작은 마을 です"), ["LANGUAGE"]),
    (
        "feature code outside week",
        edit(lambda t: t["features"][0].update(standardCode="6사01-01")),
        ["FEATURE_SOURCE"],
    ),
    (
        "evidence when empty",
        on_day("WED", evidence={"kind": "SIGHTING", "when": " "}),
        ["EVIDENCE WED"],
    ),
    (
        "too few features",
        edit(lambda t: t.update(features=t["features"][:1])),
        ["FEATURES"],
    ),  # 표가 틀리면 논리 계산은 하지 않음
    ("feature missing candidate", edit(lambda t: t["features"][2]["values"].pop()), ["FEATURES"]),
    (
        "duplicate feature name",
        edit(lambda t: t["features"].append(feature("땅", {}))),
        ["FEATURES"],
    ),
    ("unknown condition feature", cond("MON", feature="소리"), ["CONDITION MON"]),
    ("allowed outside table", cond("MON", allowed=["마름"]), ["CONDITION MON"]),
    # 정답을 빼는 단서
    ("clue excludes answer", edit(_answer_out), ["LOGIC", "LOGIC THU"]),
    # 이미 빠진 후보만 빼는 RULE(learning 결정적 단서 계산과 어긋남)
    ("rule removes nothing new", edit(_stale_rule), ["LOGIC FRI"]),
    # 마지막 틀린 후보가 수요일에 빠짐
    ("last wrong out too early", edit(_early_finish), ["LOGIC"]),
    # 어떤 RULE로도 빠지지 않는 틀린 후보
    ("wrong candidate never out", edit(_never_out), ["LOGIC"]),
    # 시험 lab3-inventor-6: HINT가 남은 후보를 빼서 화요일에 답이 정해짐
    ("lab3-inventor-6 hint hides", edit(_inventor6), ["LOGIC TUE"]),
    # 월~수 HINT가 남은 후보 1개만 가리킴
    ("early hint narrows to one", edit(_narrow_hint), ["LOGIC WED", "LOGIC WED"]),
    # 시험 lab3-beach5-1: 조건은 모래·흙·시멘트인데 문장은 흙만 말함(문장이 조건보다 좁음)
    ("lab3-beach5-1 clue narrower", edit(_beach5), ["CLUE_TEXT MON"]),
    (
        "clue says outside value",
        on_day("THU", clue="보리 발바닥에 흙과 모래가 묻었어."),
        ["CLUE_TEXT THU"],
    ),
    ("kind invalid", cond("MON", kind="MAYBE"), ["CONDITION MON"]),
]


@pytest.mark.parametrize(
    ("name", "build", "expected"), THEME_CASES, ids=[c[0] for c in THEME_CASES]
)
def test_check_theme_exact_codes(name: str, build: Callable[[], dict], expected: list[str]) -> None:
    assert codes(checks.check_theme(build(), GRADE, CODES)) == sorted(expected)


def test_llm_output_has_no_rules_out() -> None:
    """rulesOut은 표·조건으로 정해지는 값이라 LLM 출력 형식에 없다(코드가 채움)."""
    assert "rulesOut" not in GeneratedDay.model_fields


def test_fill_rules_out_from_table() -> None:
    """RULE은 허용 값 밖 후보 전부(이미 빠진 후보 포함, 후보 순서), HINT는 빈 배열."""
    filled = checks.fill_rules_out(valid_theme())
    assert [d["rulesOut"] for d in filled["days"]] == [
        [],
        [],
        ["창고", "정자"],  # 수 RULE 지붕 없음
        ["놀이터", "창고"],  # 목 RULE 땅 흙: 수요일에 빠진 창고도 다시 적음
        [],
    ]
    assert "rulesOut" not in valid_theme()["days"][0]  # 원본은 그대로


def test_fill_rules_out_overwrites_and_tolerates_broken_condition() -> None:
    theme = day_with(valid_theme(), "WED", rulesOut=["텃밭"])
    theme = day_with(theme, "THU", condition={"kind": "RULE", "feature": "소리", "allowed": ["흙"]})
    days = checks.fill_rules_out(theme)["days"]
    assert days[2]["rulesOut"] == ["창고", "정자"]  # 다른 값이 있어도 표로 다시 채움
    assert days[3]["rulesOut"] == []  # 표에 없는 특징: 비우고 사유는 check_logic이 냄
    assert "CONDITION THU" in codes(checks.check_theme(theme, GRADE, CODES))


def test_candidate_count_is_four_for_every_grade() -> None:
    assert set(checks.CANDIDATES.values()) == {4}
    three = edit(lambda t: t.update(candidates=t["candidates"][:3]))()
    assert "CANDIDATES" in codes(checks.check_theme(three, GRADE, CODES))


@pytest.mark.parametrize(
    ("value", "text", "found"),
    [
        ("좁음", "길이 좁았어", True),  # 활용형
        ("열림", "문이 열린 채였어", True),
        ("2:3", "비율이 2대3이었어", True),  # 숫자 표기
        ("모래", "바닥은 나무였어", False),
        ("흙", "흙탕물", True),
    ],
)
def test_value_in_text(value: str, text: str, found: bool) -> None:
    assert checks.value_in_text(value, text) is found


# ---------------------------------------------------------------- 미션
def mission_inputs(thinking_type: str = "ANALYZE") -> MissionDraftRequest:
    request = ThemeDraftRequest.model_validate(request_body())
    m = request.mission_for(thinking_type)  # type: ignore[arg-type]
    return MissionDraftRequest(
        standards=m.standards,
        thinking_type=m.thinking_type,
        element_codes=m.element_codes,
        grade_min=GRADE,
        grade_max=GRADE,
        input_type=m.input_type,
        previous_failures=[],
    )


def draft_of(thinking_type: str = "ANALYZE", **kw: Any) -> Draft:
    return Draft.model_validate(mission_draft(thinking_type, **kw).model_dump())


MISSION_CASES: list[tuple[str, str, dict[str, Any], list[str]]] = [
    ("valid", "ANALYZE", {}, []),
    ("valid solve", "SOLVE", {}, []),
    ("hint count grade 3", "ANALYZE", {"hints": 2}, ["HINT_COUNT"]),
    (
        "theme answer in question",
        "ANALYZE",
        {"question": "텃밭에 간 까닭을 써 보자."},
        ["THEME_ANSWER_LEAK"],
    ),
    (
        "theme answer in example",
        "ANALYZE",
        {"exampleAnswer": "텃밭이 젖어 있어서야."},
        ["THEME_ANSWER_LEAK"],
    ),
    ("kana in title", "ANALYZE", {"title": "탐정です"}, ["LANGUAGE"]),
    ("missing example answer", "ANALYZE", {"exampleAnswer": None}, ["REQUIRED"]),
    ("solve answer in hint", "SOLVE", {"hints": None}, ["LEAK"]),
    ("question too long", "ANALYZE", {"question": "가" * 400}, ["QUESTION_LENGTH"]),
]


@pytest.mark.parametrize(
    ("name", "thinking_type", "change", "expected"),
    MISSION_CASES,
    ids=[c[0] for c in MISSION_CASES],
)
def test_check_mission_exact_codes(
    name: str, thinking_type: str, change: dict, expected: list[str]
) -> None:
    s = get_settings()
    if change.get("hints", 3) is None:  # 풀이 최종 답 숫자를 생각 열기 질문에
        change = {"hints": 3}
        draft = draft_of(thinking_type, **change)
        draft = draft.model_copy(update={"hints": ["579를 떠올려 볼까?", *draft.hints[1:]]})
    elif isinstance(change.get("hints"), int):
        draft = draft_of(thinking_type, hints=change["hints"])
    else:
        draft = draft_of(thinking_type, **change)
    bad = checks.check_mission(
        valid_theme(),
        mission_inputs(thinking_type),
        draft,
        GRADE,
        s.mission_draft_question_max_chars,
        s.followup_example_overlap_chars,
    )
    assert codes(bad) == sorted(expected)


def test_mission_checks_leave_element_and_standard_code_to_learning() -> None:
    """검사 분담: 요소 code·standardCode가 요청과 달라도 ai는 막지 않는다(learning 몫)."""
    s = get_settings()
    draft = draft_of("ANALYZE")
    wrong = draft.model_copy(
        update={
            "elements": [
                e.model_copy(update={"code": "NOT_IN_REQUEST", "standard_code": "9과99-99"})
                for e in draft.elements
            ]
        }
    )
    assert (
        checks.check_mission(
            valid_theme(),
            mission_inputs(),
            wrong,
            GRADE,
            s.mission_draft_question_max_chars,
            s.followup_example_overlap_chars,
        )
        == []
    )


def test_friday_guide_lists_all_clues_after_check() -> None:
    theme = valid_theme()
    fri = checks.finish_mission(theme, "FRI", draft_of("REFLECT"))
    assert fri.guide is not None and fri.guide.count("요일:") == 5
    assert checks.finish_mission(theme, "MON", draft_of("ANALYZE")).guide is None


# ---------------------------------------------------------------- 대화
def dlg(d: str, **kw: Any) -> dict:
    return dialogue(d, **kw).model_dump()


DIALOGUE_CASES: list[tuple[str, str, Callable[[], dict], list[str]]] = [
    ("valid mon", "MON", lambda: dlg("MON"), []),
    ("valid fri", "FRI", lambda: dlg("FRI"), []),
    ("recap on monday", "MON", lambda: dlg("MON", recap="어제 단서"), ["RECAP"]),
    ("no recap tuesday", "TUE", lambda: dlg("TUE", recap=None), ["RECAP"]),
    (
        "too many lines",
        "TUE",
        lambda: dlg("TUE", lines=[{"speaker": "뭉치", "text": "가자"}] * 2),
        ["LINE_COUNT"],
    ),
    (
        "clue speaker unknown",
        "MON",
        lambda: dlg("MON", speaker="할머니"),
        ["CLUE_SPEAKER", "SPEAKER"],
    ),
    (
        "line repeats clue",
        "FRI",
        lambda: dlg(
            "FRI", lines=[{"speaker": "뭉치", "text": "보리가 지나간 길에 젖은 자국이 있대"}]
        ),
        ["CLUE_REPEATED"],
    ),
    (
        "name prefix",
        "MON",
        lambda: dlg("MON", lines=[{"speaker": "뭉치", "text": "뭉치: 가 보자"}]),
        ["SPEAKER_IN_TEXT"],
    ),
    (
        "line too long",
        "MON",
        lambda: dlg("MON", lines=[{"speaker": "뭉치", "text": "가" * 41}]),
        ["LINE_LENGTH"],
    ),
    (
        "kana line",
        "MON",
        lambda: dlg("MON", lines=[{"speaker": "뭉치", "text": "가자です"}]),
        ["LANGUAGE"],
    ),
    # 찾는 대상이 말함(이름 일부 '보리'로도 같은 대상). 시험 forest3 유형 결함을 재구성
    (
        "target speaks",
        "MON",
        lambda: dlg("MON", lines=[{"speaker": "보리", "text": "멍멍"}]),
        ["SPEAKER", "TARGET_SPEAKS"],
    ),
    (
        "self name",
        "MON",
        lambda: dlg("MON", lines=[{"speaker": "뭉치", "text": "뭉치는 궁금해"}]),
        ["SELF_NAME"],
    ),
    (
        "theme answer in line",
        "MON",
        lambda: dlg("MON", lines=[{"speaker": "뭉치", "text": "텃밭에 가 볼까"}]),
        ["THEME_ANSWER_LEAK"],
    ),
]


@pytest.mark.parametrize(
    ("name", "d", "build", "expected"), DIALOGUE_CASES, ids=[c[0] for c in DIALOGUE_CASES]
)
def test_check_dialogue_exact_codes(
    name: str, d: str, build: Callable[[], dict], expected: list[str]
) -> None:
    s = get_settings()
    bad = checks.check_dialogue(
        valid_theme(),
        d,
        build(),
        draft_of(checks.DAY_TYPE[d]),
        GRADE,
        s.followup_example_overlap_chars,
    )
    assert codes(bad) == sorted(expected)


def test_dialogue_lines_put_clue_verbatim_last() -> None:
    theme = valid_theme()
    lines = checks.dialogue_lines(dlg("TUE"), checks.day_clue(theme, "TUE"))
    assert lines[0]["speaker"] == "뭉치" and lines[-1] == {
        "speaker": "지호",
        "text": theme["days"][1]["clue"],
    }


# ---------------------------------------------------------------- 검토·응답
def test_check_review_splits_fail_warn_and_shape() -> None:
    review = story_review({"CLUE_LOGIC": "FAIL", "GRADE_VOCAB": "WARN"}).model_dump()
    fails, warns, shape = checks.check_review(review, checks.REVIEW_IDS)
    assert [x["id"] for x in fails] == ["CLUE_LOGIC"] and [x["id"] for x in warns] == [
        "GRADE_VOCAB"
    ]
    assert shape == []
    review["items"].pop()
    assert checks.check_review(review, checks.REVIEW_IDS)[2][0].startswith("REVIEW_SHAPE")


def test_public_theme_drops_internal_fields() -> None:
    public = checks.public_theme(checks.fill_rules_out(copy.deepcopy(valid_theme())))
    assert not {"features", "target"} & set(public)
    assert not {"clueType", "condition", "evidence"} & set(public["days"][0])
    assert public["days"][2]["rulesOut"] == ["창고", "정자"]
