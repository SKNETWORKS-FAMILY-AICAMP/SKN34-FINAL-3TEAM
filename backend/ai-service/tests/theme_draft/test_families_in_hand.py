"""② 손에 든 것의 출처·정체 (#634, 설계 ai.md 17.8.13): 출처 찾기·선물 상자 수수께끼·비밀 재료
찾기. '대상을 아직 못 찾았다' 전제 뒤집기, 선물·재료 사실표, 후보 이름·정답만의 값 감추기."""

import copy
import json
from typing import Any

import pytest

from app.config import get_settings
from app.mission_draft.models import Draft, MissionDraftRequest
from app.theme_draft import checks, families, prompts
from app.theme_draft.models import ThemeDraftRequest
from tests.theme_draft.fixtures import day_with, feature, mission_draft, valid_theme
from tests.theme_draft.helpers import request_body

SEEDS = {
    "ORIGIN": "줄거리: 출처 찾기 / 뭉치 역할: 수의사(하얀 가운·청진기 목걸이) / "
    "장소: 아파트 놀이터 / 손에 든 것: 놀이터에서 만난 길 잃은 강아지",
    "GIFT": "줄거리: 선물 상자 수수께끼 / 뭉치 역할: 마술사(마술 모자·나비넥타이) / "
    "장소: 아이의 생일 파티 / 손에 든 것: 생일에 받은 리본 상자",
    "SECRET_INGREDIENT": "줄거리: 비밀 재료 찾기 / 뭉치 역할: 요리사(요리사 모자·앞치마) / "
    "장소: 마을 떡집 / 손에 든 것: 대회에 낸 할머니의 떡",
}
GIFT_OF = {"놀이터": "목도리", "텃밭": "머그컵", "창고": "고무공", "정자": "그림책"}


def codes(reasons: list[str]) -> list[str]:
    return sorted(r.split(" ")[0] for r in reasons)


def gift_theme() -> dict[str, Any]:
    """valid_theme의 장소 후보를 선물로 바꾼 선물 상자 줄거리(check_theme을 통과). 정답 머그컵."""
    theme = copy.deepcopy(valid_theme())
    theme |= {
        "storyType": "GIFT",
        "target": "생일에 받은 리본 상자",
        "candidates": [GIFT_OF[c] for c in theme["candidates"]],
        "answer": GIFT_OF[theme["answer"]],
        "bigQuestion": "상자에 넣은 선물은 무엇이었을까?",
    }
    cands = theme["candidates"]
    theme["features"] = [
        feature(name, {c: families.GIFTS.fact(c, name) or "" for c in cands})
        for name in families.GIFTS.features
    ]
    # 월(흔적) 무게로 목도리·고무공, 금(기록) 소리로 그림책이 빠짐
    for d, clue, kind, feat, allowed in (
        ("MON", "상자를 들어 보니 묵직한 상자였어.", "RULE", "상자 무게", ["묵직한 상자"]),
        (
            "TUE",
            "선물을 그릇 가게나 서점에서 사는 걸 봤대.",
            "HINT",
            "선물을 산 가게",
            ["그릇 가게", "서점"],
        ),
        (
            "WED",
            "서점이나 그릇 가게에서 선물을 계산하는 걸 봤대.",
            "HINT",
            "선물을 산 가게",
            ["서점", "그릇 가게"],
        ),
        ("THU", "상자를 다시 들어 보니 묵직한 상자였어.", "HINT", "상자 무게", ["묵직한 상자"]),
        (
            "FRI",
            "메모에 달그락 소리가 난다고 적혀 있었어.",
            "RULE",
            "흔들면 나는 소리",
            ["달그락 소리"],
        ),
    ):
        day = checks.theme_day(theme, d)
        day["clue"] = clue
        day["condition"] = {"kind": kind, "feature": feat, "allowed": allowed}
    return theme


# ---------------------------------------------------------------- 등록표·씨앗
@pytest.mark.parametrize("code", list(SEEDS))
def test_in_hand_seed_topic_gives_story_type(code: str) -> None:
    found = families.parse_topic(SEEDS[code])
    assert found is not None and found.code == code and found.target_in_hand
    user = prompts.plan_user(ThemeDraftRequest.model_validate(request_body(topic=SEEDS[code])), [])
    assert f"storyType: {code}" in user and "처음부터 등장인물이 가지고 있다" in user


def test_fact_tables_values_do_not_contain_each_other() -> None:
    for table in (families.ANIMALS, families.GIFTS, families.INGREDIENTS):
        for i, name in enumerate(table.features):
            values = {row[i] for row in table.rows.values()}
            assert not [
                (a, b)
                for a in values
                for b in values
                if a != b and a.replace(" ", "") in b.replace(" ", "")
            ], (table.name, name)


def test_in_hand_trace_features() -> None:
    assert checks.traceable("흔들면 나는 소리", families.GIFT)
    assert checks.traceable("물드는 색", families.SECRET_INGREDIENT)
    assert checks.traceable("묻은 꽃가루", families.ORIGIN)
    assert not checks.traceable("자라는 곳", families.SECRET_INGREDIENT)  # 목격·기록 날
    assert not checks.traceable("냄새")  # 숨은 것 가족은 그대로


# ---------------------------------------------------------------- 코드 검사
def test_gift_theme_passes_without_incident_and_hides_candidates_and_answer_values() -> None:
    assert checks.check_theme(gift_theme(), 3) == []  # 동물이 아니라 incident·answerLook 필수 아님
    assert checks.answer_facts(gift_theme()) == [
        "달그락 소리",
        "그릇 가게",
    ]  # 그림책과 겹치는 값은 빼고
    bad = checks.check_theme(
        day_with(gift_theme(), "TUE", sceneNote="서윤이 그림책을 펼친 장면"), 3
    )
    assert bad == ["CANDIDATE_NAME TUE.sceneNote에 후보 선물 이름 ['그림책'](엔딩 전 글)"]
    leak = {
        **gift_theme(),
        "intro": "생일에 받은 상자를 흔들자 달그락 소리가 났어요. 뭉치가 출동해요.",
    }
    bad = checks.check_theme(leak, 3)
    assert bad == ["ANSWER_FACT intro에 정답만의 선물 값 ['달그락 소리'](엔딩 전 글)"]
    assert list(checks.fix_targets(bad)) == ["intro"]
    bad = checks.check_theme({**gift_theme(), "target": "머그컵이 든 상자"}, 3)
    assert codes(bad) == ["TARGET_NAMES"]
    outside = {**gift_theme(), "candidates": ["목도리", "머그컵", "고무공", "자전거"]}
    assert "FACT_TABLE" in codes(checks.check_theme(outside, 3))


def mission_inputs() -> MissionDraftRequest:
    m = ThemeDraftRequest.model_validate(request_body()).mission_for("ANALYZE")
    return MissionDraftRequest(
        standards=m.standards,
        thinking_type=m.thinking_type,
        element_codes=m.element_codes,
        grade_min=3,
        grade_max=3,
        input_type=m.input_type,
        previous_failures=[],
    )


@pytest.mark.parametrize(
    "question", ["그림책을 소개하는 글을 써 보자.", "달그락 소리가 나는 까닭을 써 보자."]
)
def test_gift_mission_with_candidate_or_answer_value_is_redone(question: str) -> None:
    s = get_settings()
    draft = Draft.model_validate(mission_draft("ANALYZE", question=question).model_dump())
    bad = checks.check_mission(
        gift_theme(),
        mission_inputs(),
        draft,
        3,
        s.mission_draft_question_max_chars,
        s.followup_example_overlap_chars,
    )
    assert "CANDIDATE_NAME" in codes(bad)


# ---------------------------------------------------------------- '못 찾은 대상' 전제 뒤집기
def test_mission_dialogue_and_review_say_target_is_in_hand() -> None:
    gift = gift_theme()
    text = prompts.story_text(gift, "MON", 3)
    assert "손에 든 대상: 생일에 받은 리본 상자" in text and "아직 찾지 못했으므로" not in text
    assert "선물 이름, 머리 낱말·정답의 표 값 포함" not in text  # 후보 범주는 '물건'
    assert (
        "물건 후보 이름, 머리 낱말·정답의 표 값 포함): 목도리, 머그컵, 고무공, 그림책, 달그락 소리"
        in text
    )
    assert "아직 찾지 못했으므로" in prompts.story_text(valid_theme(), "MON", 3)
    plain = Draft.model_validate(mission_draft("ANALYZE").model_dump())
    assert "손에 든 대상(대화에 나와도 됨" in prompts.dialogue_user(gift, "MON", plain, 3, [])
    review = json.loads(
        prompts.mission_review_user(mission_inputs(), plain, 3, gift["target"], in_hand=True)
    )
    assert review["target"] == "생일에 받은 리본 상자(처음부터 손에 든 대상)"
    assert "손에 든 것 종류(storyType ORIGIN·GIFT·SECRET_INGREDIENT·ROUTE)" in prompts.REVIEW_SYSTEM
    assert prompts.target_in_hand(gift) and not prompts.target_in_hand(valid_theme())


def test_pictures_keep_gift_closed_and_ingredient_food_hidden_until_reveal() -> None:
    gift = gift_theme()
    intro2 = prompts.cut_image_prompt(gift, "INTRO", 2, gift["introCuts"][1], [])
    assert "closed (do not show what is inside), with no tag, card or label." in intro2
    assert "Do not draw any of these gift items: 목도리, 머그컵, 고무공, 그림책." in intro2
    outro3 = prompts.cut_image_prompt(gift, "OUTRO", 3, gift["outroCuts"][2], [])
    assert "The answer, 머그컵, may appear" in outro3 and "gift items" not in outro3
    mission = prompts.mission_image_prompt(
        gift, "MON", Draft.model_validate(mission_draft("ANALYZE").model_dump()), []
    )
    assert "may appear in the characters' hands" in mission and "gift box stays closed" in mission
    food = {**gift, "storyType": "SECRET_INGREDIENT", "target": "대회에 낸 할머니의 떡"}
    intro = prompts.cut_image_prompt(food, "INTRO", 2, food["introCuts"][1], [])
    assert "Do not draw 대회에 낸 할머니의 떡" in intro  # 물든 색이 답이라 엔딩 전엔 그리지 않음
    video = prompts.video_prompt(gift, "INTRO", 4, gift["introCuts"][3], [])
    assert (
        "The gift box stays closed, with no tag, card or label." in video
        and "Do not show any of these gift items" in video
    )
    assert prompts.cut_shows_target(gift, "INTRO", 1) and not prompts.cut_shows_target(
        food, "INTRO", 1
    )


def test_fact_table_names_fit_candidate_length_check() -> None:
    """사실표 이름이 후보 글자 수 검사(2~10자)에 걸리면 고를 때마다 다시 생성됨(쥐·공·쑥 → 바꿈)."""
    lo, hi = checks.CANDIDATE_CHARS
    for table in (families.ANIMALS, families.GIFTS, families.INGREDIENTS):
        assert all(lo <= len(name) <= hi for name in table.rows), table.name


def test_evidence_plan_follows_what_each_fact_feature_can_show() -> None:
    """사실표 특징마다 알 수 있는 증거 종류(kinds)에 맞춰 요일 배정을 바꾼다(② 작은 실측 2차: 소리를
    목격 날에 둠). 두 날을 바꿔 둘 다 맞으면 맞바꾸고, 짝이 없으면 그 특징으로 알 수 있는 종류로."""
    theme = gift_theme()
    sound = {"kind": "RULE", "feature": "흔들면 나는 소리", "allowed": ["달그락 소리"]}
    shop = {"kind": "HINT", "feature": "선물을 산 가게", "allowed": ["서점", "그릇 가게"]}
    checks.theme_day(theme, "MON")["condition"] = sound
    checks.theme_day(theme, "TUE")["condition"] = shop
    theme["evidencePlan"] = {
        "MON": {"kind": "SIGHTING", "medium": None},  # 소리는 목격으로 알 수 없음
        "TUE": {"kind": "TRACE", "medium": None},  # 산 가게는 흔적으로 알 수 없음
        "WED": {"kind": "SIGHTING", "medium": None},
        "THU": {"kind": "TRACE", "medium": None},
        "FRI": {"kind": "RECORD", "medium": "메모"},
    }
    assert checks.fit_evidence_plan(theme) == ["MON", "TUE"]
    assert theme["evidencePlan"]["MON"]["kind"] == "TRACE"
    assert theme["evidencePlan"]["TUE"]["kind"] == "SIGHTING"
    assert not checks.kind_fits(families.GIFT, "선물을 산 가게", "TRACE")
    assert checks.kind_fits(families.GIFT, "선물을 산 가게", "RECORD")
    assert not checks.kind_fits(families.SECRET_INGREDIENT, "재료 맛", "SIGHTING")
    assert not checks.kind_fits(families.PRANK, "꼬리 모양", "TRACE")
    assert checks.kind_fits(families.LOST, "냄새", "SIGHTING")  # 사실표 밖은 흔적만 봄
    # 짝이 없으면 그 특징으로 알 수 있는 종류로(목격 먼저)
    lone = gift_theme()
    checks.theme_day(lone, "WED")["condition"] = shop
    lone["evidencePlan"] = {d: {"kind": "TRACE", "medium": None} for d in checks.DAYS}
    assert checks.fit_evidence_plan(lone) == ["TUE", "WED"]
    assert lone["evidencePlan"]["WED"]["kind"] == "SIGHTING"


def test_shop_clue_needs_buying_proof() -> None:
    """산 가게 단서는 그 가게에서 '샀다'는 근거 말이 있어야 함(CLUE_PROOF, 칸 고쳐 쓰기)."""
    went = day_with(gift_theme(), "TUE", clue="그릇 가게나 서점에서 나오는 걸 봤대.")
    bad = checks.check_theme(went, 3)
    assert codes(bad) == ["CLUE_PROOF"] and list(checks.fix_targets(bad)) == ["TUE.clue"]
    bought = day_with(gift_theme(), "TUE", clue="선물을 그릇 가게나 서점에서 계산하는 걸 봤대.")
    assert checks.check_theme(bought, 3) == []
    no_thing = day_with(gift_theme(), "TUE", clue="그릇 가게나 서점에서 계산하는 걸 봤대.")
    assert [r.split(" ")[0] for r in checks.check_theme(no_thing, 3)] == ["CLUE_PROOF"]  # 선물 낱말
    assert checks.clue_proof_problems(valid_theme()) == []  # 사실표 종류만


def test_origin_route_every_clue_names_target() -> None:
    # 마지막 확인: '가게 앞 바닥을 봤다'처럼 장소만 말해 대상과 이어지지 않음 → 출처·길은 모든
    # 단서에 대상 낱말(CLUE_OWNER, 칸 고쳐 쓰기)
    assert families.ORIGIN.owner_all and families.ROUTE.owner_all and not families.GIFT.owner_all
    theme = day_with({**valid_theme(), "storyType": "ORIGIN"}, "WED", clue="지붕이 없는 곳이었대.")
    bad = [r for r in checks.check_theme(theme, 3) if r.startswith("CLUE_OWNER")]
    assert [r.split(" ")[1] for r in bad] == ["WED"]  # 대상 낱말(보리)이 없는 수요일 단서만
    assert "CLUE_OWNER" in families.type_rules(families.ORIGIN)
    assert any("대상 낱말" in r for r in prompts.fix_rules(theme, "WED.clue"))
    assert "같은 대상의 증거라 서로 다른 때를 섞은 것이 아니다" in prompts.REVIEW_SYSTEM


def test_in_hand_clues_get_no_clock_time() -> None:
    # 마지막 확인 2차: 증거의 때가 둘(산 때·받은 뒤)이라 시각을 붙이면 '10시 기록·11시에 샀다' 모순
    for t in (families.ORIGIN, families.GIFT, families.SECRET_INGREDIENT, families.ROUTE):
        assert not t.clue_time and not t.hide_times, t.code
    gift = gift_theme()
    gift["days"][0]["evidence"]["when"] = "오후 3시"
    before = gift["days"][0]["clue"]
    assert checks.add_clue_time(gift)["days"][0]["clue"] == before
    assert "단서에 시각(3시·10시 반 등)을 쓰지 않고" in families.type_rules(families.GIFT)
    assert families.INGREDIENTS.features[1] == "재료 맛"


def test_in_hand_sighting_clue_must_not_be_trace() -> None:
    # 마지막 확인 3차: 길 종류에서 '상자에 묻은 먼지 색'을 목격 날에 씀 → CLUE_EVIDENCE 칸 고쳐 쓰기
    theme = day_with(
        {**valid_theme(), "storyType": "ROUTE"}, "TUE", clue="보리 털에 흙이 묻어 있었대."
    )
    bad = [r for r in checks.check_theme(theme, 3) if r.startswith("CLUE_EVIDENCE")]
    assert bad == [
        "CLUE_EVIDENCE TUE clue 목격 날 단서가 대상에 남은 흔적을 말함(그 길·가게에서 대상을 "
        "나르거나 든 사람을 본 목격으로 씀)"
    ]
    assert list(checks.fix_targets(bad)) == ["TUE.clue"]
    lost = day_with(valid_theme(), "TUE", clue="보리 털에 흙이 묻어 있었대.")  # 다른 종류는 그대로
    assert not [r for r in checks.check_theme(lost, 3) if "목격 날 단서가" in r]
    assert families.TIMES.media_of("가로등") == frozenset({"사진", "영상", "일지", "메모"})
    assert "동물 먹이" in prompts.SAFETY_STORY and "동물 먹이" in prompts.PLAN_SYSTEM


def test_mungchi_alone_cut_does_not_draw_in_hand_target() -> None:
    # 그림·영상 실측: 선물 상자 시작 3컷(뭉치 혼자 출동)에서 뭉치가 상자를 들고 그려짐
    gift = gift_theme()
    cut3 = prompts.cut_image_prompt(gift, "INTRO", 3, gift["introCuts"][2], [])
    assert "Do not draw 생일에 받은 리본 상자 in this picture; Mungchi holds nothing." in cut3
    assert "closed (do not show what is inside)" not in cut3
    cut4 = prompts.cut_image_prompt(gift, "INTRO", 4, gift["introCuts"][3], [])
    assert "closed (do not show what is inside)" in cut4  # 사람이 있는 컷은 그대로
    video3 = prompts.video_prompt(gift, "INTRO", 3, gift["introCuts"][2], [])
    assert "Do not show 생일에 받은 리본 상자; Mungchi holds nothing." in video3
