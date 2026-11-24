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
    DISCOVERY,
    HOOK,
    MATERIAL,
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
    # 금요일 조건을 모래로: 정답(흙)이 빠지고 놀이터는 어떤 RULE로도 빠지지 않음
    fri = theme["days"][4]
    fri["condition"]["allowed"] = ["모래"]
    fri["clue"] = "일지에 보리 발바닥에 모래가 묻어 있었다고 적혔어."


def _stale_rule(theme: dict) -> None:
    # 목요일 RULE(땅 모래·흙): 빼는 창고는 월요일에 이미 빠졌고 남은 놀이터·텃밭은 모두 맞음
    theme["days"][3].update(
        # #782 설계 v3: 허용 값이 둘이면 빠지는 값을 부정으로(늘어놓으면 CLUE_TEXT)
        clue="보리 발에 묻은 가루는 시멘트가 아니었어.",
        condition={"kind": "RULE", "feature": "땅", "allowed": ["모래", "흙"]},
    )


# #782 테마 짜임: valid_theme은 월 RULE(물기 젖음: 창고·정자) → 화 STORY(사건 단서) → 수 HINT(지붕
# 없음) → 목 STORY → 금 RULE(땅 흙: 놀이터). 월요일 힌트는 늘 특징 값 전부라(CLUE_EMPTY) 아래 상황은
# 화~금에서 만듦
def _early_finish(theme: dict) -> None:
    # 월 RULE(창고·정자) → 화 RULE(땅 흙: 놀이터): 마지막 틀린 후보가 화요일에 빠짐. 그래서 수요일
    # 힌트가 남은 후보 하나(텃밭)만 가리킴. 금요일은 같은 단서를 되풀이하지 않게 사건 단서로
    days = theme["days"]
    days[1].update(
        clue="보리 발바닥에 흙이 묻어 있었대.",
        condition={"kind": "RULE", "feature": "땅", "allowed": ["흙"]},
    )
    days[4].update(
        clue="일지에 보리가 저녁에 골목을 지나갔다고 적혔어.",
        condition={"kind": "STORY", "feature": "", "allowed": []},
    )


def _thursday_finish(theme: dict) -> None:
    # 목 RULE(땅 흙: 놀이터) → 금 STORY: 마지막 틀린 후보가 목요일에 빠짐(#782 테마 짜임: 금요일이
    # 어야 함, 전에는 통과)
    days = theme["days"]
    days[3].update(
        clue="보리 발바닥에 흙이 묻어 있었어.",
        condition={"kind": "RULE", "feature": "땅", "allowed": ["흙"]},
    )
    days[4].update(
        clue="일지에 보리가 골목 안쪽으로 갔다고 적혔어.",
        condition={"kind": "STORY", "feature": "", "allowed": []},
    )


def _never_out(theme: dict) -> None:
    # 금요일을 HINT로(땅 모래·흙): 놀이터가 어떤 RULE로도 빠지지 않음
    theme["days"][4].update(
        clue="일지에 보리 발바닥에 묻은 건 시멘트가 아니었다고 적혔어.",
        condition={"kind": "HINT", "feature": "땅", "allowed": ["모래", "흙"]},
    )


def _inventor6(theme: dict) -> None:
    # 화요일 HINT(땅 흙·시멘트): 남은 놀이터(모래)를 빼는 내용인데 HINT라고 적음(남은 후보도 텃밭
    # 하나만 가리킴). 금요일 RULE(땅 흙)과 같은 단서가 되지 않게 시멘트를 함께 둠
    tue = theme["days"][1]
    tue.update(
        clue="보리 발에 묻은 건 모래가 아니었대.",
        condition={"kind": "HINT", "feature": "땅", "allowed": ["흙", "시멘트"]},
    )


def _narrow_hint(theme: dict) -> None:
    # 목요일 HINT(땅 흙·시멘트): 남은 놀이터·텃밭 중 놀이터를 빼는 HINT이자 텃밭 하나만 가리킴
    # (#782 테마 짜임: 월~목 힌트는 남은 후보 2개 이상)
    theme["days"][3].update(
        clue="보리 발자국에 묻은 건 모래가 아니었어.",
        condition={"kind": "HINT", "feature": "땅", "allowed": ["흙", "시멘트"]},
    )


def _repeat_hint(theme: dict) -> None:
    # 목요일 HINT(지붕 없음): 수요일과 같은 특징·같은 허용 값이라 새로 알려 주는 것이 없음
    theme["days"][3].update(
        clue="보리 발자국이 지붕이 없는 길로 이어졌어.",
        condition={"kind": "HINT", "feature": "지붕", "allowed": ["없음"]},
    )


def _new_value_hint(theme: dict) -> None:
    # 목요일 HINT(땅 모래·흙): 금요일(땅 흙)과 특징은 같아도 허용 값이 달라 되풀이가 아님
    theme["days"][3].update(
        clue="보리 발자국에 묻은 건 시멘트가 아니었어.",
        condition={"kind": "HINT", "feature": "땅", "allowed": ["모래", "흙"]},
    )


def _beach5(theme: dict) -> None:
    # 화요일 HINT(땅: 모래·흙, 남은 놀이터·텃밭 모두 맞음)인데 문장은 흙만 말해 표보다 좁음
    tue = theme["days"][1]
    tue["condition"] = {"kind": "HINT", "feature": "땅", "allowed": ["모래", "흙"]}
    tue["clue"] = "보리 발에 흙이 묻어 있었대."


def _all_values(theme: dict) -> None:
    # 화요일 HINT(땅: 모래·흙)인데 두 바닥을 '모두' 지났다고 씀(조건은 그중 한 곳)
    _beach5(theme)
    theme["days"][1]["clue"] = "보리 발이 모래·흙 바닥을 모두 스쳤대."


def _one_of_values(theme: dict) -> None:
    _beach5(theme)
    theme["days"][1]["clue"] = "보리 발은 모래나 흙 바닥 중 한 곳을 밟았대."


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
    ("candidate one char", edit(lambda t: _rename(t, "창고", "샘")), ["CANDIDATES"]),
    ("days out of order", edit(lambda t: t["days"].reverse()), ["DAYS"]),
    ("wrong thinking type", on_day("MON", thinkingType="SOLVE"), ["DAYS MON"]),
    ("clue empty", on_day("WED", clue=""), ["CLUE_TEXT WED", "REQUIRED"]),
    # 흔적 날 단서는 대상 낱말을 넣으므로 46자(기준안), 그 밖은 40자(#535 6차)
    (
        "trace clue too long",
        on_day("MON", clue="보리 발자국이 젖어 있었어" + "가" * 33),
        ["LENGTH"],
    ),
    ("trace clue up to 46", on_day("MON", clue="보리 발자국이 젖어 있었어" + "가" * 30), []),
    ("clue too long", on_day("TUE", clue="보리 털이 비에 젖어 반짝였대" + "가" * 26), ["LENGTH"]),
    ("trace clue without target", on_day("MON", clue="발자국이 젖어 있었어."), ["CLUE_OWNER MON"]),
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
    ("unknown condition feature", cond("WED", feature="소리"), ["CONDITION WED"]),
    ("allowed outside table", cond("WED", allowed=["얼음"]), ["CONDITION WED"]),
    # 정답을 빼는 단서
    ("clue excludes answer", edit(_answer_out), ["LOGIC", "LOGIC FRI"]),
    # 이미 빠진 후보만 빼는 RULE(learning 결정적 단서 계산과 어긋남)
    ("rule removes nothing new", edit(_stale_rule), ["LOGIC THU"]),
    # 단서 문장의 증거와 evidence 종류가 다름(실측: 사진 단서인데 SIGHTING)
    (
        "photo clue but sighting",
        lambda: day_with(valid_theme(), "WED", clue="사진 속 보리는 지붕이 없는 곳에 있었어."),
        ["CLUE_EVIDENCE WED"],
    ),
    (
        "record without record word",
        lambda: day_with(valid_theme(), "FRI", clue="보리 발바닥에 흙이 묻어 있었어."),
        ["CLUE_EVIDENCE FRI"],
    ),
    # 마지막 틀린 후보가 화요일에 빠짐
    ("last wrong out too early", edit(_early_finish), ["LOGIC", "LOGIC WED"]),
    # #782 테마 짜임: 마지막 틀린 후보는 금요일에 빠짐(목요일도 이름)
    ("last wrong out on thursday", edit(_thursday_finish), ["LOGIC"]),
    # 어떤 RULE로도 빠지지 않는 틀린 후보
    ("wrong candidate never out", edit(_never_out), ["LOGIC"]),
    # 시험 lab3-inventor-6: HINT가 남은 후보를 빼서 화요일에 답이 정해짐
    ("lab3-inventor-6 hint hides", edit(_inventor6), ["LOGIC TUE", "LOGIC TUE"]),
    # 월~목 HINT가 남은 후보 1개만 가리킴(#782 테마 짜임: 목요일까지)
    ("early hint narrows to one", edit(_narrow_hint), ["LOGIC THU", "LOGIC THU"]),
    # #782 테마 짜임: 앞 요일과 같은 단서(같은 특징·같은 허용 값)는 CLUE_REPEAT
    ("hint repeats earlier clue", edit(_repeat_hint), ["CLUE_REPEAT THU"]),
    ("same feature new values is not repeat", edit(_new_value_hint), []),
    # 사건 단서(STORY)는 후보를 빼지 않고 후보 이름·특징 표 값을 말하지 않음
    (
        "story clue names candidate",
        on_day("TUE", clue="보리가 공을 물고 놀이터 쪽으로 달려갔대."),
        ["STORY_VALUE TUE"],
    ),
    (
        "story clue tells feature value",
        on_day("THU", clue="보리 발자국이 흙길 안쪽으로 이어졌어."),
        ["STORY_VALUE THU"],
    ),
    (
        # 그날 쓰지 않는 값이라도 표 값이면 몰래 후보를 가름(시멘트: 창고)
        "story clue tells table value",
        on_day("TUE", clue="보리가 시멘트 바닥 쪽으로 달려갔대."),
        ["STORY_VALUE TUE"],
    ),
    # 시험 lab3-beach5-1: 조건은 모래·흙·시멘트인데 문장은 흙만 말함(문장이 조건보다 좁음)
    ("lab3-beach5-1 clue narrower", edit(_beach5), ["CLUE_TEXT TUE"]),
    (
        "clue says outside value",
        on_day("FRI", clue="일지에 보리 발바닥에 흙과 모래가 묻었다고 적혔어."),
        ["CLUE_TEXT FRI"],
    ),
    ("kind invalid", cond("TUE", kind="MAYBE"), ["CONDITION TUE"]),
    # 단서 말투(실측 2026-11-11 글 검토 CLUE_LOGIC): 허용 값 여럿을 '모두' 있었다고 쓰거나 RULE을
    # 흐리게 씀
    # #782 설계 v3: 허용 값을 늘어놓는 것도 CLUE_TEXT(빠지는 값을 부정으로)
    ("clue says all allowed values", edit(_all_values), ["CLUE_TEXT TUE", "CLUE_WORDING TUE"]),
    # #782 설계 v3(사용자 결정 2026-11-21): 직접 본 사람은 하나만 봄 — 'A나 B'로 늘어놓으면
    # CLUE_TEXT
    ("clue lists one of allowed values", edit(_one_of_values), ["CLUE_TEXT TUE"]),
    (
        "rule clue hedges",
        on_day("MON", clue="보리 발자국이 젖어 있었을 수도 있어."),
        ["CLUE_WORDING MON"],
    ),
    ("hint clue may hedge", on_day("WED", clue="보리는 지붕이 없는 곳으로 갔을 수도 있대."), []),
    ("straight is not hedge", on_day("WED", clue="보리는 지붕이 없는 반듯한 곳으로 갔대."), []),
    # 시작·종료 영상 콘티
    ("intro cuts three", edit(lambda t: t["introCuts"].pop()), ["CUTS"]),
    ("outro cuts five", edit(lambda t: t["outroCuts"].append(dict(t["outroCuts"][0]))), ["CUTS"]),
    (
        "cut caption too long",
        edit(lambda t: t["introCuts"][0].update(caption="가" * 31)),
        ["LENGTH"],
    ),
    ("cut action empty", edit(lambda t: t["outroCuts"][1].update(action=" ")), ["REQUIRED"]),
    (
        "answer in intro caption",
        edit(lambda t: t["introCuts"][3].update(caption="텃밭에 있을까?")),
        ["ANSWER_LEAK"],
    ),
    (
        "answer in intro scene",
        edit(lambda t: t["introCuts"][2].update(scene="텃밭 옆 길모퉁이")),
        ["ANSWER_LEAK"],
    ),
    (
        "answer in outro cut is fine",
        edit(lambda t: t["outroCuts"][2].update(caption="텃밭이었어!")),
        [],
    ),
    # 시작 콘티 뭉치 표정: 1·2(평소 모습·사건)는 뭉치가 없어 none, 3·4(출동·도착)는 none이 아님
    (
        "mungchi in intro cut 1",
        edit(lambda t: t["introCuts"][0].update(mungchiMood="smile")),
        ["CUT_MOOD"],
    ),
    (
        "mungchi missing in intro cut 3",
        edit(lambda t: t["introCuts"][2].update(mungchiMood="none")),
        ["CUT_MOOD"],
    ),
    (
        "mungchi mood unknown",
        edit(lambda t: t["outroCuts"][3].update(mungchiMood="angry")),
        ["CUT_MOOD"],
    ),
    (
        # 종료 콘티는 4컷 모두 뭉치가 나옴(그림이 항상 뭉치를 그려서, 점검 C9)
        "outro cut without mungchi",
        edit(lambda t: t["outroCuts"][1].update(mungchiMood="none")),
        ["CUT_MOOD"],
    ),
    # 뭉치는 팔이 없어 손·팔다리 동작은 사람만, 화면 쪽으로 다가오거나 밖으로 나가지 않음
    # (실측 2026-11-11: 그런 컷에서 영상에 팔·다리가 생기거나 확대돼 잘림)
    (
        "mungchi hands over target",
        edit(lambda t: t["outroCuts"][2].update(action="뭉치가 지호에게 보리를 건넨다")),
        ["CUT_ACTION"],
    ),
    (
        "everyone raises hands includes mungchi",
        edit(lambda t: t["outroCuts"][3].update(action="모두가 두 손을 들어 기뻐한다")),
        ["CUT_ACTION"],
    ),
    (
        "mungchi jumps in scene",
        edit(lambda t: t["introCuts"][3].update(scene="뭉치가 길모퉁이에서 뛰며 웃는다")),
        ["CUT_ACTION"],
    ),
    (
        "mungchi runs toward camera",
        edit(lambda t: t["introCuts"][2].update(action="뭉치가 화면 쪽으로 다가온다")),
        ["CUT_ACTION"],
    ),
    (
        # 실측 2026-11-11 auto4b: 씨앗 '농부(밀짚모자)'의 '밀짚'이 '짚'에 걸려 줄거리 9번 실패
        "straw hat is not a hand action",
        edit(lambda t: t["introCuts"][2].update(scene="밀짚모자를 쓴 뭉치가 마을 길 위에 있다")),
        [],
    ),
    (
        # '모아'는 손 동작이 아닌 말에도 쓰여 목록에서 뺌(#535 7차), 손을 쓰면 '두 손'으로 잡힘
        "gathering clues is not a hand action",
        edit(lambda t: t["outroCuts"][0].update(scene="뭉치가 다섯 흔적을 모아 정답을 떠올린다")),
        [],
    ),
    (
        "mungchi joins both hands",
        edit(lambda t: t["outroCuts"][0].update(scene="뭉치가 두 손을 모아 기뻐한다")),
        ["CUT_ACTION"],
    ),
    (
        "person gestures while mungchi watches",
        edit(lambda t: t["outroCuts"][2].update(action="뭉치 곁에서 지호가 손을 흔든다")),
        [],
    ),
    (
        # 시작 1·2컷은 뭉치가 없어 손 동작은 보지 않음(다가오기만 봄)
        "hands fine in intro cut without mungchi",
        edit(lambda t: t["introCuts"][0].update(action="모두 함께 손을 흔든다")),
        [],
    ),
    # 증거 발견 줄·수사 연결 문장: 필수·길이, 단서 결론(허용 값)·후보·정답 금지
    ("discovery empty", on_day("MON", discovery=" "), ["REQUIRED"]),
    ("discovery too long", on_day("TUE", discovery="가" * 41), ["LENGTH"]),
    ("mission hook empty", on_day("WED", missionHook=""), ["REQUIRED"]),
    ("mission hook too long", on_day("THU", missionHook="가" * 41), ["LENGTH"]),
    (
        "discovery tells clue value",
        on_day("FRI", discovery="가게 일지에 흙 묻은 발자국 이야기가 있어!"),
        ["CLUE_EARLY FRI"],
    ),
    # 장면 메모도 그날 단서 결론을 말하면 CLUE_EARLY(#535 닫기 5차, 칸 고쳐 쓰기)
    (
        "scene note tells clue value",
        on_day("FRI", sceneNote="뭉치와 지호가 흙길 옆 가게에서 일지를 살펴본다."),
        ["CLUE_EARLY FRI"],
    ),
    (
        "scene note without clue value",
        on_day("FRI", sceneNote="뭉치와 지호가 가게 앞에서 일지를 살펴본다."),
        [],
    ),
    # 예전(#535)에는 수사 연결 문장이 배울 개념을 말하는 자리라 막지 않았다. #782 C안부터는
    # 증거의 한 부분(단서 특징 값과 무관)을 가리키고 웹 '오늘 장면'에서 문제 전에 읽으므로 그날
    # 단서 결론이면 칸 고쳐 쓰기(사용자 결정 2026-11-19)
    (
        "mission hook states clue value",
        on_day("WED", missionHook="지붕 없음을 알려면 특징을 살펴봐야 해. 도와줄래?"),
        ["CLUE_EARLY WED"],
    ),
    # 1자 줄기(젖음→젖)는 보지 않음(오탐이 많음), 정확히 같은 낱말만
    ("one char stem is not clue early", on_day("MON", discovery="젖은 발자국이 찍혀 있어!"), []),
    (
        "discovery names candidate",
        on_day("MON", discovery="놀이터 앞에 보리 발자국이 있어!"),
        ["ANSWER_LEAK"],
    ),
    (
        "mission hook names answer",
        on_day("FRI", missionHook="텃밭 사진을 보기 전에 이번 주 수사를 돌아보자."),
        ["ANSWER_LEAK"],
    ),
]


@pytest.mark.parametrize(
    ("name", "build", "expected"), THEME_CASES, ids=[c[0] for c in THEME_CASES]
)
def test_check_theme_exact_codes(name: str, build: Callable[[], dict], expected: list[str]) -> None:
    assert codes(checks.check_theme(build(), GRADE, CODES)) == sorted(expected)


@pytest.mark.parametrize(
    ("bad", "expected"),
    [
        (
            [
                "LENGTH TUE.clue 44자 > 40",
                "LENGTH WED.missionHook 47자 > 40",
                "LENGTH title 25자 > 20",
            ],
            ["TUE.clue", "WED.missionHook", "title"],
        ),
        (["LENGTH outroCuts3.caption 33자 > 30"], ["outroCuts3.caption"]),
        (["CLUE_EARLY TUE discovery에 그날 단서 결론(허용 값 ['흙'])"], ["TUE.discovery"]),
        (["CLUE_EARLY THU sceneNote에 그날 단서 결론(허용 값 ['흙'])"], ["THU.sceneNote"]),
        (["ANSWER_LEAK MON.missionHook에 후보 이름 ['창고']"], ["MON.missionHook"]),
        (["ANSWER_LEAK intro에 정답 이름"], ["intro"]),
        # 이야기 틀·정답 논리·표에 닿는 사유가 하나라도 있으면 칸 고쳐 쓰기 없음
        (["LENGTH TUE.clue 44자 > 40", "LOGIC 정답 텃밭이 MON 단서로 빠짐"], []),
        (["ANSWER_LEAK characters.텃밭지기에 정답 이름"], []),
        (["ANSWER_LEAK introCuts1.scene에 정답 이름"], []),
        # 콘티 뭉치 동작은 그 칸만 고쳐 씀(정답 유출과 달리)
        (
            [
                "CUT_ACTION outroCuts3.action 뭉치가 손·팔다리를 쓰는 동작(건넨), 손짓은 사람만",
                "CUT_ACTION introCuts3.scene 화면 쪽으로 다가오거나 나가는 동작(달려온)",
            ],
            ["outroCuts3.action", "introCuts3.scene"],
        ),
        # 단서 문장의 허용 값 낱말 문제도 그 단서만 고쳐 씀(#535 7차)
        (["CLUE_TEXT TUE clue 단서 문장에 허용 값 낱말 없음"], ["TUE.clue"]),
        # 정답 논리와 섞이면 줄거리부터 다시
        (["CLUE_TEXT TUE clue 단서 문장에 허용 값 낱말 없음", "LOGIC TUE 단서가 정답을 뺌"], []),
        # 단서 말투는 그 단서만 고쳐 씀
        (["CLUE_WORDING WED clue 후보를 빼는 단서를 흐리게 씀('수도 있')"], ["WED.clue"]),
        # 증거 종류 불일치도 그 단서만 고쳐 씀(글자 수 초과와 섞여도 줄거리를 다시 만들지 않음)
        (
            ["LENGTH MON.clue 45자 > 40", "CLUE_EVIDENCE FRI clue 증거 종류가 다름"],
            ["MON.clue", "FRI.clue"],
        ),
        # 배정과 다른 증거 종류는 그날 단서·증거 발견 줄·수사 연결 문장만 고쳐 씀(#535)
        (
            [
                "CLUE_EVIDENCE WED clue 증거 종류가 배정과 다름(배정 흔적 TRACE, 지금 SIGHTING)",
                "CLUE_EVIDENCE WED discovery 증거 종류가 배정과 다름(배정 흔적 TRACE, "
                "지금 SIGHTING)",
                "CLUE_EVIDENCE WED missionHook 증거 종류가 배정과 다름(배정 흔적 TRACE, 지금 "
                "SIGHTING)",
            ],
            ["WED.clue", "WED.discovery", "WED.missionHook"],
        ),
    ],
)
def test_fix_targets_only_single_field_reasons(bad: list[str], expected: list[str]) -> None:
    targets = checks.fix_targets(bad)
    assert list(targets) == expected
    assert all(r in sum(targets.values(), []) for r in bad) or not targets


def test_text_at_and_set_text_at_paths() -> None:
    theme = valid_theme()
    checks.set_text_at(theme, "WED.missionHook", "새 문장")
    checks.set_text_at(theme, "outroCuts2.caption", "새 문구")
    checks.set_text_at(theme, "title", "새 제목")
    assert checks.theme_day(theme, "WED")["missionHook"] == "새 문장"
    assert theme["outroCuts"][1]["caption"] == "새 문구" and theme["title"] == "새 제목"
    assert checks.text_at(theme, "outroCuts2.caption") == "새 문구"
    assert (checks.text_max("WED.clue"), checks.text_max("introCuts1.caption")) == (40, 30)
    checks.set_text_at(theme, "outroCuts3.action", "뭉치가 곁에서 통통 튄다")
    assert theme["outroCuts"][2]["action"] == "뭉치가 곁에서 통통 튄다"
    assert checks.text_max("outroCuts3.action") == checks.CUT_TEXT_MAX


def test_llm_output_has_no_rules_out() -> None:
    """rulesOut은 표·조건으로 정해지는 값이라 LLM 출력 형식에 없다(코드가 채움)."""
    assert "rulesOut" not in GeneratedDay.model_fields


def test_fill_rules_out_from_table() -> None:
    """RULE은 허용 값 밖 후보 전부(이미 빠진 후보 포함, 후보 순서), HINT·STORY는 빈 배열."""
    filled = checks.fill_rules_out(valid_theme())
    assert [d["rulesOut"] for d in filled["days"]] == [
        ["창고", "정자"],  # 월 RULE 물기 젖음
        [],  # 화 STORY(사건 단서, #782 테마 짜임): 특징이 없어 아무 후보도 빼지 않음
        [],
        [],  # 목 STORY
        ["놀이터", "창고"],  # 금 RULE 땅 흙: 월요일에 빠진 창고도 다시 적음
    ]
    assert "rulesOut" not in valid_theme()["days"][0]  # 원본은 그대로


def test_fill_rules_out_overwrites_and_tolerates_broken_condition() -> None:
    theme = day_with(valid_theme(), "MON", rulesOut=["텃밭"])
    theme = day_with(theme, "THU", condition={"kind": "RULE", "feature": "소리", "allowed": ["흙"]})
    days = checks.fill_rules_out(theme)["days"]
    assert days[0]["rulesOut"] == ["창고", "정자"]  # 다른 값이 있어도 표로 다시 채움
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


@pytest.mark.parametrize(
    ("value", "text", "found"),
    [
        ("흙", "흙탕물", True),  # 정확히 일치
        ("흙", "바닥에 흙이 묻었어", True),
        ("게", "활동 순서를 설명해 볼게.", False),  # 한 글자 값은 낱말 첫머리만(끝말 오탐 뺌)
        ("게", "게 발자국이 보여", True),
        ("2:3", "비율이 2대3이었어", True),
        ("미끄러움", "길이 미끄러웠어", True),  # 줄기 '미끄러'(3자) 일치
        ("초록색", "초록 모자를 봤어", True),  # 줄기 '초록'(2자)
        ("좁음", "길이 좁았어", False),  # 1자 줄기 '좁'은 보지 않음(value_in_text와 다름)
        ("젖음", "젖은 발자국", False),
        ("없음", "지붕이 없음", True),
        ("모래", "바닥은 나무였어", False),
    ],
)
def test_mentions_value_needs_two_char_stem(value: str, text: str, found: bool) -> None:
    """CLUE_EARLY 비교(증거 발견 줄·수사 연결 문장·대화가 같이 씀)."""
    assert checks.mentions_value(value, text) is found


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
        {"question": f"{MATERIAL['MON']} 텃밭에 간 까닭을 써 보자."},  # 지문은 그대로(#782)
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
    (
        "question too long",
        "ANALYZE",
        {"question": MATERIAL["MON"] + "가" * 400},
        ["QUESTION_LENGTH"],
    ),
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


# ---------------------------------------------------------------- 대화
def dlg(**kw: Any) -> dict:
    return dialogue(**kw).model_dump()


def say(text: str, speaker: str = "지호") -> list[dict[str, str]]:
    return [{"speaker": speaker, "text": text}]


def four(text: str, speaker: str = "지호") -> list[dict[str, str]]:
    """기본 대화 4줄 중 첫 줄만 바꾼 대화 줄(#782 테마 짜임: 모든 학년 4~5줄)."""
    base = [x.model_dump() for x in dialogue().lines]
    return [{"speaker": speaker, "text": text}, *base[1:]]


DIALOGUE_CASES: list[tuple[str, str, Callable[[], dict], list[str]]] = [
    ("valid mon", "MON", lambda: dlg(), []),
    ("valid fri", "FRI", lambda: dlg(), []),
    ("five lines ok", "TUE", lambda: dlg(lines=say("응") + four("가자")), []),
    ("too many lines", "TUE", lambda: dlg(lines=say("응") * 2 + four("가자")), ["LINE_COUNT"]),
    ("too few lines", "MON", lambda: dlg(lines=four("가자")[1:]), ["LINE_COUNT"]),
    ("unknown speaker", "MON", lambda: dlg(lines=four("여기야", "할머니")), ["SPEAKER"]),
    # 단서는 미션을 마친 뒤 보여 주므로 대화 줄이 그날 허용 값을 말하면 안 됨
    (
        "line tells clue value",
        "FRI",
        lambda: dlg(lines=four("발바닥에 흙이 묻었네")),
        ["CLUE_EARLY FRI"],
    ),
    # 뒤 요일 값은 괜찮고, 앞 요일 단서 결과는 안 됨(#782 테마 짜임 PREV_CLUE: 순서 없이 풀 수 있음)
    ("later day value is fine", "MON", lambda: dlg(lines=four("흙길을 따라가 보자")), []),
    (
        "line tells earlier clue",
        "THU",
        lambda: dlg(lines=four("어제 지붕이 없음을 알았지")),
        ["PREV_CLUE THU"],
    ),
    ("name prefix", "MON", lambda: dlg(lines=four("뭉치: 가 보자", "뭉치")), ["SPEAKER_IN_TEXT"]),
    ("line too long", "MON", lambda: dlg(lines=four("가" * 41)), ["LINE_LENGTH"]),
    ("kana line", "MON", lambda: dlg(lines=four("가자です")), ["LANGUAGE"]),
    # 찾는 대상이 말함(이름 일부 '보리'로도 같은 대상). 시험 forest3 유형 결함을 재구성
    (
        "target speaks",
        "MON",
        lambda: dlg(lines=four("멍멍", "보리")),
        ["SPEAKER", "TARGET_SPEAKS"],
    ),
    ("self name", "MON", lambda: dlg(lines=four("뭉치는 궁금해", "뭉치")), ["SELF_NAME"]),
    (
        "theme answer in line",
        "MON",
        lambda: dlg(lines=four("텃밭에 가 볼까")),
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


def test_owner_name_in_target_is_not_target_speaking() -> None:
    """대상 이름에 주인 이름이 들어가도('지호의 강아지 보리') 등장인물 지호는 대상이 아님
    (실측 repo-auto3-1 오탐). 이름 일부 '보리'는 여전히 대상."""
    theme = theme_with(target="지호의 강아지 보리")
    assert not checks.is_target(theme, "지호") and not checks.is_target(theme, "뭉치")
    assert checks.is_target(theme, "보리")
    s = get_settings()
    bad = checks.check_dialogue(
        theme,
        "MON",
        dlg(lines=four("같이 찾아 줘", "지호")),
        draft_of("ANALYZE"),
        3,
        s.followup_example_overlap_chars,
    )
    assert "TARGET_SPEAKS" not in codes(bad)
    assert checks.dialogue_speakers(theme, [{"speaker": "지호"}, {"speaker": "보리"}]) == ["지호"]


def test_hook_problems_catch_answer_example_and_clue_conclusion() -> None:
    """미션 뒤 고쳐 쓴 수사 연결 문장이 문제 답·예시 답·단서 결론을 말하면 잡음(#535 닫기 3차)."""
    theme, overlap = valid_theme(), get_settings().followup_example_overlap_chars
    assert checks.hook_problems(theme, "FRI", HOOK["FRI"], draft_of("ANALYZE"), overlap) == []
    early = checks.hook_problems(theme, "FRI", "흙 자국을 풀려면 도와줄래?", draft_of(), overlap)
    assert early == ["CLUE_EARLY 그날 단서 결론(허용 값 ['흙'])"]
    example = "미끄러웠으니 천천히 걸어야 해. 도와줄래?"  # 예시 답과 12자 넘게 겹침
    assert checks.hook_problems(theme, "FRI", example, draft_of(), overlap) == [
        "LEAK EXAMPLE_ANSWER"
    ]
    solve = checks.hook_problems(theme, "FRI", "579개를 세어 줄래?", draft_of("SOLVE"), overlap)
    assert "LEAK ANSWER_KEY" in solve


def test_full_speakers_restores_shortened_character_name() -> None:
    """띄어 쓴 등장인물 이름의 뒷부분만 쓴 화자는 원래 이름으로(한 명에게만 맞을 때, 닫기 3차)."""
    theme = valid_theme()
    theme["characters"] = [*theme["characters"], {"name": "캠핑장 관리인", "look": "모자"}]
    generated = {
        "lines": [{"speaker": "관리인", "text": "어서 와."}, {"speaker": "선생님", "text": "응."}],
    }
    out = checks.full_speakers(theme, generated)
    assert [x["speaker"] for x in out["lines"]] == ["캠핑장 관리인", "선생님"]  # 안 맞으면 그대로
    assert generated["lines"][0]["speaker"] == "관리인"  # 받은 값은 바꾸지 않음


@pytest.mark.parametrize(
    ("feature", "ok"),
    [
        ("바닥 재질", True),
        ("바닥 물기", True),
        ("받침 모양", True),
        ("땅", True),
        ("빛", False),
        ("그늘 여부", False),
        ("주변 소리", False),
        ("입구까지 거리", False),
        ("지붕", False),
    ],
)
def test_traceable_feature(feature: str, ok: bool) -> None:
    """흔적으로 남을 수 있는 특징(기준안, #535 6차)."""
    assert checks.traceable(feature) is ok


def _planned(kinds: dict[str, str], features: dict[str, str]) -> dict:
    theme = valid_theme()
    theme["evidencePlan"] = {
        d: {"kind": k, "medium": "사진" if k == "RECORD" else None} for d, k in kinds.items()
    }
    for d in theme["days"]:
        d["condition"] = {**d["condition"], "feature": features[d["day"]]}
    return theme


def test_fit_evidence_plan_moves_trace_to_traceable_day() -> None:
    """흔적 날 특징이 흔적에 남지 않으면 흔적이 맞는 목격 날과 배정을 통째로 바꿈."""
    kinds = {"MON": "TRACE", "TUE": "SIGHTING", "WED": "SIGHTING", "THU": "TRACE", "FRI": "RECORD"}
    feats = {"MON": "빛", "TUE": "주변 소리", "WED": "바닥 재질", "THU": "땅", "FRI": "물기"}
    theme = _planned(kinds, feats)
    assert checks.fit_evidence_plan(theme) == ["MON", "WED"]
    plan = theme["evidencePlan"]
    types = {d["day"]: d["clueType"] for d in valid_theme()["days"]}
    assert theme["days"][0]["clueType"] == types["WED"]  # 단서 종류도 함께 바꿈
    assert theme["days"][2]["clueType"] == types["MON"]
    assert [plan[d]["kind"] for d in checks.DAYS] == [
        "SIGHTING",
        "SIGHTING",
        "TRACE",
        "TRACE",
        "RECORD",
    ]


def test_fit_evidence_plan_without_traceable_day_becomes_sighting() -> None:
    """흔적이 맞는 날이 없으면 그 흔적 날을 목격으로 바꿈(기록 매체 배정은 그대로)."""
    kinds = {"MON": "TRACE", "TUE": "SIGHTING", "WED": "SIGHTING", "THU": "RECORD", "FRI": "RECORD"}
    feats = {"MON": "빛", "TUE": "주변 소리", "WED": "그늘", "THU": "거리", "FRI": "냄새"}
    theme = _planned(kinds, feats)
    assert checks.fit_evidence_plan(theme) == ["MON"]
    assert theme["evidencePlan"]["MON"] == {"kind": "SIGHTING", "medium": None}
    assert theme["evidencePlan"]["THU"]["kind"] == "RECORD"


def test_fit_evidence_plan_keeps_fitting_plan() -> None:
    theme = valid_theme()
    theme["evidencePlan"] = checks.evidence_plan("seed")
    before = copy.deepcopy(theme["evidencePlan"])
    feats = {d["day"]: "바닥 재질" for d in theme["days"]}
    for d in theme["days"]:
        d["condition"] = {**d["condition"], "feature": feats[d["day"]]}
    assert checks.fit_evidence_plan(theme) == [] and theme["evidencePlan"] == before


def test_repair_logic_changes_fewest_conditions() -> None:
    """정답 논리가 틀리면 특징 표는 두고 그 요일 조건만 바꿔 맞춤(#535 6차)."""
    theme = day_with(
        valid_theme(), "FRI", condition={"kind": "HINT", "feature": "땅", "allowed": ["흙"]}
    )
    assert any(r.startswith("LOGIC") for r in checks.check_theme(theme, GRADE, CODES))
    assert checks.repair_logic(theme) == ["FRI"]
    assert theme["days"][4]["condition"] == {"kind": "RULE", "feature": "땅", "allowed": ["흙"]}
    assert not [r for r in checks.check_theme(theme, GRADE, CODES) if r.startswith("LOGIC")]
    assert theme["days"][4]["rulesOut"]  # rulesOut도 새 조건으로 채움
    # 사건 단서 날(화·목)은 특징이 없어 바꾸지 않음(#782 테마 짜임)
    assert [checks.is_story(d["condition"]) for d in theme["days"]] == [
        False,
        True,
        False,
        True,
        False,
    ]


def test_repair_logic_leaves_valid_or_unfixable_theme() -> None:
    assert checks.repair_logic(valid_theme()) == []
    theme = valid_theme()
    answer = theme["answer"]
    for f in theme["features"]:  # 정답과 틀린 후보 하나가 모든 특징에서 같으면 조건으로 못 가름
        vals = {v["candidate"]: v for v in f["values"]}
        other = next(c for c in theme["candidates"] if c != answer)
        vals[other]["value"] = vals[answer]["value"]
    before = copy.deepcopy(theme["days"])
    assert checks.repair_logic(theme) == [] and theme["days"] == before


def test_elimination_summary_follows_table() -> None:
    text = checks.elimination_summary(valid_theme())
    assert text.startswith("월요일 ") and text.endswith(f"남은 정답 {valid_theme()['answer']}")


def test_dialogue_lines_are_model_lines_only() -> None:
    """대화는 모델이 쓴 줄 그대로(#782 테마 짜임: 끝에 증거 발견 줄·수사 연결 문장을 붙이지 않음),
    단서·앞 요일 요약 줄은 없음. 줄 수는 모든 학년 4~5줄."""
    theme = valid_theme()
    lines = checks.dialogue_lines(dlg())
    assert lines == [x.model_dump() for x in dialogue().lines] and len(lines) == 4
    assert not any(x["clue"] in y["text"] for x in theme["days"] for y in lines)
    assert set(checks.DIALOGUE_LINES.values()) == {(4, 5)}


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
    theme = checks.fill_rules_out(copy.deepcopy(valid_theme()))
    theme["evidencePlan"] = checks.evidence_plan("seed")
    assert "evidencePlan" not in checks.public_theme(theme)  # 증거 배정도 내부 칸(#535)
    assert not {"target", "introCuts", "outroCuts"} & set(public)
    assert not {"clueType", "condition", "evidence", "discovery", "missionHook"} & set(
        public["days"][0]
    )
    assert public["days"][0]["rulesOut"] == ["창고", "정자"]


def test_public_theme_has_feature_table_and_clue_feature() -> None:
    """#647: 후보 특징 표는 이름·후보별 값만(standardCode 빼고), 요일은 그날 특징 이름."""
    public = checks.public_theme(checks.fill_rules_out(copy.deepcopy(valid_theme())))
    assert [f["name"] for f in public["features"]] == ["땅", "지붕", "물기"]
    assert public["features"][0] == {
        "name": "땅",
        "values": [
            {"candidate": "놀이터", "value": "모래"},
            {"candidate": "텃밭", "value": "흙"},
            {"candidate": "창고", "value": "시멘트"},
            {"candidate": "정자", "value": "흙"},
        ],
    }
    assert all("standardCode" not in f for f in public["features"])
    # 사건 단서 날(화·목, #782 테마 짜임)은 특징이 없어 null(learning·웹이 이미 처리)
    assert [d["clueFeature"] for d in public["days"]] == ["물기", None, "지붕", None, "땅"]
    assert public["days"][1]["rulesOut"] == [] and public["days"][3]["rulesOut"] == []
    # 특징 표가 없는 줄거리(예전 저장본 등)는 null
    bare = checks.fill_rules_out(copy.deepcopy(valid_theme()))
    bare["features"] = []
    assert checks.public_theme(bare)["features"] is None


def test_dialogue_leak_checks_only_llm_lines() -> None:
    """끝 두 줄(코드가 넣는 증거 발견 줄·수사 연결 문장)에 미션 금지어가 있어도 대화는 실패하지
    않음. 대화를 다시 만들어도 바뀌지 않는 줄이라서(점검 C10). LLM 줄에 있으면 실패."""
    theme = valid_theme()
    word = DISCOVERY["MON"].split()[0]
    draft = draft_of("ANALYZE").model_copy(update={"forbidden_terms": [word]})
    s = get_settings()
    ok = checks.check_dialogue(
        theme, "MON", dlg(lines=say("같이 가 보자")), draft, GRADE, s.followup_example_overlap_chars
    )
    assert "LEAK" not in codes(ok)
    bad = checks.check_dialogue(
        theme,
        "MON",
        dlg(lines=say(f"{word} 말이야")),
        draft,
        GRADE,
        s.followup_example_overlap_chars,
    )
    assert "LEAK" in codes(bad)


def test_theme_answer_leak_reason_names_the_word() -> None:
    """정답 낱말 유출 사유에 걸린 낱말을 적어 다시 생성 때 피하게 함(점검 C13)."""
    theme = valid_theme()
    s = get_settings()
    bad = checks.check_dialogue(
        theme,
        "MON",
        dlg(lines=say("텃밭에 가 볼까")),
        draft_of("ANALYZE"),
        GRADE,
        s.followup_example_overlap_chars,
    )
    assert any(r.startswith("THEME_ANSWER_LEAK") and "'텃밭'" in r for r in bad)


def test_example_fix_only_for_written_answers() -> None:
    """예시 답 고쳐 쓰기는 서술·논술·풀이만(고르기·순서·분류는 정답 키라 못 고침, 점검 C16)."""
    from app.theme_draft.nodes.mission import only_example

    bad = ["MISSION_REVIEW EXAMPLE_COMPLETE 사유"]
    assert only_example(bad, "NARRATIVE") and only_example(bad, "SOLUTION_STEPS")
    assert not only_example(bad, "CHOICE") and not only_example(bad, "CLASSIFICATION")


# --- 증거 종류·기록 매체 코드 배정 (#535) ------------------------------------------------
def test_evidence_plan_is_fixed_per_seed_and_keeps_mix() -> None:
    """같은 씨앗이면 같은 배정. 흔적·목격 각 1개 이상·기록 2개 이하, 기록 날마다 서로 다른 매체."""
    plans = [
        checks.evidence_plan(f"2026-11-{n:02d}-{g}") for n in range(1, 29) for g in (3, 4, 5, 6)
    ]
    for plan in plans:
        kinds = [slot["kind"] for slot in plan.values()]
        assert list(plan) == list(checks.DAYS)
        assert kinds.count("TRACE") >= 1 and kinds.count("SIGHTING") >= 1
        assert kinds.count("RECORD") <= 2
        media = [slot["medium"] for slot in plan.values() if slot["kind"] == "RECORD"]
        assert len(set(media)) == len(media) and set(media) <= set(checks.RECORD_MEDIA)
        assert all(slot["medium"] is None for slot in plan.values() if slot["kind"] != "RECORD")
    assert checks.evidence_plan("2026-11-16-3") == checks.evidence_plan("2026-11-16-3")
    assert len({tuple(s["kind"] for s in p.values()) for p in plans}) > 10  # 요일 배치가 섞임
    record = sum(s["kind"] == "RECORD" for p in plans for s in p.values())
    assert record / (5 * len(plans)) < 0.45  # 수정 전 49~53%보다 적게(기대값 33%)


def planned(**slots: tuple[str, str | None]) -> dict[str, Any]:
    """fixture 증거 종류 그대로의 배정에 slots(요일=(종류, 매체))만 바꾼 줄거리."""
    theme = valid_theme()
    plan = {
        d["day"]: {
            "kind": d["evidence"]["kind"],
            "medium": "일지" if d["evidence"]["kind"] == "RECORD" else None,
        }
        for d in theme["days"]
    }
    for day, (kind, medium) in slots.items():
        plan[day] = {"kind": kind, "medium": medium}
    theme["evidencePlan"] = plan
    return theme


def test_valid_theme_matches_default_request_plan() -> None:
    """시험 줄거리의 증거 종류·매체가 기본 요청의 코드 배정과 같음(그래프 시험이 배정 검사를
    통과)."""
    from app.theme_draft.prompts import evidence_plan_for

    plan = evidence_plan_for(ThemeDraftRequest.model_validate(request_body()))
    assert plan == planned()["evidencePlan"]
    assert checks.check_theme(planned(), GRADE, CODES) == []


def test_evidence_kind_against_plan() -> None:
    """종류가 배정과 다르면 그날 세 칸 사유, 기록 매체 낱말이 없으면 단서·증거 발견 줄 사유."""
    bad = checks.check_theme(planned(WED=("TRACE", None)), GRADE, CODES)
    assert [r.split("(")[0] for r in bad] == [
        "CLUE_EVIDENCE WED clue 증거 종류가 배정과 다름",
        "CLUE_EVIDENCE WED discovery 증거 종류가 배정과 다름",
        "CLUE_EVIDENCE WED missionHook 증거 종류가 배정과 다름",
    ]
    assert list(checks.fix_targets(bad)) == ["WED.clue", "WED.discovery", "WED.missionHook"]
    media = checks.check_theme(planned(FRI=("RECORD", "녹음")), GRADE, CODES)
    assert media == [
        "CLUE_EVIDENCE FRI clue 기록 매체가 배정과 다름(배정 매체 '녹음' 낱말을 씀)",
        "CLUE_EVIDENCE FRI discovery 기록 매체가 배정과 다름(배정 매체 '녹음' 낱말을 씀)",
    ]
    assert list(checks.fix_targets(media)) == ["FRI.clue", "FRI.discovery"]
    # 영상은 '녹화'도 같은 매체
    video = day_with(planned(FRI=("RECORD", "영상")), "FRI", discovery="가게 녹화 영상을 찾았어!")
    video = day_with(video, "FRI", clue="녹화에 보리 발바닥에 흙이 묻어 있었다고 남았어.")
    assert checks.check_theme(video, GRADE, CODES) == []


def test_record_clue_reason_not_doubled_with_plan() -> None:
    """기록 날 단서에 기록 낱말이 아예 없으면 배정 매체 사유 하나만(같은 칸 사유를 두 번 내지
    않음)."""
    theme = day_with(planned(), "FRI", clue="보리 발바닥에 흙이 묻어 있었어.")
    bad = checks.check_theme(theme, GRADE, CODES)
    assert codes(bad) == ["CLUE_EVIDENCE FRI"]
    assert "기록 매체가 배정과 다름" in bad[0]
    # 배정이 없으면(예전 줄거리) 문장↔종류 검사 그대로
    assert codes(
        checks.check_theme(
            day_with(valid_theme(), "FRI", clue="보리 발바닥에 흙이 묻어 있었어."), GRADE, CODES
        )
    ) == ["CLUE_EVIDENCE FRI"]


def test_apply_evidence_plan_sets_kind_keeps_when() -> None:
    theme = checks.apply_evidence_plan(planned(WED=("RECORD", "메모")))
    wed = checks.theme_day(theme, "WED")
    assert wed["evidence"] == {"kind": "RECORD", "when": "보리가 사라진 날 오후"}
    assert checks.theme_day(theme, "MON")["evidence"]["kind"] == "TRACE"
    assert checks.apply_evidence_plan(valid_theme()) == valid_theme()  # 배정 없으면 그대로


def test_names_target_accepts_one_letter_word_joined_with_target_word() -> None:
    # #535 7차 auto3d: 대상 '대회에 낼 떡 모양 틀', 단서 '떡틀 자국…'이 CLUE_OWNER 오탐
    theme = {"target": "대회에 낼 떡 모양 틀"}
    assert checks.target_words(theme) == ["틀", "모양"]
    assert checks.names_target(theme, "떡틀 자국이 남은 받침은 나무였어.")
    assert checks.names_target(theme, "모양틀 자국은 둥글었어.")
    assert checks.names_target(theme, "틀 자국이 남았어.")
    assert not checks.names_target(theme, "자국이 남은 받침은 나무였어.")
    # 대상 이름에 없는 낱말과 붙은 한 글자는 그대로 보지 않음
    assert not checks.names_target({"target": "바닷가 게"}, "설명해 볼게, 자국은 젖었어.")


def test_outro_recap_follows_table_and_compose_puts_it_before_story() -> None:
    # #535 7차: 종료 이야기 정리는 코드가 특징 표로 계산해 붙임(LLM이 쓰면 표와 다르게 요약).
    # 같은 틀 다섯 줄은 딱딱해서 세 문장으로 이음(사용자 2026-11-16)
    theme = checks.fill_rules_out(valid_theme())
    recap = checks.outro_recap(theme)
    remaining, outs, hints, stories = list(theme["candidates"]), [], [], []
    for d in theme["days"]:
        out = [c for c in d["rulesOut"] if c in remaining]
        remaining = [c for c in remaining if c not in out]
        if out:
            outs.append((checks.DAY_KO[d["day"]], out))
        else:
            (stories if checks.is_story(d["condition"]) else hints).append(checks.DAY_KO[d["day"]])
    assert (hints, stories) == (["수"], ["화", "목"])
    sentences = recap.split(". ")
    assert sentences[0].startswith(f"{outs[0][0]}요일 단서로 ")
    positions = [sentences[0].index("·".join(cs)) for _, cs in outs]
    assert positions == sorted(positions)  # 빠진 날 차례대로 한 문장
    assert all(f"{day}요일" in sentences[1] for day in hints)
    assert "남은 후보를 가르지는 못했지만 정답과 딱 맞았어" in sentences[1]
    assert not any(f"{day}요일" in sentences[1] for day in stories)
    # 사건 단서 날은 따로 한 문장(#782 테마 짜임)
    assert sentences[2] == "화요일과 목요일 단서는 사건이 어떻게 벌어졌는지 알려 줬어"
    assert recap.endswith(f"그래서 {theme['answer']}만 남았어.")
    assert recap.count("단서로") == 1  # 같은 틀을 되풀이하지 않음
    theme["outroStory"] = "보리는 텃밭에서 낮잠을 자고 있었어."
    checks.compose_outro(theme)
    assert theme["outro"] == f"{recap} 보리는 텃밭에서 낮잠을 자고 있었어."
    # 마무리 장면이 '…요.'로 끝나면 정리도 같은 말투
    theme["outroStory"] = "보리는 텃밭에서 낮잠을 자고 있었어요."
    checks.compose_outro(theme)
    assert "빠졌어요." in theme["outro"] and "남았어요." in theme["outro"]
    assert "알려 줬어요." in theme["outro"]
    # 사람이 쓴 테마(outroStory 없음)는 그대로
    plain = valid_theme()
    assert checks.compose_outro(plain)["outro"] == valid_theme()["outro"]


def test_outro_story_with_weekday_recap_is_fixed_in_place() -> None:
    theme = checks.fill_rules_out(valid_theme())
    theme["outroStory"] = "월요일 단서로 먼저 하나를 뺐어. 보리를 찾았어."
    checks.compose_outro(theme)
    bad = checks.check_theme(theme, 3, set())
    recap = [r for r in bad if r.startswith("OUTRO_RECAP")]
    assert recap and checks.fix_targets(recap) == {"outro": recap}
    # 칸 고쳐 쓰기는 마무리 장면만 읽고 쓰며, 쓰면 정리를 다시 붙임
    assert checks.text_at(theme, "outro") == theme["outroStory"]
    assert checks.text_max("outro", theme) == checks.OUTRO_STORY_MAX
    checks.set_text_at(theme, "outro", "뭉치는 보리를 예린에게 돌려줬어.")
    assert theme["outroStory"] == "뭉치는 보리를 예린에게 돌려줬어."
    assert theme["outro"].startswith(checks.outro_recap(theme)) and theme["outro"].endswith(
        "돌려줬어."
    )
    assert not [r for r in checks.check_theme(theme, 3, set()) if r.startswith("OUTRO_RECAP")]


def test_clue_gets_no_time_from_code_and_length_has_no_time_allowance() -> None:
    """단서 앞 그때 시각·'그때' 붙이기는 #782 테마 짜임에서 뺐다(사용자 결정 2026-11-19, 단서는 발견
    장면 대사). 글자 수 상한에도 시각 몫이 없다."""
    day = {
        "day": "MON",
        "clue": "틀 자국이 남은 받침은 나무였어.",
        "evidence": {"kind": "TRACE", "when": "오후 3시, 떡 대회 준비를 마친 때"},
    }
    theme = {"days": [dict(day)]}
    assert checks.finalize_texts(theme)["days"][0]["clue"] == day["clue"]
    assert checks.day_text_max(day, "clue") == checks.TRACE_CLUE_MAX
    assert checks.day_text_max({**day, "evidence": {"kind": "RECORD"}}, "clue") == checks.LINE_MAX


def test_repair_logic_adds_answer_value_when_many_days_exclude_answer() -> None:
    # #535 8차 auto4c: 월~목 네 날이 모두 정답을 빼 3일 상한에 걸려 줄거리를 다시 만들었음
    theme = checks.fill_rules_out(valid_theme())
    table, _ = checks.feature_table(theme)
    answer = theme["answer"]
    broken = copy.deepcopy(theme)
    # 화·목은 사건 단서라(#782 테마 짜임) 특징이 없어 예전 valid_theme 조건(화 HINT 물기, 목 RULE
    # 땅)을 넣어 네 날 모두 정답을 빼게 함
    broken["days"][1]["condition"] = {"kind": "HINT", "feature": "물기", "allowed": []}
    broken["days"][3]["condition"] = {"kind": "RULE", "feature": "땅", "allowed": []}
    for d in broken["days"][:4]:
        vals = table[d["condition"]["feature"]]
        others = sorted(set(vals.values()) - {vals[answer]})
        d["condition"] = {**d["condition"], "allowed": others[:1]}
    assert [
        r
        for r in checks.check_logic(broken, broken["candidates"], answer, broken["days"])
        if r.startswith("LOGIC")
    ]
    changed = checks.repair_logic(broken)
    assert set(changed) >= {"MON", "TUE", "WED", "THU"}
    assert not [
        r
        for r in checks.check_logic(broken, broken["candidates"], answer, broken["days"])
        if r.startswith(("LOGIC", "CONDITION"))
    ]
    for d in broken["days"]:
        assert table[d["condition"]["feature"]][answer] in d["condition"]["allowed"]


def test_generated_day_with_empty_text_is_invalid_output() -> None:
    # #535 8차: 빈 칸 응답은 형식 밖(검증 오류 → LLM_INVALID_OUTPUT → 테마 클라이언트가 한 번 더)
    day = {**valid_theme()["days"][0]}
    day.pop("rulesOut", None)
    GeneratedDay.model_validate(day)
    with pytest.raises(ValueError):
        GeneratedDay.model_validate({**day, "discovery": " "})


@pytest.mark.parametrize(
    ("text", "grade", "expected"),
    [
        ("두 원의 넓이를 구해 비교해 보자.", 4, ["넓이"]),
        ("두 원의 넓이를 구해 비교해 보자.", 5, []),
        ("3/5 ÷ 3/4로 확인해.", 5, ["분수의 나눗셈"]),
        ("3/5 ÷ 3/4로 확인해.", 6, []),
        ("0.35와 0.40을 비교해.", 3, ["소수 둘째 자리"]),
        ("0.3과 0.4를 비교해.", 3, []),
        ("직육면체의 겉넓이를 구해.", 5, ["겉넓이·부피"]),
        ("원주율 3.14로 원의 넓이를 구해.", 6, []),
        ("넓이는 36π㎡야.", 6, ["π 기호"]),
        ("비율로 나타내 봐.", 5, ["비율·백분율"]),
        ("다른 생각도 있을까?", 3, []),
        ("기온이 12°C에서 15°C로 올랐어.", 3, []),
        ("각도기로 각도를 재 봐.", 3, ["각도"]),
        ("땅의 넓이를 구해 봐.", 4, ["넓이"]),
    ],
)
def test_math_ahead_by_grade(text: str, grade: int, expected: list[str]) -> None:
    # #535 9차 글 검토 GRADE_VOCAB: 목요일 수학이 학년보다 앞선 개념(기준안 표 MATH_AHEAD)
    assert checks.math_ahead([text], grade) == expected


def test_outro_recap_follows_story_register_including_da_style() -> None:
    theme = checks.fill_rules_out(valid_theme())
    theme["outroStory"] = "뭉치는 텃밭에서 보리를 찾았다."
    recap = checks.outro_recap(theme)
    assert "빠졌다." in recap and "딱 맞았다." in recap and recap.endswith("남았다.")
    assert "어떻게 벌어졌는지 알려 줬다." in recap  # 사건 단서 문장도 같은 말투
    assert "빠졌어" not in recap
