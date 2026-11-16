"""줄거리 종류·가족 등록표 (#634, 설계 ai.md 17.8): 씨앗 읽기, 종류 규칙 주입, 가족별 코드 검사·
프롬프트·그림 규칙."""

import copy
import json
from typing import Any

import pytest

from app.config import get_settings
from app.mission_draft.models import Draft, MissionDraftRequest
from app.theme_draft import checks, families, prompts
from app.theme_draft.models import GeneratedStoryReview, ThemeDraftRequest
from tests.theme_draft.fixtures import (
    day_with,
    feature,
    generated_theme,
    mission_draft,
    theme_with,
    valid_theme,
)
from tests.theme_draft.helpers import request_body
from tests.theme_draft.test_graph import gen_llm, review_llm, run

# learning ThemeTopicSeeds 씨앗 그대로(종류 이름·라벨은 두 서비스가 같은 표)
SEEDS = {
    "LOST": "줄거리: 잃어버린 것 찾기 / 뭉치 역할: 탐정(탐정 모자·돋보기) / 장소: 동네 시장 / "
    "찾는 대상: 가게 주인 아이의 반려 고양이",
    "TREASURE": "줄거리: 보물 쪽지 따라가기 / 뭉치 역할: 보물 탐험대(탐험 조끼·나침반 목걸이) / "
    "장소: 할아버지 댁 뒷마당 / 찾는 대상: 할아버지가 숨긴 타임캡슐",
    "PRANK": "줄거리: 동물 장난꾸러기 찾기 / 뭉치 역할: 경찰관(경찰 제복·경찰 모자) / 장소: 마을 "
    "떡집 / 밝힐 것: 떡을 몰래 먹은 동물",
    "FOOTPRINT": "줄거리: 발자국 주인 찾기 / 뭉치 역할: 소방관(방화복·소방 헬멧) / 장소: 마을 "
    "소방서 앞마당 / 밝힐 것: 진흙길에 발자국을 남긴 동물",
}
ANIMALS = {"놀이터": "고양이", "텃밭": "너구리", "창고": "까치", "정자": "다람쥐"}


def codes(reasons: list[str]) -> list[str]:
    return sorted(r.split(" ")[0] for r in reasons)


def animal_theme(story_type: str = "PRANK") -> dict[str, Any]:
    """valid_theme의 장소 후보를 동물로 바꾼 동물 주인공 줄거리(check_theme을 통과)."""
    theme = copy.deepcopy(valid_theme())
    theme |= {
        "storyType": story_type,
        "target": "떡을 몰래 먹은 동물",
        "incident": "떡 접시가 비어 있고 떡 부스러기가 흩어짐",
        "answerLook": "귀 끝이 까맣고 꼬리가 굵은 갈색 너구리",
        "candidates": [ANIMALS[c] for c in theme["candidates"]],
        "answer": ANIMALS[theme["answer"]],
        "bigQuestion": "떡을 몰래 먹은 건 누구였을까?",
    }
    # 특징은 동물 사실표 그대로(#634: 값은 코드가 표로 맞춤)
    cands = theme["candidates"]
    theme["features"] = [
        feature(name, {c: families.animal_fact(c, name) or "" for c in cands})
        for name in families.ANIMAL_FEATURES
    ]
    # 월(흔적) 발톱으로 고양이, 수(목격) 발 수로 까치, 금(기록) 꼬리로 다람쥐가 빠짐
    for d, clue, kind, feat, allowed in (
        ("MON", "그 동물 발자국에 발톱 자국이 있었어.", "RULE", "발자국의 발톱", ["발톱 자국"]),
        (
            "TUE",
            "지나간 동물의 부드러운 털이나 깃털을 봤대.",
            "HINT",
            "몸을 덮은 것",
            ["부드러운 털", "깃털"],
        ),
        ("WED", "네 발로 걷는 뒷모습을 봤대.", "RULE", "발자국 발 수", ["네 발"]),
        ("THU", "그 동물이 남긴 부드러운 털이 있었어.", "HINT", "몸을 덮은 것", ["부드러운 털"]),
        ("FRI", "사진에 굵은 꼬리가 찍혔어.", "RULE", "꼬리 모양", ["굵은 꼬리"]),
    ):
        day = checks.theme_day(theme, d)
        day["clue"] = clue
        day["condition"] = {"kind": kind, "feature": feat, "allowed": allowed}
    return theme


# ---------------------------------------------------------------- 씨앗 읽기·종류 규칙
@pytest.mark.parametrize("code", list(SEEDS))
def test_learning_seed_topic_gives_story_type(code: str) -> None:
    found = families.parse_topic(SEEDS[code])
    assert found is not None and found.code == code
    assert (
        prompts.seed_story_type(ThemeDraftRequest.model_validate(request_body(topic=SEEDS[code])))
        == code
    )


def test_old_seed_is_lost_and_free_text_or_mismatch_is_none() -> None:
    assert families.parse_topic("뭉치 역할: 탐정 / 장소: 시장 / 찾는 대상: 고양이") is families.LOST
    assert families.parse_topic("우리 반 텃밭") is None
    assert families.parse_topic(None) is None
    assert (
        families.parse_topic("줄거리: 우주 여행 / 뭉치 역할: 탐정 / 장소: 달 / 찾는 대상: 깃발")
        is None
    )
    # 라벨이 종류와 안 맞음(발자국 주인은 '밝힐 것')
    assert (
        families.parse_topic(
            "줄거리: 발자국 주인 찾기 / 뭉치 역할: 탐정 / 장소: 숲 / 찾는 대상: 동물"
        )
        is None
    )


def test_plan_user_gets_only_seed_type_rules_or_all_for_free_text() -> None:
    prank = prompts.plan_user(
        ThemeDraftRequest.model_validate(request_body(topic=SEEDS["PRANK"])), []
    )
    assert "storyType: PRANK" in prank and "줄거리 종류: 동물 장난꾸러기 찾기" in prank
    assert (
        "줄거리 종류: 잃어버린 것 찾기" not in prank
        and "줄거리 종류: 보물 쪽지 따라가기" not in prank
    )
    free = prompts.plan_user(
        ThemeDraftRequest.model_validate(request_body(topic="우리 반 텃밭")), []
    )
    assert "주제에 가장 맞는 종류 하나를 골라" in free
    assert all(f"줄거리 종류: {t.label}" in free for t in families.STORY_TYPES.values())
    # 공통 규칙: 제복 모양은 되고 휘장·글자는 안 됨, 큰 질문 종류는 종류 규칙으로
    assert "제복 모양은 되지만 실제 기관 휘장·글자는 쓰지" in prompts.PLAN_SYSTEM
    assert "누구에게(누구에게 맡겼나)" not in prompts.PLAN_SYSTEM


def test_seed_story_type_overrides_model_value_in_graph() -> None:
    """씨앗이면 모델이 다른 종류를 써도 코드가 주제의 종류로 덮어씀(검토 user에 그 종류가 감)."""
    gen = gen_llm(theme=lambda n, d: generated_theme(theme_with(storyType="LOST")))
    review = review_llm()
    response = run(gen, review, request_body(topic=SEEDS["TREASURE"]))
    assert response.failure is None
    user = json.loads(review.users(GeneratedStoryReview.__name__)[0])
    assert user["theme"]["storyType"].startswith("TREASURE(")
    assert response.theme is not None
    dumped = response.theme.model_dump(by_alias=True)
    assert not {"storyType", "incident", "answerLook"} & set(dumped)  # 내부 칸(계약 그대로)


# ---------------------------------------------------------------- ③ 코드 검사
def test_animal_theme_passes_and_lost_theme_has_no_candidate_check() -> None:
    assert checks.check_theme(animal_theme(), 3) == []
    lost = day_with(valid_theme(), "MON", sceneNote="뭉치와 지호가 놀이터 옆 길을 살펴보는 장면")
    assert "CANDIDATE_NAME" not in codes(checks.check_theme(lost, 3))


def test_animal_required_fields_and_target_without_candidate_names() -> None:
    bad = checks.check_theme({**animal_theme(), "incident": " ", "answerLook": None}, 3)
    assert [r for r in bad if r.startswith("REQUIRED")] == [
        "REQUIRED incident",
        "REQUIRED answerLook",
    ]
    bad = checks.check_theme({**animal_theme(), "target": "떡을 몰래 먹은 너구리"}, 3)
    assert any(r.startswith("TARGET_NAMES target에 후보 동물 이름 ['너구리']") for r in bad)


def test_candidate_animal_before_ending_is_field_fixed() -> None:
    theme = day_with(
        animal_theme(), "TUE", sceneNote="떡집 앞에서 고양이 한 마리가 낮잠을 자는 장면"
    )
    bad = checks.check_theme(theme, 3)
    assert bad == ["CANDIDATE_NAME TUE.sceneNote에 후보 동물 이름 ['고양이'](엔딩 전 글)"]
    assert list(checks.fix_targets(bad)) == ["TUE.sceneNote"]
    # 인물 모습은 칸 고쳐 쓰기 대상이 아니라 줄거리를 다시 만듦
    looks = theme_with(characters=[{"name": "지호", "look": "까치 무늬 티셔츠를 입은 아이"}])
    bad = checks.check_theme({**animal_theme(), "characters": looks["characters"]}, 3)
    assert codes(bad) == ["CANDIDATE_NAME"] and checks.fix_targets(bad) == {}
    # 종료 이야기·종료 콘티·단서는 엔딩 뒤나 후보 목록과 함께 보여 검사하지 않음
    assert checks.check_theme({**animal_theme(), "outro": "범인 아닌 너구리를 찾았다"}, 3) == [
        "UNSAFE ['범인']"
    ]


def test_candidate_words_heads_and_one_letter_boundaries() -> None:
    assert checks.candidate_words({"candidates": ["옆집 고양이", "까치"]}) == [
        "옆집 고양이",
        "고양이",
        "까치",
    ]
    one = {"candidates": ["개", "쥐"]}
    assert checks.candidate_names(one, "개울 옆 소리") == []
    assert checks.candidate_names(one, "개가 지나가고 쥐를 봤어") == ["개", "쥐"]
    assert checks.candidate_names({"candidates": ["옆집 고양이"]}, "고양이 발자국") == ["고양이"]


def test_animal_trace_words_and_features() -> None:
    footprint = {"storyType": "FOOTPRINT", "target": "눈길에 발자국을 남긴 동물"}
    assert checks.target_words(footprint) == ["동물"]  # '남긴'이 대상 낱말로 뽑히던 틈
    # 꾸미는 말(받침 ㄴ·ㄹ)은 대상 낱말에서 뺌(작은 실측: '숨긴'), 모든 종류 공통
    assert checks.target_words({"target": "눈길에 발자국을 남긴 동물"}) == ["동물"]
    assert checks.target_words({"target": "할아버지가 숨긴 타임캡슐"}) == ["타임캡슐"]
    assert checks.target_words({"target": "강아지 보리"}) == ["보리", "강아지"]
    assert not checks.traceable("발가락 수") and checks.traceable("발자국 발 수", families.PRANK)
    assert checks.traceable("몸을 덮은 것", families.PRANK) and checks.traceable(
        "발자국의 발톱", families.PRANK
    )
    assert not checks.traceable("꼬리 모양", families.PRANK)  # 꼬리는 목격·기록 날
    assert not checks.traceable("냄새", families.PRANK)
    bad = checks.check_theme(
        day_with(animal_theme(), "MON", clue="발자국에 발톱 자국이 있었어."), 3
    )
    assert bad == [
        "CLUE_OWNER MON clue 흔적 단서에 찾는 대상 낱말(동물)이 없음(누구의 흔적인지 밝힘)"
    ]


def test_animal_fact_table_values_are_fixed_by_code() -> None:
    """모델이 지은 동물 특징 값은 사실표 값으로 맞추고, 그 특징을 쓰는 날 허용 값은 허용하던 후보의
    새 값으로 옮긴다(빼려던 후보가 그대로). 표 밖 동물·특징은 FACT_TABLE로 다시 생성."""
    theme = animal_theme()
    tail = next(f for f in theme["features"] if f["name"] == "꼬리 모양")
    for v in tail["values"]:
        v["value"] = {"너구리": "고리무늬 꼬리"}.get(v["candidate"], v["value"])
    checks.theme_day(theme, "FRI")["condition"]["allowed"] = ["고리무늬 꼬리"]
    assert checks.fact_table_problems(theme) == [
        "FACT_TABLE 특징 값이 사실표와 다름 ['꼬리 모양·너구리']"
    ]
    assert checks.apply_facts(theme) == ["꼬리 모양"]
    assert checks.theme_day(theme, "FRI")["condition"]["allowed"] == ["굵은 꼬리"]
    assert checks.fact_table_problems(theme) == []
    assert checks.apply_facts(valid_theme()) == []  # 숨은 것 가족은 그대로
    outside = {**animal_theme(), "candidates": ["고양이", "너구리", "까치", "여우"]}
    outside["features"] = [*outside["features"], feature("다니는 때", {"고양이": "밤"})]
    assert codes(checks.fact_table_problems(outside)) == ["FACT_TABLE", "FACT_TABLE"]


def test_animal_rules_carry_fact_table_and_values_do_not_contain_each_other() -> None:
    rules = families.type_rules(families.PRANK)
    assert "고양이 | 부드러운 털 | 네 발 | 발바닥 자국 | 가는 꼬리" in rules
    for i, name in enumerate(families.ANIMAL_FEATURES):
        values = {row[i] for row in families.ANIMAL_FACTS.values()}
        assert not [
            (a, b)
            for a in values
            for b in values
            if a != b and a.replace(" ", "") in b.replace(" ", "")
        ], name  # 값끼리 포함되면 단서 문장 허용 밖 값 검사가 헷갈림


@pytest.mark.parametrize(
    ("text", "hit"),
    [
        ("경찰관이 범인을 찾는다", ["범인"]),
        ("수갑을 채웠다", ["수갑"]),
        ("떡을 훔쳐 갔다", ["훔쳐"]),
        ("도둑이 들었다", ["도둑"]),
        ("도둑고양이가 지나갔다", []),
        ("도둑게가 기어간다", []),
    ],
)
def test_unsafe_police_words(text: str, hit: list[str]) -> None:
    assert sorted(set(checks.UNSAFE.findall(text))) == hit


def test_mungchi_grabbing_is_a_hand_action() -> None:
    assert checks.cut_action_problems("뭉치가 너구리를 붙잡는다")
    assert checks.cut_action_problems("뭉치가 고양이를 잡아 올린다")
    assert not checks.cut_action_problems("사육사가 너구리를 안아 올리고 뭉치는 통통 튄다")


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


def test_mission_dialogue_and_hook_with_candidate_animal_are_flagged() -> None:
    s = get_settings()
    draft = Draft.model_validate(
        mission_draft(
            "ANALYZE", question="고양이가 좋아하는 떡을 생각하며 글을 써 보자."
        ).model_dump()
    )
    args = (
        mission_inputs(),
        draft,
        3,
        s.mission_draft_question_max_chars,
        s.followup_example_overlap_chars,
    )
    assert "CANDIDATE_NAME" in codes(checks.check_mission(animal_theme(), *args))
    assert "CANDIDATE_NAME" not in codes(checks.check_mission(valid_theme(), *args))
    said = {"lines": [{"speaker": "지호", "text": "까치가 울던데?"}], "discoverySpeaker": "뭉치"}
    plain = Draft.model_validate(mission_draft("ANALYZE").model_dump())
    bad = checks.check_dialogue(
        animal_theme(), "MON", said, plain, 3, s.followup_example_overlap_chars
    )
    assert "CANDIDATE_NAME 대화 줄에 후보 동물 이름 ['까치']" in bad
    assert "CANDIDATE_NAME" in checks.hook_problems(
        animal_theme(), "MON", "다람쥐 흔적을 풀어 보자", plain, 8
    )


# ---------------------------------------------------------------- 프롬프트·그림 규칙
@pytest.mark.parametrize(
    ("code", "allowed"),
    [
        ("LOST", {("INTRO", 1), ("OUTRO", 3), ("OUTRO", 4)}),
        ("TREASURE", {("OUTRO", 3), ("OUTRO", 4)}),
        ("PRANK", {("OUTRO", 2), ("OUTRO", 3), ("OUTRO", 4)}),
        ("FOOTPRINT", {("OUTRO", 2), ("OUTRO", 3), ("OUTRO", 4)}),
    ],
)
def test_target_cuts_by_story_type(code: str, allowed: set[tuple[str, int]]) -> None:
    theme = {"storyType": code}
    shown = {
        (s, i)
        for s in ("INTRO", "OUTRO")
        for i in range(1, 5)
        if prompts.cut_shows_target(theme, s, i)
    }
    assert shown == allowed


def test_animal_pictures_hide_candidates_and_keep_answer_look() -> None:
    theme = animal_theme()
    cut = theme["introCuts"][3]
    intro = prompts.cut_image_prompt(theme, "INTRO", 4, cut, [])
    assert "Do not draw any of these animals: 고양이, 너구리, 까치, 다람쥐." in intro
    outro = prompts.cut_image_prompt(theme, "OUTRO", 2, theme["outroCuts"][1], [])
    assert "귀 끝이 까맣고 꼬리가 굵은 갈색 너구리" in outro and "Do not draw" not in outro
    video = prompts.video_prompt(theme, "OUTRO", 3, theme["outroCuts"][2], [])
    assert "gently lift it in place" in video and "귀 끝이 까맣고" in video
    lost_video = prompts.video_prompt(valid_theme(), "OUTRO", 2, valid_theme()["outroCuts"][1], [])
    assert "Do not show 강아지 보리." in lost_video and "these animals" not in lost_video


def test_review_users_use_answer_keys_and_story_type() -> None:
    theme = animal_theme()
    user = json.loads(
        prompts.image_review_user(
            theme, "장면", ids=("ANSWER_HINT",), has_mungchi=True, shows_target=False
        )
    )
    assert user["answer"] == "너구리" and user["answerAllowed"] is False
    assert (
        user["candidates"] == ["고양이", "너구리", "까치", "다람쥐"] and "answerPlace" not in user
    )
    assert user["storyType"].startswith("PRANK(")
    video = json.loads(prompts.video_review_user(theme, theme["outroCuts"][2], True, True, True))
    assert video["answerAllowed"] is True and video["answerLook"].startswith("귀 끝")
    for system in (prompts.REVIEW_SYSTEM, prompts.IMAGE_REVIEW_SYSTEM, prompts.VIDEO_REVIEW_SYSTEM):
        assert prompts.SAFETY_STORY in system


def test_animal_mission_story_uses_incident_and_bans_candidate_heads() -> None:
    theme = animal_theme()
    text = prompts.story_text(theme, "MON", 3)
    assert "이번 주 사건: 떡 접시가 비어 있고" in text and "동물 이야기·동물 설명" in text
    assert (
        "동물 후보 이름, 머리 낱말·정답의 표 값 포함): 고양이, 너구리, 까치, 다람쥐, 굵은 꼬리"
        in text
    )
    assert "이번 주 사건" not in prompts.story_text(valid_theme(), "MON", 3)
    assert prompts.story_brief(theme, "MON")["incident"].startswith("떡 접시")
    assert "incident" not in prompts.story_brief(valid_theme(), "MON")


def test_fix_rules_follow_story_type() -> None:
    animal = animal_theme()
    assert prompts.fix_rules(animal, "outro")[0].startswith(
        "종료 이야기의 마무리 장면만 쓴다: 정답 동물을"
    )
    treasure = {**valid_theme(), "storyType": "TREASURE"}
    assert "쪽지를 받아 들고 놀람" in prompts.fix_rules(treasure, "introCuts2.scene")[0]
    assert "보물 속 편지" in prompts.fix_rules(treasure, "outroCuts4.action")[0]
    assert "고양이" in prompts.fix_rules(animal, "TUE.sceneNote")[1]  # 머리 낱말까지 쓰지 말 낱말


def test_note_style_clue_is_field_fixed_but_ratio_is_not() -> None:
    """'오후 3시 목격: 짧은 꼬리.' 같은 쪽지 꼴은 CLUE_WORDING(칸 고쳐 쓰기), 비율·시각은 그대로."""
    note = {
        "clue": "오후 3시 목격: 짧고 굵은 꼬리.",
        "condition": {"kind": "HINT", "allowed": ["a"]},
    }
    assert checks.clue_wording_problems(note) == [
        "단서를 '목격:'처럼 쪽지 꼴로 씀(누가 무엇을 봤는지 한 문장으로)"
    ]
    for ok in ("길이는 2:3이었어.", "3:30에 찍힌 사진이야."):
        assert checks.clue_wording_problems({"clue": ok, "condition": {"kind": "HINT"}}) == []
    bad = checks.check_theme(day_with(animal_theme(), "FRI", clue="사진: 굵은 꼬리."), 3)
    assert list(checks.fix_targets(bad)) == ["FRI.clue"]


def test_empty_incident_is_field_fixed_and_subject_after_place_word_is_found() -> None:
    """판정 실측 보강: 사건·정답 동물 모습 칸이 비면 그 칸만 써 넣고(줄거리 다시 생성 대신),
    '강가 안내원이'처럼 장소 낱말 뒤 주어도 잡아 뭉치 동작으로 오판하지 않음."""
    bad = checks.check_theme({**animal_theme(), "incident": ""}, 3)
    assert bad == ["REQUIRED incident"] and list(checks.fix_targets(bad)) == ["incident"]
    assert checks.text_max("incident") == 60
    assert "이번 주 사건 물건·일 한 줄" in prompts.fix_rules(animal_theme(), "incident")[0]
    assert not checks.cut_action_problems("강가 안내원이 너구리를 부드럽게 안아 올린다.")
    assert checks.cut_action_problems("강가에서 뭉치가 너구리를 안아 올린다.")


def test_treasure_hide_spot_before_ending_is_field_fixed() -> None:
    """보물 쪽지: 숨긴 곳은 끝까지 모르는 답이라 엔딩 전 글에 '숨긴 자리'를 쓰면 HIDE_SPOT(칸 고쳐
    쓰기). 다른 종류·종료 이야기는 보지 않음."""
    treasure = {**valid_theme(), "storyType": "TREASURE"}
    assert checks.check_theme(treasure, 3) == []
    bad = checks.check_theme(day_with(treasure, "MON", discovery="숨긴 자리에서 흔적을 찾았어!"), 3)
    assert codes(bad) == ["HIDE_SPOT"] and list(checks.fix_targets(bad)) == ["MON.discovery"]
    assert (
        "숨겨 둔 곳"
        in checks.hide_spot_problems(day_with(treasure, "TUE", clue="숨겨 둔 곳 바닥은 흙이었어."))[
            0
        ]
    )
    lost = day_with(valid_theme(), "MON", discovery="숨긴 자리에서 흔적을 찾았어!")
    assert "HIDE_SPOT" not in codes(checks.check_theme(lost, 3))
    assert "HIDE_SPOT" in families.type_rules(families.TREASURE)
