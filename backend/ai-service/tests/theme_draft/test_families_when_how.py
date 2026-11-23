"""④ 때·길·방법 (#634, 설계 ai.md 17.8.17): 시간 탐정·어느 길로 왔을까·무엇을 타고 왔을까.

마을 규칙표·탈것 사실표, '없는 값' 단서 금지(CLUE_ABSENT)와 있는 값으로 가르기(FACT_TABLE), 시작
이야기 끝 마을 규칙(compose_intro), 시간 탐정의 시각 붙이기 끄기·엔딩 전 시각(TIME_WORD), 여객선은
물가에서만(VEHICLE_PLACE), 그림에 시계·후보 탈것 감추기.
"""

import copy
from typing import Any

import pytest

from app.mission_draft.models import Draft
from app.theme_draft import checks, families, prompts
from app.theme_draft.models import ThemeDraftRequest
from tests.theme_draft.fixtures import day, feature, mission_draft, valid_theme
from tests.theme_draft.helpers import request_body

SEEDS = {
    "WHEN": "줄거리: 시간 탐정 / 뭉치 역할: 탐정(체크무늬 모자·나비넥타이) / "
    "장소: 아파트 화단 / 밝힐 것: 화단에 물을 준 때",
    "ROUTE": "줄거리: 어느 길로 왔을까 / 뭉치 역할: 우체부(우체부 모자·가방끈) / "
    "장소: 골목 동네 / 손에 든 것: 할머니가 보낸 택배 상자",
    "VEHICLE": "줄거리: 무엇을 타고 왔을까 / 뭉치 역할: 역무원(역무원 모자·호루라기 목걸이) / "
    "장소: 바닷가 마을 / 밝힐 것: 삼촌이 타고 온 탈것",
}
TIMES = ["아침 7시", "낮 12시", "저녁 7시", "밤 9시"]
VEHICLES = ["자전거", "킥보드", "버스", "기차"]


def codes(reasons: list[str]) -> list[str]:
    return sorted(r.split(" ")[0] for r in reasons)


def table_features(table: families.FactTable, cands: list[str]) -> list[dict[str, Any]]:
    return [feature(name, {c: table.fact(c, name) or "" for c in cands}) for name in table.features]


WHEN_INTRO = "지호네 화단이 흠뻑 젖어 있었어요. 탐정 뭉치가 출동해요."


def when_theme() -> dict[str, Any]:
    """시간 탐정 줄거리(정답 저녁 7시, check_theme 통과). 월 RULE 켜진 가로등 → 아침 7시·낮 12시,
    금 RULE 열린 빵집 → 밤 9시. 화~목은 남은 저녁 7시·밤 9시를 새로 알려 줄 특징이 없어(가로등은
    월요일과 같은 단서, 빵집 문은 값 전부, 종소리는 없는 값) 사건 단서(#782 테마 짜임). 흔적 날
    없음(목격·기록만)."""
    theme = copy.deepcopy(valid_theme())
    theme |= {
        "storyType": "WHEN",
        "target": "화단에 물을 준 때",
        "bigQuestion": "화단에 물을 준 건 언제였을까?",
        "candidates": list(TIMES),
        "answer": "저녁 7시",
        "features": table_features(families.TIMES, TIMES),
        "days": [
            day(
                "MON",
                "물을 줄 때 켜진 가로등 불빛이 보였대.",
                "목격",
                "RULE",
                "가로등",
                ["켜진 가로등"],
                "SIGHTING",
            ),
            day(
                "TUE",
                "그때 찍힌 사진에 물뿌리개를 든 사람이 있었어.",
                "기록",
                "STORY",
                "",
                [],
                "RECORD",
            ),
            day(
                "WED",
                "물 주던 사람이 화단 둘레를 천천히 돌았대.",
                "시각",
                "STORY",
                "",
                [],
                "SIGHTING",
            ),
            day(
                "THU",
                "물을 다 준 사람이 물뿌리개를 담장 옆에 두고 갔대.",
                "냄새",
                "STORY",
                "",
                [],
                "SIGHTING",
            ),
            day(
                "FRI",
                "그때 찍힌 사진에 열린 빵집이 함께 보였어.",
                "소리",
                "RULE",
                "빵집 문",
                ["열린 빵집"],
                "RECORD",
            ),
        ],
    }
    for d in theme["days"]:
        d["evidence"]["when"] = "화단에 물을 준 그때"
        # 미션 지문(#782)도 엔딩 전 글이라 시각을 쓰지 않음(TIME_WORD)
        d["missionMaterial"] = "이웃의 말: 물뿌리개 소리가 나고 잠시 뒤 화단에서 물 냄새가 퍼졌어."
    # #782 설계 v4: 시간 탐정 시작 이야기에는 때를 가리키는 말이 없음(valid_theme의 '비가 그친
    # 오후'는 정답 시각 후보와 어긋나거나 미리 알려 줌 — TIME_WORD)
    theme["intro"] = WHEN_INTRO
    theme["introStory"] = theme["intro"]
    theme["outroCuts"][0]["caption"] = f"뭉치: 알았다! {theme['answer']}!"  # #779 종료 1컷은 정답
    return checks.compose_intro(theme)


def vehicle_theme() -> dict[str, Any]:
    """탈것 찾기 줄거리(정답 버스, check_theme 통과). 월 RULE 소리 → 자전거·킥보드, 금 RULE 표 →
    기차, 수·목은 사건 단서(#782 테마 짜임: 마지막 후보는 금요일에, 앞 요일 단서를 되풀이하지
    않음). 없는 값(바퀴 자국 없음)은 단서로 쓰지 않음."""
    theme = copy.deepcopy(valid_theme())
    theme |= {
        "storyType": "VEHICLE",
        "target": "삼촌이 타고 온 탈것",
        "bigQuestion": "삼촌은 무엇을 타고 왔을까?",
        "candidates": list(VEHICLES),
        "answer": "버스",
        "features": table_features(families.VEHICLES, VEHICLES),
        "days": [
            day(
                "MON",
                "삼촌이 올 때 드르륵 소리도 따르릉 소리도 아니었어.",  # #782 v3 부정형
                "목격",
                "RULE",
                "들린 소리",
                ["부릉 소리", "덜컹덜컹 소리"],
                "SIGHTING",
            ),
            day(
                "TUE",
                "사진 속 삼촌 손에 든 건 헬멧이 아니었어.",
                "기록",
                "HINT",
                "들고 온 것",
                ["교통카드", "좌석표"],
                "RECORD",
            ),
            day(
                "WED",
                "이웃이 삼촌이 큰길 쪽에서 가방을 메고 걸어오는 걸 봤대.",
                "소리",
                "STORY",
                "",
                [],
                "SIGHTING",
            ),
            day(
                "THU",
                "삼촌이 골목 입구에서 모자를 벗고 땀을 닦았대.",
                "잠김",
                "STORY",
                "",
                [],
                "SIGHTING",
            ),
            day(
                "FRI",
                "사진 속 삼촌 손에 교통카드가 있었어.",
                "시각",
                "RULE",
                "들고 온 것",
                ["교통카드"],
                "RECORD",
            ),
        ],
    }
    theme["outroCuts"][0]["caption"] = f"뭉치: 알았다! {theme['answer']}!"  # #779 종료 1컷은 정답
    return theme


# ---------------------------------------------------------------- 등록표·씨앗
@pytest.mark.parametrize("code", list(SEEDS))
def test_when_how_seed_topic_gives_story_type(code: str) -> None:
    found = families.parse_topic(SEEDS[code])
    assert found is not None and found.code == code and found.family == "WHEN_HOW"
    user = prompts.plan_user(ThemeDraftRequest.model_validate(request_body(topic=SEEDS[code])), [])
    assert f"storyType: {code}" in user


def test_fact_tables_values_do_not_contain_each_other() -> None:
    for table in (families.TIMES, families.VEHICLES):
        for i, name in enumerate(table.features):
            values = {row[i] for row in table.rows.values()}
            assert not [
                (a, b)
                for a in values
                for b in values
                if a != b and a.replace(" ", "") in b.replace(" ", "")
            ], (table.name, name)
        assert table.absent <= {v for row in table.rows.values() for v in row}
        # 후보 이름은 2~10자(CANDIDATE_CHARS — 한 글자 '배'를 '여객선'으로)
        assert all(2 <= len(c.replace(" ", "")) <= 10 for c in table.rows)


@pytest.mark.parametrize(
    "table",
    [
        families.ANIMALS,
        families.GIFTS,
        families.INGREDIENTS,
        families.TIMES,
        families.VEHICLES,
    ],
)
def test_fact_values_do_not_contain_candidate_names(table: families.FactTable) -> None:
    # 값에 후보 이름이 들어가면 그 값을 쓰는 단서가 정답 이름을 말해 ANSWER_LEAK(칸 고쳐 쓰기로도 못
    # 고침, 처음 탈것 표의 '버스표'·'기차표')
    values = {v for row in table.rows.values() for v in row}
    names = [c.replace(" ", "") for c in table.rows]
    names += [c.split()[-1] for c in table.rows]  # 머리 낱말(CANDIDATE_NAME과 같은 낱말)
    assert not [(v, n) for v in values for n in names if len(n) >= 2 and n in v.replace(" ", "")], (
        table.name
    )


def test_blocked_candidates_only_for_same_rows() -> None:
    # 오전 10시·오후 3시는 세 값이 같고, 낮 12시와는 종소리(정답 쪽이 없는 값)로만 갈림
    assert families.TIMES.blocked() == {
        "오전 10시": ["낮 12시", "오후 3시"],
        "오후 3시": ["오전 10시", "낮 12시"],
    }
    assert families.VEHICLES.blocked() == {}
    rule = families.TIMES.absent_rule()
    assert (
        "정답이 오전 10시면 후보에 낮 12시·오후 3시를 두지 않음" in rule and "CLUE_ABSENT" in rule
    )
    assert families.WHEN.no_trace and not families.VEHICLE.no_trace and not families.ROUTE.no_trace


def test_when_plan_has_no_trace_and_other_types_keep_plan() -> None:
    plan = {"MON": {"kind": "TRACE", "medium": None}, "TUE": {"kind": "RECORD", "medium": "사진"}}
    assert checks.plan_for_type(plan, families.WHEN) == {
        "MON": {"kind": "SIGHTING", "medium": None},
        "TUE": {"kind": "RECORD", "medium": "사진"},
    }
    assert checks.plan_for_type(plan, families.VEHICLE) is plan
    request = ThemeDraftRequest.model_validate(request_body(topic=SEEDS["WHEN"]))
    assert "TRACE" not in {s["kind"] for s in prompts.evidence_plan_for(request).values()}


# ---------------------------------------------------------------- 시간 탐정
def test_when_theme_passes_and_intro_gets_town_rule() -> None:
    theme = when_theme()
    assert checks.check_theme(theme, 3) == []
    assert theme["intro"].endswith(families.TOWN_NOTES[0])  # 시작 이야기가 '…요.'로 끝남
    # 마을 규칙의 '낮 12시'·'오전 9시'는 후보 이름·시각 검사에 걸리지 않음(모델 몫만 봄)
    assert checks.intro_story(theme) == WHEN_INTRO
    # 다시 합쳐도 한 번만 붙고, 모델이 규칙을 옮겨 써도 한 번만
    again = checks.compose_intro({**theme, "introStory": theme["intro"]})
    assert again["intro"].count("가로등은") == 1


def test_compose_intro_matches_story_ending() -> None:
    plain = {**when_theme(), "introStory": "물이 고여 있었다."}
    assert checks.compose_intro(plain)["intro"].endswith("켜진다.")
    casual = {**when_theme(), "introStory": "누가 물을 줬을까"}
    assert checks.compose_intro(casual)["intro"].endswith("켜져.")
    lost = {**valid_theme(), "introStory": "x"}  # 규칙 없는 종류는 그대로
    assert checks.compose_intro(lost)["intro"] == valid_theme()["intro"]


def test_when_intro_length_counts_model_part_and_fix_rewrites_it() -> None:
    theme = checks.compose_intro({**when_theme(), "introStory": "가" * 190 + "요."})
    assert len(theme["intro"]) > checks.TEXT_MAX["intro"]  # 규칙만큼 길어져도
    assert not [r for r in checks.check_theme(theme, 3) if r.startswith("LENGTH intro")]
    assert checks.text_at(theme, "intro") == checks.intro_story(theme)
    checks.set_text_at(theme, "intro", "화단이 젖어 있었어요. 탐정 뭉치가 출동해요.")
    assert theme["intro"] == "화단이 젖어 있었어요. 탐정 뭉치가 출동해요. " + families.TOWN_NOTES[0]
    long = {**when_theme(), "introStory": "가" * 201}
    assert "LENGTH intro 201자 > 200" in checks.check_theme(checks.compose_intro(long), 3)


def test_clue_time_is_not_added() -> None:
    """단서 앞 시각·'그때' 붙이기는 #782 테마 짜임에서 모든 종류에서 뺌(단서는 발견 장면 대사)."""
    for theme in (when_theme(), copy.deepcopy(valid_theme())):
        theme["days"][1]["evidence"]["when"] = "오후 3시"
        before = [d["clue"] for d in theme["days"]]
        assert [d["clue"] for d in checks.finalize_texts(theme)["days"]] == before


def test_when_time_words_before_ending_are_fixed_by_field() -> None:
    theme = when_theme()
    theme["days"][1]["sceneNote"] = "오전 9시 수업 전에 화단을 살펴보는 장면"
    theme["days"][2]["clue"] = "세 시에 켜진 가로등 불빛이 보였대."
    bad = checks.check_theme(theme, 3)
    assert [r for r in bad if r.startswith("TIME_WORD")] == [
        "TIME_WORD TUE.sceneNote에 시각 '9시'(그때가 정답이라 엔딩 전 글에 시각을 쓰지 않음 — "
        "'그 일을 할 때'·'아침에'처럼)",
        "TIME_WORD WED.clue에 시각 '세 시'(그때가 정답이라 엔딩 전 글에 시각을 쓰지 않음 — "
        "'그 일을 할 때'·'아침에'처럼)",
    ]
    assert set(checks.fix_targets([r for r in bad if r.startswith("TIME_WORD")])) == {
        "TUE.sceneNote",
        "WED.clue",
    }
    # 시각이 아닌 말은 걸리지 않음
    for text in ("두 시간 동안 물을 줬대", "두 시장 사이 화단", "12시간 전"):
        assert not checks.TIME_WORD.search(text), text
    # 시각을 붙이는 종류는 검사하지 않음
    lost = day_note(valid_theme(), "오전 9시 수업 전")
    assert not [r for r in checks.check_theme(lost, 3) if r.startswith("TIME_WORD")]


def day_note(theme: dict[str, Any], note: str) -> dict[str, Any]:
    out = copy.deepcopy(theme)
    out["days"][1]["sceneNote"] = note
    return out


def test_absent_value_clue_regenerates() -> None:
    theme = when_theme()
    mon = theme["days"][0]
    mon["condition"] = {"kind": "HINT", "feature": "종소리", "allowed": ["종 안 울림"]}
    mon["clue"] = "물을 줄 때 종 안 울림이었대."
    bad = checks.check_theme(theme, 3)
    assert any(r.startswith("CLUE_ABSENT MON") for r in bad)
    assert checks.fix_targets([r for r in bad if r.startswith("CLUE_ABSENT")]) == {}


def test_answer_must_split_from_candidates_by_present_values() -> None:
    cands = ["아침 7시", "오전 10시", "오후 3시", "밤 9시"]
    theme = {
        **when_theme(),
        "candidates": cands,
        "answer": "오전 10시",
        "features": table_features(families.TIMES, cands),
    }
    bad = [r for r in checks.fact_table_problems(theme) if "가를 수" in r]
    assert bad and "['오후 3시']" in bad[0] and "종 안 울림" in bad[0]
    # 동물처럼 없는 값이 없는 표도 같은 검사(가를 특징을 빼면 걸림)
    ok = {**theme, "candidates": ["아침 7시", "오전 10시", "저녁 7시", "밤 9시"]}
    ok["features"] = table_features(families.TIMES, ok["candidates"])
    assert not [r for r in checks.fact_table_problems(ok) if "가를 수" in r]


def test_repair_logic_does_not_add_absent_values() -> None:
    theme = when_theme()
    table, _ = checks.feature_table(theme)
    found = checks._search_logic_fix(theme, table, theme["days"])
    # 이미 맞는 논리라 바꿀 것이 없거나, 바꿔도 없는 값을 허용 값에 넣지 않음
    for d in found[0] if found else []:
        assert "종 안 울림" not in (d.get("condition") or {}).get("allowed", [])


def test_when_prompts_hide_times_and_clocks() -> None:
    theme = when_theme()
    rules = families.type_rules(families.WHEN)
    assert families.TOWN_NOTES[0] in rules and "TIME_WORD" in rules
    text = prompts.story_text(theme, "MON", 3)
    assert "밝힐 것: 화단에 물을 준 때" in text and "아직 찾지 못했으므로" not in text
    assert "7시" in text  # 쓰지 말 낱말(후보 머리 낱말)
    plain = Draft.model_validate(mission_draft("ANALYZE").model_dump())
    assert "밝힐 것(그 일은 이야기에 나와도 되지만" in prompts.dialogue_user(
        theme, "MON", plain, 3, []
    )
    cut = prompts.cut_image_prompt(theme, "INTRO", 2, theme["introCuts"][1], [])
    assert "Do not draw any clock or watch" in cut and "화단에 물을 준 때" not in cut
    outro = prompts.cut_image_prompt(theme, "OUTRO", 3, theme["outroCuts"][2], [])
    assert "clock" not in outro and "The answer," not in outro
    mission = prompts.mission_image_prompt(theme, "MON", plain, [])
    assert (
        "Do not draw any clock or watch" in mission and "itself is not the evidence" not in mission
    )
    video = prompts.video_prompt(theme, "INTRO", 1, theme["introCuts"][0], [])
    assert "Do not show any clock or watch" in video and "Do not show 화단" not in video
    assert prompts.mission_target(theme) is None and prompts.mission_shows_target(theme)
    rules_fix = prompts.fix_rules(theme, "intro")
    assert any("코드가 붙이므로" in r for r in rules_fix)
    assert any("어떤 시각" in r for r in rules_fix)


# ---------------------------------------------------------------- 탈것·길
def test_vehicle_theme_passes_and_hides_vehicles() -> None:
    theme = vehicle_theme()
    assert checks.check_theme(theme, 3) == []
    assert checks.target_words(theme) == ["탈것", "바퀴"]
    bad = checks.check_theme(day_note(theme, "기차역 앞에서 삼촌을 만나는 장면"), 3)
    assert bad == ["CANDIDATE_NAME TUE.sceneNote에 후보 탈것 이름 ['기차'](엔딩 전 글)"]
    cut = prompts.cut_image_prompt(theme, "INTRO", 2, theme["introCuts"][1], [])
    assert "Do not draw any of these vehicles: 자전거, 킥보드, 버스, 기차." in cut
    outro = prompts.cut_image_prompt(theme, "OUTRO", 3, theme["outroCuts"][2], [])
    assert "The answer, 버스, may appear" in outro
    assert not prompts.mission_shows_target(theme)


def test_vehicle_first_cut_does_not_show_the_arriving_person() -> None:
    """시작 1컷(평소 모습)에 온 사람이 나오면 2컷 '와 계시네!'(깜짝 방문)와 어긋남(1단계 실측
    2026-11-23: 1컷에 짐을 정리하는 삼촌). 그 칸만 고쳐 씀(CUT_TARGET), 2컷부터는 나와도 됨."""
    theme = vehicle_theme()
    assert checks.arrival_person(theme) == "삼촌"
    theme["introCuts"][0]["scene"] = (
        "거실에서 아이는 소파 곁에 있고 삼촌은 창문 가까이 짐을 정리한다."
    )
    bad = [r for r in checks.check_theme(theme, 3) if r.startswith("CUT_TARGET")]
    assert bad == [
        "CUT_TARGET introCuts1.scene 시작 1컷(평소 모습)에 찾아올 사람 '삼촌'(2컷에서 처음 보임, "
        "없다는 말도 쓰지 않음)"
    ]
    assert checks.FIX_REASON[2].match(bad[0])  # 칸 고쳐 쓰기 경로(CUT_TARGET)
    theme = vehicle_theme()
    theme["introCuts"][1]["scene"] = "현관 안쪽에서 삼촌과 아이의 어깨 위가 크게 보인다."
    assert not [r for r in checks.check_theme(theme, 3) if r.startswith("CUT_TARGET")]
    assert checks.arrival_person(valid_theme()) is None
    # 그림 지시도: 컷 글에서 빼도 등장인물 목록을 보고 그려 넣었음(1단계 다시 그리기 2026-11-23)
    first = prompts.cut_image_prompt(
        vehicle_theme(), "INTRO", 1, vehicle_theme()["introCuts"][0], []
    )
    assert "삼촌 has not arrived yet" in first
    second = prompts.cut_image_prompt(
        vehicle_theme(), "INTRO", 2, vehicle_theme()["introCuts"][1], []
    )
    assert "has not arrived" not in second


def test_vehicle_absent_value_clue_and_ferry_place() -> None:
    theme = vehicle_theme()
    theme["days"][0]["condition"] = {
        "kind": "RULE",
        "feature": "도착한 곳 바퀴 자국",
        "allowed": ["바퀴 자국 없음"],
    }
    assert checks.clue_absent_problems(theme) == [
        "CLUE_ABSENT MON 단서 조건에 없는 값 ['바퀴 자국 없음'](무엇이 없다는 말은 근거가 약함 — "
        "정답의 값이 있는 값인 특징으로 단서를 씀)"
    ]
    ferry = {**vehicle_theme(), "candidates": ["자전거", "킥보드", "버스", "여객선"]}
    assert checks.place_problems(ferry) and checks.place_problems(ferry)[0].startswith(
        "VEHICLE_PLACE 후보 여객선"
    )
    seaside = {**ferry, "world": "섬마을 바닷가의 맑은 오후"}
    assert checks.place_problems(seaside) == []
    assert checks.place_problems(
        {**ferry, "world": "강아지와 강당이 있는 마을"}
    )  # '강' 한 글자 아님


def test_route_is_in_hand_without_table() -> None:
    route = {**valid_theme(), "storyType": "ROUTE", "target": "할머니가 보낸 택배 상자"}
    assert families.ROUTE.target_in_hand and families.ROUTE.facts is None
    assert prompts.mission_shows_target(route) and not prompts.mission_shows_target(valid_theme())
    assert checks.traceable("묻은 흙", families.ROUTE)
    assert "ROUTE" in prompts.REVIEW_SYSTEM and "VEHICLE" in prompts.REVIEW_SYSTEM


def test_in_hand_mission_image_review_allows_target() -> None:
    # #634: 출처·선물 상자처럼 대상이 늘 보이는 종류는 요일 그림 지시('손에 들어도 됨')와 그림 검토
    # targetAllowed가 같아야 함(전에는 늘 거짓)
    gift = {**valid_theme(), "storyType": "GIFT"}
    assert prompts.mission_shows_target(gift)
    assert not prompts.mission_shows_target({**valid_theme(), "storyType": "SECRET_INGREDIENT"})


def test_vehicle_clues_name_the_person() -> None:
    # 작은 실측: 소리 단서에 온 사람이 없어 글 검토 CLUE_LOGIC → 모든 단서에 온 사람(칸 고쳐 쓰기)
    theme = vehicle_theme()
    assert checks.clue_person(theme) == "삼촌"
    assert checks.clue_person({**theme, "target": "사촌 언니가 타고 온 탈것"}) == "사촌언니"
    assert checks.clue_person(valid_theme()) is None
    theme["days"][1]["clue"] = "사진 속 손에 든 건 헬멧이 아니었어."
    bad = checks.check_theme(theme, 3)
    assert bad == [
        "CLUE_OWNER TUE clue 단서에 온 사람('삼촌')이 없음(그 사람이 탄 탈것의 증거임을 밝힘)"
    ]
    assert list(checks.fix_targets(bad)) == ["TUE.clue"]
    assert any("온 사람('삼촌')" in r for r in prompts.fix_rules(theme, "TUE.clue"))
    assert "CLUE_OWNER" in families.type_rules(families.VEHICLE)


def test_when_outro_must_keep_answer_time() -> None:
    # 판정 실측: 정답 오전 10시인데 마무리 장면이 '낮 12시라고 확인' → 그 칸만 고쳐 씀
    theme = {**when_theme(), "outroStory": "관리인 아저씨가 저녁 7시에 물을 줬다고 웃었어요."}
    assert checks.outro_other_candidates(theme) == []
    wrong = {**theme, "outroStory": "관리인 아저씨가 밤 9시에 물을 줬다고 웃었어요."}
    assert checks.outro_other_candidates(wrong) == ["밤 9시"]
    bad = [r for r in checks.check_theme(wrong, 3) if r.startswith("OUTRO_ANSWER")]
    assert bad and list(checks.fix_targets(bad)) == ["outro"]
    # 정답과 머리 낱말이 같은 후보('아침 7시')는 정답을 줄여 쓰면 걸림
    short = {**theme, "outroStory": "관리인 아저씨가 7시에 물을 줬대요."}
    assert checks.outro_other_candidates(short) == ["아침 7시"]
    assert checks.outro_other_candidates({**vehicle_theme(), "outroStory": "기차 아님"}) == []
    assert any("다른 후보는 쓰지 않는다" in r for r in prompts.fix_rules(wrong, "outro"))


def test_route_trace_is_only_what_sticks_to_target() -> None:
    # 판정 실측: 길에서 들린 소리가 흔적 날에 배정돼 CLUE_LOGIC → 길은 대상에 묻은 것만 흔적
    assert checks.traceable("묻은 흙", families.ROUTE)
    assert checks.traceable("바닥 재질", families.ROUTE)
    for name in ("들린 소리", "길 모양", "가로등 빛"):
        assert not checks.traceable(name, families.ROUTE), name
    assert checks.traceable("흔들면 나는 소리", families.GIFT)  # ②는 그대로


def test_when_intro_must_not_say_daypart() -> None:
    """#782 설계 v4: 3차 측정 way5b "점심을 먹고 온 아이가 먹이 준 일이 끝난 걸 앎"인데 정답 오후
    3시. 시작 이야기(모델 몫)만 보고, 코드가 붙인 마을 규칙('오후 7시')과 다른 요일 장면은 보지
    않음."""
    theme = {**when_theme(), "introStory": "점심을 먹고 온 지호는 화단이 젖은 걸 알았어요."}
    bad = [r for r in checks.check_theme(theme, 3) if r.startswith("TIME_WORD intro")]
    assert bad and "'점심'" in bad[0] and list(checks.fix_targets(bad)) == ["intro"]
    assert not [r for r in checks.check_theme(when_theme(), 3) if r.startswith("TIME_WORD")]


def test_no_object_types_use_person_close_for_intro_two() -> None:
    """탈것·소리 탐정은 시작 2컷에 사건 물건이 없어 인물 클로즈업(1단계 실측 2026-11-23: '사건
    물건을 크게'면 검토가 '탈것이 크게 안 보임'으로 세 번 떨어뜨리고, 그림은 물건을 지어냄)."""
    from tests.theme_draft.test_families_sound import sound_theme

    for theme in (vehicle_theme(), sound_theme()):
        frame = prompts.cut_frame(theme, "INTRO", 2)
        assert frame is not None and frame.id == "PERSON_CLOSE"
        cut = prompts.cut_image_prompt(theme, "INTRO", 2, theme["introCuts"][1], [])
        assert "no object needs to be large" in cut and "incident object or spot" not in cut
    assert prompts.cut_frame(valid_theme(), "INTRO", 2).id == "OBJECT_CLOSE"
