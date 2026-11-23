"""사실표 종류의 후보 4개·정답을 코드가 고름(#782): 소리 탐정만 하던 것을 동물·선물·재료·시각·
탈것으로 넓힘. 같은 요청은 같은 값·주가 바뀌면 섞임, 정답 먼저·막힌 이름 빼기(FactTable.blocked),
물가 아닌 장소의 여객선 빼기, 동물 사는 곳·겨울 거르기(성격 칸), 끝 선택 칸이 붙은 주제 글 읽기,
줄거리 프롬프트의 '코드가 정한 후보' 문구, 52주 × 4학년 정답 고르기."""

import datetime
from collections import Counter
from typing import Any

import pytest

from app.theme_draft import checks, families, prompts
from app.theme_draft.models import ThemeDraftRequest
from tests.theme_draft.helpers import request_body

SEEDS = {
    "PRANK": "줄거리: 동물 장난꾸러기 찾기 / 뭉치 역할: 경찰관(경찰 제복·경찰 모자) / 장소: 마을 "
    "떡집 / 밝힐 것: 떡을 몰래 먹은 동물",
    "FOOTPRINT": "줄거리: 발자국 주인 찾기 / 뭉치 역할: 소방관(방화복·소방 헬멧) / 장소: 마을 "
    "소방서 앞마당 / 밝힐 것: 진흙길에 발자국을 남긴 동물",
    "GIFT": "줄거리: 선물 상자 수수께끼 / 뭉치 역할: 마술사(마술 모자·나비넥타이) / "
    "장소: 아이의 생일 파티 / 손에 든 것: 생일에 받은 리본 상자",
    "SECRET_INGREDIENT": "줄거리: 비밀 재료 찾기 / 뭉치 역할: 요리사(요리사 모자·앞치마) / "
    "장소: 마을 떡집 / 손에 든 것: 대회에 낸 할머니의 떡",
    "WHEN": "줄거리: 시간 탐정 / 뭉치 역할: 탐정(체크무늬 모자·나비넥타이) / "
    "장소: 아파트 화단 / 밝힐 것: 화단에 물을 준 때",
    "VEHICLE": "줄거리: 무엇을 타고 왔을까 / 뭉치 역할: 역무원(역무원 모자·호루라기 목걸이) / "
    "장소: 산골 마을 / 밝힐 것: 삼촌이 타고 온 탈것",
    "SOUND": "줄거리: 소리 탐정 / 뭉치 역할: 소리 박사(헤드폰·연구 가운) / 장소: 할머니 댁 "
    "시골집 / 밝힐 것: 할머니 댁 마당에서 밤마다 들린 소리",
}
WATER_VEHICLE = SEEDS["VEHICLE"].replace("산골 마을", "바닷가 마을")
WEEKS = [datetime.date(2027, 1, 4) + datetime.timedelta(weeks=w) for w in range(52)]
GRADES = (3, 4, 5, 6)


def request(topic: str | None, week: datetime.date | None = None, grade: int = 3) -> Any:
    body = request_body(grade=grade, topic=topic)
    if week is not None:
        body["weekStart"] = week.isoformat()
    return ThemeDraftRequest.model_validate(body)


def plan(topic: str | None, week: datetime.date | None = None, grade: int = 3) -> dict[str, Any]:
    found = prompts.candidate_plan_for(request(topic, week, grade))
    assert found is not None
    return found


def all_plans(topic: str) -> list[dict[str, Any]]:
    return [plan(topic, w, g) for w in WEEKS for g in GRADES]


# ---------------------------------------------------------------- 같은 씨앗·막힌 이름
@pytest.mark.parametrize("code", list(SEEDS))
def test_same_request_same_plan_and_week_changes_it(code: str) -> None:
    seed = SEEDS[code]
    table = families.STORY_TYPES[code].facts
    assert table is not None
    assert plan(seed) == plan(seed)  # 다시 생성해도 같은 값
    plans = all_plans(seed)
    for p in plans:
        names = p["candidates"]
        assert len(set(names)) == checks.CANDIDATES[3] and p["answer"] in names
        assert set(names) <= set(table.rows)
        assert not set(names) & set(table.blocked().get(p["answer"], []))
    # 주가 바뀌면 정답·후보가 바뀜(한 학년 52주에서 정답이 둘 넘게)
    assert len({p["answer"] for p in plans[::4]}) > 2


def test_free_text_or_no_fact_table_gives_no_plan() -> None:
    assert prompts.candidate_plan_for(request("우리 반 텃밭")) is None
    assert prompts.candidate_plan_for(request(None)) is None
    lost = "줄거리: 잃어버린 것 찾기 / 뭉치 역할: 탐정 / 장소: 동네 시장 / 찾는 대상: 고양이"
    assert prompts.candidate_plan_for(request(lost)) is None


def test_sound_keeps_group_first() -> None:
    # 소리 탐정은 그대로: 범주를 먼저 고르고 그 범주에서 4개(group 칸 있음)
    for p in all_plans(SEEDS["SOUND"])[:40]:
        assert {families.SOUNDS.group(c) for c in p["candidates"]} == {p["group"]}
    assert "group" not in plan(SEEDS["GIFT"])


def test_time_answer_avoids_blocked_times() -> None:
    blocked = families.TIMES.blocked()
    assert blocked  # 오전 10시 ↔ 낮 12시·오후 3시
    plans = all_plans(SEEDS["WHEN"])
    answers = {p["answer"] for p in plans}
    assert {"오전 10시", "오후 3시"} <= answers  # 막힌 이름이 있는 시각도 정답으로 나옴
    for p in plans:
        assert not set(p["candidates"]) & set(blocked.get(p["answer"], []))


def test_ferry_only_at_water_place() -> None:
    assert all("여객선" not in p["candidates"] for p in all_plans(SEEDS["VEHICLE"]))
    water = all_plans(WATER_VEHICLE)
    assert any("여객선" in p["candidates"] for p in water)
    assert any(p["answer"] == "여객선" for p in water)
    # 물가가 아니면 표 5개에서 여객선을 빼 4개가 남음(후보는 늘 같은 4개, 정답만 바뀜)
    assert {frozenset(p["candidates"]) for p in all_plans(SEEDS["VEHICLE"])} == {
        frozenset({"자전거", "킥보드", "버스", "기차"})
    }


# ---------------------------------------------------------------- 동물 사는 곳·계절
SUMMER = datetime.date(2027, 7, 5)
WINTER = datetime.date(2027, 1, 4)


def with_traits(code: str, traits: str) -> str:
    return f"{SEEDS[code]} / 성격: {traits}"


@pytest.mark.parametrize("code", ["PRANK", "FOOTPRINT"])
def test_animals_follow_place_traits(code: str) -> None:
    school = with_traits(code, "학교 실내")  # 두 낱말 태그는 앞 낱말로
    fit = {"까치", "비둘기", "참새", "고양이", "생쥐"}
    for g in GRADES:
        for week in (SUMMER, WINTER):
            assert set(plan(school, week, g)["candidates"]) <= fit
    water = with_traits(code, "물가")
    seen = {c for w in WEEKS for c in plan(water, w)["candidates"]}
    assert seen == {"까치", "비둘기", "참새", "고양이", "너구리", "오리"}


def test_winter_drops_hibernating_animals() -> None:
    forest = with_traits("PRANK", "숲·산")
    winter = [d for d in WEEKS if d.month in (12, 1, 2)]
    summer = [d for d in WEEKS if d.month in (6, 7, 8)]
    winter_seen = {c for w in winter for g in GRADES for c in plan(forest, w, g)["candidates"]}
    assert not winter_seen & families.ANIMAL_NO_WINTER
    assert winter_seen == {"너구리", "까치", "비둘기", "참새"}  # 겨울 숲은 꼭 4마리
    summer_seen = {c for w in summer for g in GRADES for c in plan(forest, w, g)["candidates"]}
    assert families.ANIMAL_NO_WINTER <= summer_seen


def test_seasons() -> None:
    assert [families.season_of(m) for m in (12, 1, 2, 3, 5, 6, 8, 9, 11)] == [
        "겨울",
        "겨울",
        "겨울",
        "봄",
        "봄",
        "여름",
        "여름",
        "가을",
        "가을",
    ]


def test_no_traits_or_too_few_animals_is_not_filtered_by_habitat() -> None:
    # 성격 칸이 없으면 사는 곳으로는 거르지 않음(9마리 모두 후보). 겨울잠 동물만 겨울에 늘 뺌
    # (#782: 성격 칸이 없는 겨울 주에 다람쥐가 정답이 되던 것)
    seen = {c for p in all_plans(SEEDS["PRANK"]) for c in p["candidates"]}
    assert seen == set(families.ANIMALS.rows)
    winter = [d for d in WEEKS if d.month in (12, 1, 2)]
    winter_seen = {
        c for w in winter for g in GRADES for c in plan(SEEDS["PRANK"], w, g)["candidates"]
    }
    assert not winter_seen & families.ANIMAL_NO_WINTER
    # 모르는 태그면 맞는 동물이 3마리(새)뿐이라 사는 곳으로 거르지 않음(성격 칸 없을 때와 같음)
    market = with_traits("PRANK", "시장")
    assert len(families.habitat_animals(("시장",), 7)) < checks.CANDIDATES[3]
    assert all(plan(market, w) == plan(SEEDS["PRANK"], w) for w in WEEKS)
    # 갈래 칸만 있으면 거르지 않음
    branch = f"{SEEDS['PRANK']} / 갈래: 장난"
    assert all(plan(branch, w) == plan(SEEDS["PRANK"], w) for w in WEEKS)


def test_habitat_table_covers_every_animal() -> None:
    assert set(families.ANIMAL_HABITATS) == set(families.ANIMALS.rows)
    for tag in ("마을", "학교", "물가", "공원", "밭", "숲", "산"):
        for month in (1, 7):
            assert len(families.habitat_animals((tag,), month)) >= checks.CANDIDATES[3], tag


# ---------------------------------------------------------------- 주제 글 끝 선택 칸
def test_topic_with_trailing_fields_is_read() -> None:
    topic = f"{SEEDS['VEHICLE']} / 갈래: 깜짝 방문 / 성격: 마을 길·물가"
    fields = families.parse_topic_fields(topic)
    assert fields is not None and fields.story_type is families.VEHICLE
    assert fields.place == "산골 마을" and fields.target == "삼촌이 타고 온 탈것"
    assert fields.branch == "깜짝 방문" and fields.traits == ("마을 길", "물가")
    assert families.parse_topic(topic) is families.VEHICLE
    only_traits = families.parse_topic_fields(f"{SEEDS['PRANK']} / 성격: 마을·공원")
    assert only_traits is not None and only_traits.story_type is families.PRANK
    assert only_traits.target == "떡을 몰래 먹은 동물" and only_traits.traits == ("마을", "공원")
    assert only_traits.branch is None
    plain = families.parse_topic_fields(SEEDS["GIFT"])
    assert plain is not None and plain.traits == () and plain.branch is None
    assert plain.place == "아이의 생일 파티"
    old = families.parse_topic_fields("뭉치 역할: 탐정 / 장소: 시장 / 찾는 대상: 고양이")
    assert old is not None and old.story_type is families.LOST and old.place == "시장"
    # 라벨이 종류와 안 맞으면 끝 칸이 있어도 None
    assert (
        families.parse_topic(
            "줄거리: 발자국 주인 찾기 / 뭉치 역할: 탐정 / 장소: 숲 / 찾는 대상: 동물 / 성격: 숲"
        )
        is None
    )
    # 장소 칸에 물가 낱말이 없어도 성격 태그가 물가·바다면 여객선을 둘 수 있음
    assert any("여객선" in plan(topic, w)["candidates"] for w in WEEKS)
    inland = f"{SEEDS['VEHICLE']} / 성격: 마을 길"
    assert all("여객선" not in plan(inland, w)["candidates"] for w in WEEKS)


# ---------------------------------------------------------------- 프롬프트·검사
@pytest.mark.parametrize("code", list(SEEDS))
def test_plan_prompt_gives_code_picked_candidates(code: str) -> None:
    req = request(SEEDS[code])
    p = prompts.candidate_plan_for(req)
    assert p is not None
    user = prompts.plan_user(req, [])
    assert f"candidates는 {'·'.join(p['candidates'])}, answer는 {p['answer']}" in user
    # 표에서 '그 장소에 어울리는 4개'를 고르라는 문구는 코드가 정한 문구로 바뀜
    assert "그 장소·이야기에 어울리는 4개" not in user
    assert "'이번 테마 후보'에 코드가 정한 이름을 표 이름 그대로" in user
    assert ("범주 " in user.split("이번 테마 후보(")[1].split(")")[0]) == (code == "SOUND")


def test_free_text_prompt_keeps_free_pick_rule() -> None:
    user = prompts.plan_user(request("우리 반 텃밭"), [])
    assert "그 장소·이야기에 어울리는 4개" in user and "이번 테마 후보(" not in user


def test_plan_mismatch_is_same_kind_for_every_fact_type() -> None:
    fixed = {"candidates": ["자전거", "킥보드", "버스", "기차"], "answer": "버스"}
    theme = {"storyType": "VEHICLE", "candidates": list(fixed["candidates"]), "answer": "버스"}
    ok = {**theme, "candidatePlan": fixed}
    assert not [r for r in checks.fact_table_problems(ok) if r.startswith("SAME_KIND")]
    other = {**theme, "candidatePlan": {**fixed, "answer": "기차"}}
    assert any(r.startswith("SAME_KIND 후보·정답이") for r in checks.fact_table_problems(other))
    # candidatePlan이 없으면(관리자 자유 글) 보지 않음
    assert not [r for r in checks.fact_table_problems(theme) if r.startswith("SAME_KIND")]


# ---------------------------------------------------------------- 52주 × 4학년 고르기
@pytest.mark.parametrize("topic", [*SEEDS.values(), WATER_VEHICLE])
def test_answers_spread_over_year_and_grades(topic: str) -> None:
    counts = Counter(p["answer"] for p in all_plans(topic))
    pool = len(counts)
    table = families.parse_topic(topic).facts  # type: ignore[union-attr]
    expected = 4 if topic == SEEDS["VEHICLE"] else len(table.rows)  # type: ignore[union-attr]
    assert pool == expected  # 모든 이름이 한 번 넘게 정답으로 나옴
    top = counts.most_common(1)[0][1] / sum(counts.values())
    # 가장 많은 정답도 균등 몫의 1.6배 이하. 소리 탐정은 1.8배(#782): 줄이 10 → 16으로 늘어 한
    # 이름 몫이 208번 중 13번으로 작아져 우연 흔들림 비율이 커지고, 개구리가 겨울 13주에 빠져
    # 나머지 이름 몫이 조금 늘어남(지금 씨앗 값에서 가장 많은 정답 22번 = 균등 몫의 1.69배)
    bound = 1.8 if topic == SEEDS["SOUND"] else 1.6
    assert top <= bound / pool, counts
