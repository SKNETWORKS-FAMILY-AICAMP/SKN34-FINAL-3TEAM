"""씨앗 갈래·소리 장소 맞추기·섬 (#782 기준안 — 확인 전, 사용자 결정 2026-11-19).

갈래(내부 칸 branch): 주제 글 갈래로 덮어쓰기·목록 밖 무시·글 모델 고르기 지시·응답에 없음·예전
저장본, 갈래별 줄거리 규칙 줄. 소리 탐정: 새 줄 6개·blocked {}·장소 4곳 × 범주마다 성격 태그로 후보
4개 이상·개구리 겨울·갈래로 범주 고정·마무리 손보기. 섬이면 기차 없음. learning 장소 목록 JSON의
모든 소리·탈것·장난·발자국 장소에서 후보가 4개 이상 남는지.
"""

import copy
import datetime
import json
from pathlib import Path
from typing import Any

import pytest

from app.theme_draft import checks, families, prompts
from app.theme_draft.models import ThemeDraftRequest
from tests.theme_draft.fixtures import generated_theme, valid_theme
from tests.theme_draft.helpers import request_body
from tests.theme_draft.test_graph import gen_llm, review_llm, run
from tests.theme_draft.test_media_graph import gen_llm as media_gen
from tests.theme_draft.test_media_graph import review_llm as media_review
from tests.theme_draft.test_media_graph import run as media_run
from tests.theme_draft.test_regen import base_of, full

LOST = (
    "줄거리: 잃어버린 것 찾기 / 뭉치 역할: 탐정(탐정 모자·돋보기) / 장소: 동네 공원 / "
    "찾는 대상: 아이가 산책시키던 큰 개"
)
PRANK = (
    "줄거리: 동물 장난꾸러기 찾기 / 뭉치 역할: 경찰관(경찰 모자·경찰 배지 조끼) / 장소: 마을 "
    "떡집 / 밝힐 것: 떡에 꽂을 꽃 장식을 숨겨 둔 동물"
)
TREASURE = (
    "줄거리: 보물 쪽지 따라가기 / 뭉치 역할: 보물 탐험대(탐험 조끼·나침반 목걸이) / "
    "장소: 할아버지 댁 뒷마당 / 찾는 대상: 할아버지가 숨긴 타임캡슐"
)
SOUND = (
    "줄거리: 소리 탐정 / 뭉치 역할: 소리 박사(헤드폰·연구 가운) / 장소: {place} / "
    "밝힐 것: {place}에서 밤마다 들린 소리"
)
ISLAND = (
    "줄거리: 무엇을 타고 왔을까 / 뭉치 역할: 교통 경찰(경찰 모자·형광 조끼) / 장소: 섬마을 "
    "분교 / 밝힐 것: 선생님이 타고 온 탈것"
)
WEEKS = [datetime.date(2027, 1, 4) + datetime.timedelta(weeks=w) for w in range(52)]
WINTER = (12, 1, 2)
K = checks.CANDIDATES[3]


def request(topic: str | None, week: datetime.date | None = None, grade: int = 3) -> Any:
    body = request_body(grade=grade, topic=topic)
    if week is not None:
        body["weekStart"] = week.isoformat()
    return ThemeDraftRequest.model_validate(body)


def plan(topic: str, week: datetime.date | None = None) -> dict[str, Any]:
    found = prompts.candidate_plan_for(request(topic, week))
    assert found is not None
    return found


def run_with(topic: str, **theme: Any) -> Any:
    """줄거리 모델이 theme 칸을 덮어쓴 valid_theme을 돌려주는 글 단계 실행."""
    body = {**copy.deepcopy(valid_theme()), **theme}
    response = run(
        gen_llm(theme=lambda n, d: generated_theme(body)), review_llm(), request_body(topic=topic)
    )
    assert response.failure is None and response.regen is not None
    return response


# ---------------------------------------------------------------- 갈래 칸(내부 칸 branch)
def test_topic_branch_overrides_model_value_and_is_internal() -> None:
    response = run_with(f"{LOST} / 갈래: 큰 동물", branch="물건")
    assert response.regen["theme"]["branch"] == "큰 동물"
    assert response.theme is not None
    assert "branch" not in response.theme.model_dump(by_alias=True)  # 응답 theme에는 없음


def test_topic_branch_outside_list_is_ignored() -> None:
    # 목록 밖 값은 무시하고 None(모델 값으로 채우지도 않음)
    response = run_with(f"{LOST} / 갈래: 공룡", branch="물건")
    assert response.regen["theme"]["branch"] is None
    _, value = prompts.seed_branch(request(f"{LOST} / 갈래: 공룡"))
    assert value is None
    # 다른 종류의 갈래 값(되찾음은 PRANK 것)도 목록 밖
    assert prompts.seed_branch(request(f"{LOST} / 갈래: 되찾음")) == (True, None)


def test_model_picks_branch_without_topic_branch() -> None:
    # 예전 초안(갈래 칸 없음): 모델이 고른 값, 목록 밖이면 None
    assert run_with(LOST, branch="작은 생물").regen["theme"]["branch"] == "작은 생물"
    assert run_with(LOST, branch="공룡").regen["theme"]["branch"] is None
    # 관리자 자유 글: 모델이 고른 종류의 목록으로 봄(보물 쪽지는 갈래 없음)
    free = "구조대: 길 잃은 강아지 찾기"
    assert run_with(free, branch="작은 동물").regen["theme"]["branch"] == "작은 동물"
    assert run_with(free, branch=None).regen["theme"]["branch"] is None


def test_branch_helpers() -> None:
    assert families.valid_branch("PRANK", " 정리 ") == "정리"
    assert families.valid_branch("PRANK", "물건") is None
    assert families.valid_branch("TREASURE", "물건") is None
    assert families.valid_branch(None, None) is None
    assert families.theme_branch({"storyType": "ORIGIN", "branch": "동물"}) == "동물"
    assert families.theme_branch({"storyType": "ORIGIN"}) is None  # 예전 저장본
    assert set(families.STORY_BRANCHES) == {"LOST", "PRANK", "ORIGIN", "SOUND"}
    assert set(families.BRANCH_RULES) == {
        (code, b) for code, bs in families.STORY_BRANCHES.items() for b in bs
    }
    # 소리 탐정 갈래 = 후보 범주
    assert set(families.STORY_BRANCHES["SOUND"]) == set(families.SOUNDS.groups.values())  # type: ignore[union-attr]


# ---------------------------------------------------------------- 줄거리 프롬프트 갈래 줄
def test_prompt_gives_fixed_branch_rule_and_outro_line() -> None:
    user = prompts.plan_user(request(f"{PRANK} / 갈래: 되찾음"), [])
    assert "branch: 되찾음(갈래, 주제가 정함, 그대로 쓴다)" in user
    assert (
        "- 갈래 되찾음: 장난꾸러기가 작은 물건을 가져가 장난 자리 가까운 덤불 곁에 숨겨 두었고, "
        "엔딩에서 아이가 되찾는다(동물 입에 있던 것을 사람이 먹지 않음)." in user
    )
    assert "- outro(마무리 장면)도 갈래에 맞게: 위 결말에 더해 아이가 덤불 곁에" in user
    assert "갈래 정리" not in user
    assert families.ANIMAL_OUTRO in user  # 원문은 그대로 두고 갈래 줄로 덧붙임
    tidy = prompts.plan_user(request(f"{PRANK} / 갈래: 정리"), [])
    assert (
        "- 갈래 정리: 장난꾸러기가 그 자리에서 장난을 쳤고(먹기·흩어 놓기·파헤치기·봉지 뜯기), "
        "엔딩에서 원래대로 정리한다." in tidy
    )
    assert "모두 함께 장난 자리를 원래대로 정리한다" in tidy


@pytest.mark.parametrize(
    "topic,words",
    [
        (f"{LOST} / 갈래: 큰 동물", ["안아 들 수 없는 큰 동물", "목줄을 잡고 데려간다"]),
        (f"{LOST} / 갈래: 작은 생물", ["관찰 통에 담아 기르던", "관찰 통에 다시 담긴다"]),
        (f"{LOST} / 갈래: 작은 동물", ["품에 안을 수 있는 작은 반려동물"]),
        (f"{LOST} / 갈래: 물건", ["아이가 아끼는 물건이다"]),
        (
            f"{LOST.replace('잃어버린 것 찾기', '출처 찾기').replace('찾는 대상', '손에 든 것')}"
            " / 갈래: 동물",
            ["길 잃은 동물이다", "돌아온 동물을 반갑게 맞이한다"],
        ),
    ],
)
def test_prompt_branch_lines_name_the_target_kind(topic: str, words: list[str]) -> None:
    user = prompts.plan_user(request(topic), [])
    branch = topic.rsplit("갈래: ", 1)[1]
    assert f"branch: {branch}(갈래, 주제가 정함" in user
    assert all(w in user for w in words), words


def test_prompt_lets_model_pick_branch_or_null() -> None:
    old = prompts.plan_user(request(LOST), [])  # 예전 초안: 목록과 갈래별 줄
    assert "branch: 갈래를 물건·작은 동물·큰 동물·작은 생물 가운데 주제·대상에 맞는 하나로" in old
    assert all(f"- 갈래 {b}: " in old for b in families.STORY_BRANCHES["LOST"])
    assert "마무리 장면(outro): 주인 아이가 찾은 동물의 목줄을 잡고" in old
    assert "branch: null(이 테마는 갈래를 쓰지 않는다)" in prompts.plan_user(request(TREASURE), [])
    free = prompts.plan_user(request("우리 반 텃밭"), [])
    assert "branch(갈래): 고른 종류에 갈래 목록이 있으면" in free
    for code, options in families.STORY_BRANCHES.items():
        assert f"- branch(갈래) 목록: {'·'.join(options)}\n" in free, code


def test_sound_branch_is_code_picked_group() -> None:
    topic = SOUND.format(place="할머니 댁 시골집")
    for week in WEEKS[:8]:
        req = request(topic, week)
        group = plan(topic, week)["group"]
        assert prompts.seed_branch(req) == (True, group)
        assert prompts.branch_for(req, {"storyType": "SOUND", "branch": "다른 값"}) == group
        assert f"branch: {group}(갈래, 주제가 정함" in prompts.plan_user(req, [])


def test_outro_fix_rule_follows_branch_and_old_saved_theme() -> None:
    theme = {**valid_theme(), "storyType": "LOST", "branch": "큰 동물"}
    rules = prompts.fix_rules(theme, "outro")
    assert any(r.startswith("outro(마무리 장면)도 갈래에 맞게: 주인 아이가") for r in rules)
    for old in ({**valid_theme(), "storyType": "LOST"}, {**theme, "branch": "공룡"}):
        assert not any("갈래" in r for r in prompts.fix_rules(old, "outro"))  # None으로 동작


def test_partial_regen_with_old_saved_theme_without_branch() -> None:
    response, storage = full()
    base = base_of(response)
    base["regen"]["theme"].pop("branch", None)  # 칸이 없던 때 저장본
    out = media_run(
        media_gen(),
        media_review(),
        storage=storage,
        regenerate={"targets": ["MISSION:MON"], "base": base},
    )
    assert out.failure is None and out.regen is not None
    assert families.theme_branch(out.regen["theme"]) is None


# ---------------------------------------------------------------- 소리 탐정 새 줄·장소
NEW_SOUNDS = {
    "산토끼": ("동물", ("풀숲 속", "바스락 소리", "매일 밤", "옮겨 다니는 소리")),
    "개구리": ("동물", ("개울가", "개굴개굴 소리", "비 오는 밤", "한곳에서 나는 소리")),
    "갈매기": ("동물", ("방파제 위", "끼룩 소리", "매일 밤", "한곳에서 나는 소리")),
    "해먹": ("물건", ("두 나무 사이", "삐걱 소리", "바람 부는 밤", "한곳에서 나는 소리")),
    "작은 종": ("물건", ("랜턴 걸이 위", "딸랑 소리", "바람 부는 밤", "한곳에서 나는 소리")),
    "빈 페트병": ("물건", ("개수대 옆", "찌그럭 소리", "바람 부는 밤", "옮겨 다니는 소리")),
}
# 장소 넷(주제 씨앗 소리 장소)의 성격 태그와 범주별로 '있을 법함'인 줄(기준안)
SOUND_FIT = {
    ("할머니 댁 시골집", "마을"): {
        "동물": {"부엉이", "고양이", "생쥐", "너구리", "강아지"},
        "물건": {"바람개비", "빈 양동이", "빈 깡통", "현수막"},
    },
    ("숲속 캠핑장", "숲"): {
        "동물": {"부엉이", "너구리", "산토끼", "개구리"},
        "물건": {"빈 양동이", "해먹", "작은 종", "빈 페트병"},
    },
    ("시골 학교", "학교"): {
        "동물": {"부엉이", "고양이", "생쥐", "너구리"},
        "물건": {"바람개비", "녹슨 그네", "빈 양동이", "현수막"},
    },
    ("바닷가 민박집", "바다"): {
        "동물": {"고양이", "생쥐", "강아지", "갈매기"},
        "물건": {"바람개비", "빈 양동이", "빈 깡통", "현수막"},
    },
}


def test_new_sound_rows_and_table_stays_separable() -> None:
    table = families.SOUNDS
    for name, (group, row) in NEW_SOUNDS.items():
        assert table.rows[name] == row and table.group(name) == group
    assert len(table.rows) == 16 and set(table.groups) == set(table.rows)  # type: ignore[arg-type]
    assert table.blocked() == {}
    assert set(families.SOUND_PLACES) == set(table.rows)
    assert families.SOUND_NO_WINTER == {"개구리"}


@pytest.mark.parametrize("place,tag", list(SOUND_FIT))
@pytest.mark.parametrize("group", ["동물", "물건"])
def test_sound_candidates_follow_place_trait(place: str, tag: str, group: str) -> None:
    expected = SOUND_FIT[(place, tag)][group]
    assert len(expected) >= K
    topic = f"{SOUND.format(place=place)} / 갈래: {group} / 성격: {tag}"
    # 숲속 캠핑장은 learning 장소 목록에서 봄~가을만(겨울은 아래 개구리 시험)
    weeks = [w for w in WEEKS if tag != "숲" or w.month not in WINTER]
    seen: set[str] = set()
    for week in weeks:
        p = plan(topic, week)
        assert p["group"] == group and set(p["candidates"]) <= expected
        seen |= set(p["candidates"])
    assert seen == expected
    month = weeks[0].month
    assert {
        c for c in families.place_sounds((tag,), month) if families.SOUNDS.group(c) == group
    } == (expected)


def test_frog_is_not_a_winter_candidate() -> None:
    topic = f"{SOUND.format(place='숲속 캠핑장')} / 갈래: 동물 / 성격: 숲"
    winter = [w for w in WEEKS if w.month in WINTER]
    summer = [w for w in WEEKS if w.month in (6, 7, 8)]
    winter_seen = {c for w in winter for c in plan(topic, w)["candidates"]}
    assert "개구리" not in winter_seen
    # 겨울 숲은 태그가 맞는 동물이 3마리라 태그로는 거르지 않음(개구리만 뺀 동물 7마리)
    animals = {c for c in families.SOUNDS.rows if families.SOUNDS.group(c) == "동물"}
    assert winter_seen <= animals - {"개구리"} and len(winter_seen) > K
    assert "개구리" in {c for w in summer for c in plan(topic, w)["candidates"]}
    # 성격 칸이 없어도 겨울에는 뺌
    plain = f"{SOUND.format(place='할머니 댁 시골집')} / 갈래: 동물"
    assert "개구리" not in {c for w in winter for c in plan(plain, w)["candidates"]}


def test_topic_branch_fixes_sound_group() -> None:
    topic = SOUND.format(place="할머니 댁 시골집")
    for group in ("동물", "물건"):
        fixed = f"{topic} / 갈래: {group}"
        assert {plan(fixed, w)["group"] for w in WEEKS} == {group}
    # 갈래 칸이 없거나 범주 밖 값이면 지금처럼 무작위(두 범주 모두 나옴)
    assert {plan(topic, w)["group"] for w in WEEKS} == {"동물", "물건"}
    assert {plan(f"{topic} / 갈래: 공룡", w)["group"] for w in WEEKS} == {"동물", "물건"}


def test_sound_outro_rule_has_new_object_fixes() -> None:
    rule = families.SOUND.outro_rule
    assert "깡통을 치움·현수막을 묶음·해먹 줄을 단단히 묶음·작은 종을 떼어 둠·빈 페트병을 치움" in (
        rule
    )


# ---------------------------------------------------------------- 섬
def test_island_has_no_train() -> None:
    island = f"{ISLAND} / 성격: 바다·학교·섬"
    seen = {c for w in WEEKS for c in plan(island, w)["candidates"]}
    assert seen == {"자전거", "킥보드", "버스", "여객선"}  # 기차 없음, 바다라 여객선 있음
    sea = f"{ISLAND} / 성격: 바다·학교"
    assert "기차" in {c for w in WEEKS for c in plan(sea, w)["candidates"]}


# ---------------------------------------------------------------- learning 장소 목록 전체
PLACES_PATH = (
    Path(__file__).resolve().parents[3]
    / "learning-service/src/main/resources/knowledge/theme_places.json"
)
SEASON_MONTHS = {
    "SPRING": (3, 4, 5),
    "SUMMER": (6, 7, 8),
    "AUTUMN": (9, 10, 11),
    "WINTER": (12, 1, 2),
}


def place_topics(path: Path) -> list[tuple[str, list[str], list[datetime.date]]]:
    """장소 목록의 소리·탈것·장난·발자국 사건마다 (종류, 주제 글들, 그 장소 계절의 주)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for p in data["places"]:
        if p["type"] not in ("SOUND", "VEHICLE", "PRANK", "FOOTPRINT"):
            continue
        t = families.STORY_TYPES[p["type"]]
        months = {m for s in p.get("seasons") or SEASON_MONTHS for m in SEASON_MONTHS[s]}
        weeks = [w for w in WEEKS if w.month in months]
        traits = "·".join(p.get("traits") or [])
        for e in p["events"]:
            head = (
                f"줄거리: {t.label} / 뭉치 역할: 탐정 / 장소: {p['place']} / "
                f"{t.target_label}: {e['target']}"
            )
            branches = ["동물", "물건"] if t.code == "SOUND" else [e.get("branch")]
            topics = [
                head + (f" / 갈래: {b}" if b else "") + (f" / 성격: {traits}" if traits else "")
                for b in branches
            ]
            out.append((t.code, topics, weeks))
    return out


@pytest.mark.skipif(not PLACES_PATH.exists(), reason="learning 장소 목록 JSON이 없음")
def test_every_learning_place_keeps_four_candidates() -> None:
    cases = place_topics(PLACES_PATH)
    assert {code for code, _, _ in cases} == {"SOUND", "VEHICLE", "PRANK", "FOOTPRINT"}
    for code, topics, weeks in cases:
        assert weeks, topics
        for topic in topics:
            fields = families.parse_topic_fields(topic)
            assert fields is not None and fields.story_type.code == code, topic
            for week in weeks:
                req = request(topic, week)
                if code == "SOUND":
                    pool = prompts.group_pool(req, fields, prompts.candidate_group_for(req))
                else:
                    pool = prompts.candidate_pool(req, fields)
                assert len(pool) >= K, (topic, week, pool)
                p = prompts.candidate_plan_for(req)
                assert p is not None and len(set(p["candidates"])) == K, (topic, week)
