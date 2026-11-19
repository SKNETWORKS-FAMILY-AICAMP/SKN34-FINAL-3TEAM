"""#765 그림에 나오면 안 되는 대상·후보 이름이 콘티 컷 설명(scene·action)에 있으면 CUT_TARGET.

운영(2026-11-18) 초3 초안의 종료 2컷 "느티나무 아래에서 강아지가 … 서 있다"는 대상이 나오면 안 되는
컷이라, 그림이 강아지를 그리면 ANSWER_HINT, 안 그리면 SCENE_FIT으로 어느 쪽도 통과하지 못해 종료
영상이 빠졌다.
"""

import copy
from typing import Any

import pytest

from app.theme_draft import checks, families, prompts
from tests.theme_draft.fixtures import generated_theme, theme_with, valid_theme
from tests.theme_draft.test_families import animal_theme, treasure_cuts
from tests.theme_draft.test_families_in_hand import gift_theme
from tests.theme_draft.test_graph import fixes, gen_llm, review_llm, run

# 운영 초안 9f6a7e20·0a3af355의 종료 2컷 scene 그대로(learning DB 조회, 2026-11-18)
PROD_OUTRO2 = "느티나무 아래에서 강아지가 하준, 윤슬, 공원 관리원, 뭉치 앞에 서 있다."


def cuts_with(theme: dict[str, Any], key: str, index: int, **changes: str) -> dict[str, Any]:
    theme = copy.deepcopy(theme)
    theme[key][index - 1] |= changes
    return theme


def cut_target(theme: dict[str, Any]) -> list[str]:
    return [r for r in checks.check_theme(theme, 3) if r.startswith("CUT_TARGET")]


# ---------------------------------------------------------------- 잃어버린 것·보물 쪽지: 대상 이름
def test_prod_outro2_sentence_is_caught_and_field_fixed() -> None:
    theme = cuts_with(valid_theme(), "outroCuts", 2, scene=PROD_OUTRO2)  # 대상 '강아지 보리'
    bad = checks.check_theme(theme, 3)
    assert bad == [
        "CUT_TARGET outroCuts2.scene 대상이 나오지 않는 컷에 찾는 대상 낱말 '강아지'(없다는 말도 "
        "쓰지 않음)"
    ]
    assert list(checks.fix_targets(bad)) == ["outroCuts2.scene"]  # 줄거리 전체가 아니라 그 칸만
    # 운영 대상 이름 그대로여도 같은 낱말로 걸림
    assert checks.cut_target_word(theme_with(target="반려 강아지"), PROD_OUTRO2) == "강아지"


@pytest.mark.parametrize(
    ("key", "index", "field", "text"),
    [
        ("outroCuts", 2, "scene", "뭉치가 텃밭 앞에서 보리를 바라본다"),  # 있다고 씀
        (
            "outroCuts",
            2,
            "scene",
            "뭉치와 지호가 텃밭 앞에 선다. 보리는 아직 보이지 않는다",
        ),  # 없다고 씀
        ("introCuts", 2, "scene", "지호가 보리가 사라진 걸 알아차린다"),  # 시작 2컷(사건)도
        ("introCuts", 3, "action", "뭉치가 보리를 찾으러 옆으로 달려간다"),
        ("introCuts", 4, "scene", "뭉치와 지호가 강아지 보리를 찾을 방법을 생각한다"),  # 전체 이름
        ("outroCuts", 1, "action", "뭉치가 보리의 털 사진을 보며 고개를 갸웃한다"),  # 조사 '의'
    ],
)
def test_target_name_in_hidden_cut_of_lost(key: str, index: int, field: str, text: str) -> None:
    reasons = cut_target(cuts_with(valid_theme(), key, index, **{field: text}))
    assert reasons and reasons[0].startswith(f"CUT_TARGET {key}{index}.{field} ")


def test_target_name_is_allowed_in_target_cuts_and_captions() -> None:
    """valid_theme은 시작 1컷·종료 3·5·6컷(#779 6컷 틀) scene·action에 보리가 나오고, 대상이
    나오지 않는 시작 6컷 자막(caption)에 보리를 써도 통과(자막은 영상 위 글이라 그리지 않음)."""
    theme = valid_theme()
    assert "보리" in theme["introCuts"][0]["scene"] and "보리" in theme["outroCuts"][2]["scene"]
    theme["introCuts"][5]["caption"] = "뭉치: 보리는 어디에?"
    assert cut_target(theme) == []


@pytest.mark.parametrize(
    ("target", "text"),
    [
        ("관찰 통", "뭉치가 화면 안에서 옆으로 통통 튄다"),  # 한 글자 낱말이 다른 낱말 첫머리
        ("체험 배지", "체험관 복도에 안전모를 쓴 뭉치만 보인다"),  # 대상 이름의 앞 낱말
        ("작은 북", "북쪽 길에서 뭉치가 북끈 장식 조각 앞에 있다"),
        ("아이의 연", "모래 위에 연줄 자국 사진이 놓여 있다"),
        ("나무 이름표", "뭉치가 나뭇잎 무늬 탁자 위에 놓인 단서 앞에 서 있다"),
    ],
)
def test_no_false_positive_on_other_words(target: str, text: str) -> None:
    """#535 실측 줄거리에서 names_target(흔적 단서용)이 걸린 오탐 꼴(대상 낱말을 한 낱말로만 봄)."""
    theme = cuts_with(theme_with(target=target), "outroCuts", 1, scene=text)
    assert not checks.cut_names_target(theme, text)
    assert cut_target(theme) == []


def test_front_word_needs_josa() -> None:
    """대상 이름의 앞 낱말은 조사가 붙어야 걸림: '강아지 보리'의 '강아지가'는 잡고, '나무 이름표'의
    '나무 사이'·'전시 그림'의 '전시 담당'(수목원·미술관 장면)은 안 걸림. 조사가 붙으면 다른 뜻이어도
    걸리지만('나무와 풀잎') 사유에 걸린 낱말을 적어 고쳐 쓰기가 그 낱말만 뺌(#535 실측 582건 중
    3건)."""
    assert checks.cut_target_word(valid_theme(), "강아지가 텃밭 앞에 서 있다") == "강아지"
    tree = theme_with(target="나무 이름표")
    assert checks.cut_target_word(tree, "나무 사이의 빈 길에 뭉치만 있다") is None
    assert checks.cut_target_word(theme_with(target="전시 그림"), "전시 담당 선생님 곁") is None
    theme = cuts_with(tree, "outroCuts", 1, scene="나무와 풀잎 사이의 뭉치")
    assert cut_target(theme) == [
        "CUT_TARGET outroCuts1.scene 대상이 나오지 않는 컷에 찾는 대상 낱말 '나무'(없다는 말도 "
        "쓰지 않음)"
    ]


def test_treasure_hides_target_from_intro1() -> None:
    """보물 쪽지는 시작 1컷도 대상이 나오지 않음(target_cuts 종료 3·4만)."""
    treasure = {**valid_theme(), "storyType": "TREASURE"}
    assert [r.split(" ")[1] for r in cut_target(treasure)] == [
        "introCuts1.scene",
        "introCuts1.action",
    ]
    treasure["introCuts"] = treasure_cuts(treasure)
    assert cut_target(treasure) == []


# ---------------------------------------------------------------- 사실표 종류: 후보 이름
def test_animal_candidate_in_outro1_but_answer_allowed_from_outro3() -> None:
    theme = animal_theme()
    assert cut_target(theme) == []
    bad = cut_target(
        cuts_with(theme, "outroCuts", 1, scene="뭉치가 고양이 발자국 사진 앞에 서 있다")
    )
    assert bad == ["CUT_TARGET outroCuts1.scene 후보가 나오지 않는 컷에 후보 이름 ['고양이']"]
    answer = theme["answer"]
    shown = cuts_with(theme, "outroCuts", 3, scene=f"사육사가 창고 앞에서 {answer}를 바라본다")
    assert cut_target(shown) == []  # 종료 3컷은 정답 동물이 나오는 컷(6컷 틀 answer_cuts)
    run = cuts_with(theme, "outroCuts", 2, scene=f"뭉치가 {answer}가 있는 창고로 달려간다")
    assert [r.split(" ")[1] for r in cut_target(run)] == ["outroCuts2.scene"]  # 뭉치 혼자 컷


def test_gift_candidate_hidden_in_outro2_and_secret_food_not_checked() -> None:
    gift = gift_theme()
    assert cut_target(gift) == []
    item = gift["candidates"][0]
    bad = cut_target(cuts_with(gift, "outroCuts", 2, scene=f"모두 {item}이 든 상자 앞에 모인다"))
    assert [r.split(" ")[1] for r in bad] == ["outroCuts2.scene"]
    # 비밀 재료 음식(대상)은 엔딩 전에도 덮인 채 나오는 틀이라 대상 이름 검사에서 뺌
    food = {**gift, "storyType": "SECRET_INGREDIENT", "target": "대회에 낸 할머니의 떡"}
    food = cuts_with(food, "outroCuts", 2, scene="할머니와 함께 덮인 떡 접시 앞에 모인다")
    assert families.SECRET_INGREDIENT.hidden_target_cuts == frozenset()
    assert [r for r in cut_target(food) if "찾는 대상" in r] == []


def test_hidden_cut_scope_by_story_type() -> None:
    expect = {
        "LOST": ({("INTRO", 2), ("INTRO", 3), ("INTRO", 4), ("OUTRO", 1), ("OUTRO", 2)}, set()),
        "TREASURE": ({("INTRO", i) for i in range(1, 5)} | {("OUTRO", 1), ("OUTRO", 2)}, set()),
        "PRANK": (set(), {("OUTRO", 1)}),
        "FOOTPRINT": (set(), {("OUTRO", 1)}),
        "ORIGIN": (set(), set()),
        "ROUTE": (set(), set()),
        "GIFT": (set(), {("OUTRO", 1), ("OUTRO", 2)}),
        "SECRET_INGREDIENT": (set(), {("OUTRO", 1), ("OUTRO", 2)}),
        "WHEN": (set(), {("OUTRO", 1)}),
        "VEHICLE": (set(), {("OUTRO", 1)}),
        "SOUND": (set(), {("OUTRO", 1)}),
    }
    assert set(expect) == set(families.STORY_TYPES)
    for code, (target, candidate) in expect.items():
        t = families.STORY_TYPES[code]
        assert (set(t.hidden_target_cuts), set(t.hidden_candidate_cuts)) == (target, candidate), (
            code
        )


# ---------------------------------------------------------------- 프롬프트
def test_plan_rules_list_cuts_where_target_or_candidates_appear() -> None:
    lost = families.type_rules(families.LOST)
    assert (
        "찾는 대상(target)이 그림에 나오는 컷은 introCuts 1, outroCuts 3·5·6뿐이다. 그 밖의 컷"
        "(introCuts 2·3·4·5·6, outroCuts 1·2·4)" in lost
    )
    assert "없다는 말도 쓰지 않는다" in lost
    # 종료 역할 2(도착)는 6컷에서 뭉치 달리기 컷이 맡아 줄거리 지시에 주지 않음(#779)
    assert "찾는 대상은 아직 나오지 않아 scene·action에 쓰지 않음" not in lost
    prank = families.type_rules(families.PRANK)
    # #779: 동물 종류는 종료 6컷(뭉치에게 고마워함)에 동물이 이미 떠남(target_off_cuts)
    assert "후보(동물) 이름은 정답을 포함해 outroCuts 3·5의 scene·action에만 쓴다" in prank
    assert "outroCuts 1·2·4·6에는 쓰지 않는다" in prank
    # 손에 든 것도 뭉치 혼자 나오는 컷(6컷 틀)에는 그리지 않아 그 컷만 숨김(#779)
    assert "(introCuts 4·5, outroCuts 1·2·4)" in families.hidden_cut_rules(families.ORIGIN)
    assert "그림에 나오지 않는 것을 '○○는 보이지 않는다'처럼 쓰지 않는다" in prompts.PLAN_SYSTEM


def test_fix_rules_for_hidden_cut() -> None:
    lost = prompts.fix_rules(theme_with(target="반려 강아지"), "outroCuts2.scene")
    assert any("찾는 대상('반려 강아지')이 나오지 않는다" in r for r in lost)
    assert "종료 콘티라 정답 이름을 써도 된다." in lost  # 정답(장소) 이름은 그대로 됨
    shown = prompts.fix_rules(valid_theme(), "outroCuts3.scene")
    assert not any("찾는 대상(" in r for r in shown)
    animal = prompts.fix_rules(animal_theme(), "outroCuts1.action")
    assert any(r.startswith("이 컷 그림에는 후보가 나오지 않는다: 정답을 포함해") for r in animal)
    assert "종료 콘티라 정답 이름을 써도 된다." not in animal


def test_review_and_covered_food_prompts() -> None:
    assert "찾는 대상이나 후보가 보이지 않는 것은 장면 글에 나와도 결함이 아니다" in (
        prompts.IMAGE_REVIEW_SYSTEM
    )
    for system in (prompts.IMAGE_REVIEW_SYSTEM, prompts.VIDEO_REVIEW_SYSTEM):
        assert prompts.COVERED_REVIEW in system
    gift = gift_theme()
    food = {**gift, "storyType": "SECRET_INGREDIENT", "target": "대회에 낸 할머니의 떡"}
    covered = "대회에 낸 할머니의 떡 stays covered: only a covered dish or a closed lunchbox"
    assert covered in prompts.video_prompt(food, "INTRO", 6, food["introCuts"][5], [])
    assert covered not in prompts.video_prompt(food, "OUTRO", 3, food["outroCuts"][2], [])
    # 뭉치 혼자 나오는 컷(#779 6컷 틀)은 덮인 그릇도 없이 아예 보이지 않음
    run_cut = prompts.video_prompt(food, "OUTRO", 2, food["outroCuts"][1], [])
    assert covered not in run_cut and "Mungchi holds nothing" in run_cut
    lost = valid_theme()  # 다른 종류는 그대로 '그리지 마라'
    assert "Do not draw 강아지 보리 anywhere" in prompts.cut_image_prompt(
        lost, "INTRO", 3, lost["introCuts"][2], []
    )


# ---------------------------------------------------------------- 그래프
def test_graph_rewrites_only_the_hidden_cut_field() -> None:
    """종료 2컷에 대상이 있으면 줄거리를 다시 만들지 않고 그 칸만 고쳐 써서 통과."""
    bad = cuts_with(valid_theme(), "outroCuts", 2, scene=PROD_OUTRO2)
    gen = gen_llm(
        theme=lambda n, d: generated_theme(bad),
        fix=lambda n, d: fixes(
            ("outroCuts2.scene", "뭉치와 하준이 느티나무 아래에 도착해 바라본다")
        ),
    )
    response = run(gen, review_llm())
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 1 and gen.count("GeneratedFixes") == 1
    user = gen.users("GeneratedFixes")[0]
    assert "path: outroCuts2.scene" in user and "찾는 대상('강아지 보리')이 나오지 않는다" in user


def test_six_cut_hidden_scope_by_story_type() -> None:
    """#779 6컷 틀: 4컷 번호를 같은 역할 컷으로 옮기고 뭉치 혼자 나오는 컷(시작 4·5, 종료 1·2·4)은
    대상·후보를 그리지 않아 숨김."""
    alone = {("INTRO", 4), ("INTRO", 5), ("OUTRO", 1), ("OUTRO", 2), ("OUTRO", 4)}
    lost = families.type_cuts(families.LOST, 6)
    assert lost.target == {("INTRO", 1), ("OUTRO", 3), ("OUTRO", 5), ("OUTRO", 6)}
    assert alone <= lost.hidden_target
    prank = families.type_cuts(families.PRANK, 6)
    # #779: 동물 종류는 종료 6컷(뭉치에게 고마워함)에서 동물을 뺌(target_off_cuts)
    assert prank.answer == prank.target == {("OUTRO", 3), ("OUTRO", 5)}
    assert prank.hidden_candidate == {("OUTRO", 1), ("OUTRO", 2), ("OUTRO", 4), ("OUTRO", 6)}
    gift = families.type_cuts(families.GIFT, 6)
    assert not (gift.target & alone)  # 손에 든 선물 상자도 뭉치 혼자 컷에는 그리지 않음
    legacy = families.type_cuts(families.LOST, 4)  # 예전 4컷 초안은 종류 정의 그대로
    assert legacy.target == families.LOST.target_cuts
