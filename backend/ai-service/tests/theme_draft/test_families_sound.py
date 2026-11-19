"""⑤ 소리 탐정 (#634, 설계 ai.md 17.8.18): 소리 사실표·한 범주(SAME_KIND)·흔적 없음·기록 매체 맞춤
(fit_media)·후보를 가르는 값 감추기(strict_facts)·모든 단서에 '소리'(CLUE_OWNER)·정답 모습 고정·
결말 정답(OUTRO_ANSWER), ④에서 시간 탐정 표시로 쓰던 칸을 나눈 뒤에도 시간 탐정이 그대로인지."""

import copy
from typing import Any

import pytest

from app.mission_draft.models import Draft
from app.theme_draft import checks, families, prompts
from app.theme_draft.models import ThemeDraftRequest
from tests.theme_draft.fixtures import day, feature, mission_draft, valid_theme
from tests.theme_draft.helpers import request_body

SEED = (
    "줄거리: 소리 탐정 / 뭉치 역할: 소리 박사(헤드폰·연구 가운) / 장소: 할머니 댁 시골집 / "
    "밝힐 것: 할머니 댁 마당에서 밤마다 들린 소리"
)
ANIMALS = ["부엉이", "고양이", "생쥐", "너구리"]


def sound_theme() -> dict[str, Any]:
    """소리 탐정 줄거리(동물 범주, 정답 너구리, check_theme 통과). 월 RULE 옮겨 다니는 소리 →
    부엉이, 목 RULE 뒤적이는 소리 → 고양이·생쥐. 목격·기록만."""
    theme = copy.deepcopy(valid_theme())
    theme |= {
        "storyType": "SOUND",
        "target": "할머니 댁 마당에서 밤마다 들린 소리",
        "bigQuestion": "밤마다 들린 소리의 정체는 무엇이었을까?",
        "candidates": list(ANIMALS),
        "answer": "너구리",
        "answerLook": "눈가가 까맣고 꼬리가 굵은 갈색 너구리",
        # 동물 후보끼리 값이 모두 같은 '소리 나는 밤'은 넣지 않음(FACT_TABLE)
        "features": [
            feature(name, {c: families.SOUNDS.fact(c, name) or "" for c in ANIMALS})
            for name in families.SOUNDS.features
            if name != "소리 나는 밤"
        ],
        "days": [
            day(
                "MON",
                "이웃이 옮겨 다니는 소리를 들었대.",
                "목격",
                "RULE",
                "소리 움직임",
                ["옮겨 다니는 소리"],
                "SIGHTING",
            ),
            day(
                "TUE",
                "녹음에 옮겨 다니는 소리가 담겼어.",
                "기록",
                "HINT",
                "소리 움직임",
                ["옮겨 다니는 소리"],
                "RECORD",
            ),
            day(
                "WED",
                "할머니도 옮겨 다니는 소리를 들었대.",
                "시각",
                "HINT",
                "소리 움직임",
                ["옮겨 다니는 소리"],
                "SIGHTING",
            ),
            day(
                "THU",
                "동생이 뒤적이는 소리를 들었대.",
                "소리",
                "RULE",
                "소리 느낌",
                ["뒤적이는 소리"],
                "SIGHTING",
            ),
            day(
                "FRI",
                "일지에 쓰레기통 둘레에서 소리가 났다고 적혔어.",
                "습성",
                "HINT",
                "소리 난 곳",
                ["쓰레기통 둘레"],
                "RECORD",
            ),
        ],
    }
    for d in theme["days"]:
        d["evidence"]["when"] = "소리가 나던 밤"
    return theme


# ---------------------------------------------------------------- 등록표·표
def test_sound_seed_and_table() -> None:
    found = families.parse_topic(SEED)
    assert found is families.SOUND and found.family == "SOUND"
    user = prompts.plan_user(ThemeDraftRequest.model_validate(request_body(topic=SEED)), [])
    assert "storyType: SOUND" in user and "SAME_KIND" in user and "CLUE_OWNER" in user
    table = families.SOUNDS
    assert set(table.groups.values()) == {"동물", "물건"}  # type: ignore[union-attr]
    assert set(table.groups) == set(table.rows)  # type: ignore[arg-type]
    assert table.blocked() == {} and not table.absent
    assert families.SOUND.no_trace and set(table.media) == set(table.features)  # type: ignore[arg-type]
    assert all("사진" not in m for m in table.media.values())  # type: ignore[union-attr]
    for i, name in enumerate(table.features):
        values = {row[i] for row in table.rows.values()}
        assert not [
            (a, b)
            for a in values
            for b in values
            if a != b and a.replace(" ", "") in b.replace(" ", "")
        ], name
    assert all(2 <= len(c.replace(" ", "")) <= 10 for c in table.rows)


@pytest.mark.parametrize(
    "value,clue",
    [
        ("옮겨 다니는 소리", "녹음에 옮겨 다니는 소리가 담겼어."),
        ("한곳에서 나는 소리", "이웃이 한곳에서 나는 소리를 들었대."),
        ("바람 부는 밤", "일지에 바람 부는 밤마다 소리가 났다고 적혔어."),
        ("높은 나무 위", "소리가 높은 나무 위에서 났대."),
    ],
)
def test_sound_values_fit_in_clue(value: str, clue: str) -> None:
    assert checks.value_in_text(value, clue)


# ---------------------------------------------------------------- 코드 검사
def test_sound_theme_passes() -> None:
    assert checks.check_theme(sound_theme(), 3) == []


def test_same_kind_and_answer_look_and_owner_word() -> None:
    mixed = {**sound_theme(), "candidates": ["부엉이", "고양이", "생쥐", "현수막"]}
    assert any(r.startswith("SAME_KIND") for r in checks.fact_table_problems(mixed))
    bad = checks.check_theme({**sound_theme(), "answerLook": ""}, 3)
    assert bad == ["REQUIRED answerLook"] and list(checks.fix_targets(bad)) == ["answerLook"]
    theme = sound_theme()
    theme["days"][4]["clue"] = "일지에 쓰레기통 둘레라고 적혀 있었어."
    bad = checks.check_theme(theme, 3)
    assert bad == ["CLUE_OWNER FRI clue 단서에 '소리' 낱말이 없음(그 소리의 증거임을 밝힘)"]
    assert list(checks.fix_targets(bad)) == ["FRI.clue"]
    assert checks.check_theme({**sound_theme(), "world": "귀신이 나온다는 마을"}, 3)[0].startswith(
        "UNSAFE"
    )


def test_strict_facts_hide_values_that_split_candidates() -> None:
    theme = sound_theme()
    secret = checks.secret_values(theme)
    assert "우는 소리" in secret and "옮겨 다니는 소리" in secret and "매일 밤" not in secret
    assert checks.answer_facts(theme) == ["쓰레기통 둘레", "뒤적이는 소리"]  # 정답만의 값(그대로)
    leak = {**theme, "intro": "밤마다 우는 소리가 들렸어요. 소리 박사 뭉치가 출동해요."}
    bad = checks.check_theme(leak, 3)
    assert bad == ["ANSWER_FACT intro에 후보를 가르는 소리 값 ['우는 소리'](엔딩 전 글)"]
    assert list(checks.fix_targets(bad)) == ["intro"]
    ok = {**theme, "intro": "밤마다 매일 밤 이상한 소리가 들렸어요. 소리 박사 뭉치가 출동해요."}
    assert checks.check_theme(ok, 3) == []
    # 다른 사실표 종류는 정답만의 값 그대로(②③④ 동작 유지)
    gift = {**valid_theme(), "storyType": "GIFT"}
    assert checks.secret_values(gift) == checks.answer_facts(gift)
    # 미션·대화 쓰지 말 낱말에도 미리 줌
    assert "우는 소리" in prompts.avoid_words(theme, "MON")


def test_outro_answer_for_sound() -> None:
    theme = {**sound_theme(), "outroStory": "쓰레기통 옆에서 고양이를 보았어요."}
    assert checks.outro_other_candidates(theme) == ["고양이"]
    assert not checks.outro_other_candidates({**theme, "outroStory": "너구리를 함께 봤어요."})


def test_plan_has_no_trace_and_no_photo_for_sound() -> None:
    plan = {
        "MON": {"kind": "TRACE", "medium": None},
        "TUE": {"kind": "RECORD", "medium": "사진"},
        "WED": {"kind": "RECORD", "medium": "녹음"},
    }
    out = checks.plan_for_type(plan, families.SOUND)
    assert out["MON"] == {"kind": "SIGHTING", "medium": None}
    assert out["TUE"]["medium"] in {"영상", "일지", "메모"} and out["WED"]["medium"] == "녹음"
    assert plan["TUE"]["medium"] == "사진"  # 받은 배정은 그대로 두고 새로 만듦
    request = ThemeDraftRequest.model_validate(request_body(topic=SEED))
    slots = prompts.evidence_plan_for(request).values()
    assert "TRACE" not in {s["kind"] for s in slots} and "사진" not in {s["medium"] for s in slots}


def test_fit_media_matches_feature() -> None:
    theme = sound_theme()
    theme["evidencePlan"] = {
        d["day"]: {"kind": d["evidence"]["kind"], "medium": None} for d in theme["days"]
    }
    theme["evidencePlan"]["TUE"]["medium"] = "녹음"
    theme["evidencePlan"]["FRI"]["medium"] = "녹음"  # 소리 난 곳은 녹음으로 알 수 없음
    assert checks.fit_media(theme) == ["FRI"]
    assert theme["evidencePlan"]["FRI"]["medium"] in {"영상", "일지", "메모"}
    # ② 선물: 상자 무게는 사진·영상으로 알 수 없음
    gift = {**valid_theme(), "storyType": "GIFT"}
    gift["features"] = [feature("상자 무게", {c: "가벼운 상자" for c in gift["candidates"]})]
    gift["days"] = copy.deepcopy(gift["days"])
    gift["days"][4]["condition"] = {
        "kind": "HINT",
        "feature": "상자 무게",
        "allowed": ["가벼운 상자"],
    }
    gift["evidencePlan"] = {"FRI": {"kind": "RECORD", "medium": "사진"}}
    assert checks.fit_media(gift) == ["FRI"] and gift["evidencePlan"]["FRI"]["medium"] == "메모"


# ---------------------------------------------------------------- 프롬프트·그림
def test_sound_prompts_and_pictures() -> None:
    theme = sound_theme()
    text = prompts.story_text(theme, "MON", 3)
    assert "밝힐 것: 할머니 댁 마당에서 밤마다 들린 소리. 그 소리는" in text
    plain = Draft.model_validate(mission_draft("ANALYZE").model_dump())
    assert "밝힐 것(그 소리는" in prompts.dialogue_user(theme, "MON", plain, 3, [])
    intro = prompts.cut_image_prompt(theme, "INTRO", 2, theme["introCuts"][1], [])
    assert "Do not draw any of these animals or objects: 부엉이, 고양이, 생쥐, 너구리." in intro
    assert "clock" not in intro and "밤마다 들린 소리" not in intro
    outro = prompts.cut_image_prompt(theme, "OUTRO", 3, theme["outroCuts"][2], [])
    assert "The answer, 너구리, looks like this (Korean): 눈가가 까맣고" in outro
    video = prompts.video_prompt(theme, "OUTRO", 3, theme["outroCuts"][2], [])
    assert "Nobody touches, lifts or holds the animal" in video
    video_intro = prompts.video_prompt(theme, "INTRO", 1, theme["introCuts"][0], [])
    assert "Do not show any of these animals or objects" in video_intro
    assert prompts.mission_target(theme) is None and prompts.mission_shows_target(theme)
    keys = prompts._story_keys(theme)
    assert keys["answerLook"].startswith("눈가가")
    assert "SOUND" in prompts.REVIEW_SYSTEM and "귀신" in prompts.SAFETY_STORY
    assert any("'소리' 낱말" in r for r in prompts.fix_rules(theme, "MON.clue"))
    assert any("정답 너구리의 겉모습" in r for r in prompts.fix_rules(theme, "answerLook"))


def test_when_keeps_its_rules_after_flag_split() -> None:
    # ④에서 시간 탐정 표시로 쓰던 칸을 나눈 뒤에도 시간 탐정은 그대로, 소리 탐정에는 안 붙음
    assert families.WHEN.hide_times and families.WHEN.outro_check and families.TIMES.image_hide
    assert not families.SOUND.hide_times and families.SOUND.clue_time
    assert not checks.time_word_problems({**sound_theme(), "intro": "밤 9시쯤 소리가 났어요."})
    assert families.SOUNDS.drawable and not families.TIMES.drawable


def test_code_picks_candidates_and_answer() -> None:
    # 작은 실측: 동물 4건 모두 같은 4마리, 물건 4건 중 정답 바람개비 3건 → 범주·후보 4개·정답은
    # 코드가 정함(같은 요청은 같은 값, 주·학년마다 섞임)
    plans = [
        prompts.candidate_plan_for(
            ThemeDraftRequest.model_validate(request_body(topic=SEED, grade=g))
        )
        for g in (3, 4, 5, 6)
    ]
    for plan in plans:
        assert plan is not None and plan["group"] in {"동물", "물건"}
        names = plan["candidates"]
        assert len(set(names)) == 4 and plan["answer"] in names
        assert {families.SOUNDS.group(c) for c in names} == {plan["group"]}
    request = ThemeDraftRequest.model_validate(request_body(topic=SEED))
    assert prompts.candidate_plan_for(request) == prompts.candidate_plan_for(request)
    plan = prompts.candidate_plan_for(request)
    assert f"answer는 {plan['answer']}" in prompts.plan_user(request, [])  # type: ignore[index]
    assert prompts.candidate_plan_for(ThemeDraftRequest.model_validate(request_body())) is None
    fixed = {"group": "동물", "candidates": list(ANIMALS), "answer": "너구리"}
    ok = {**sound_theme(), "candidatePlan": fixed}
    assert not [r for r in checks.fact_table_problems(ok) if r.startswith("SAME_KIND")]
    other = {**sound_theme(), "candidatePlan": {**fixed, "answer": "생쥐"}}
    assert any(r.startswith("SAME_KIND 후보·정답이") for r in checks.fact_table_problems(other))


def test_flat_features_are_not_clues() -> None:
    # 판정 실측: 동물 후보는 모두 '매일 밤'이라 그 단서가 시작 이야기의 '밤마다'와 겹침(ANSWER_HINT)
    assert checks.flat_features(families.SOUNDS, list(ANIMALS)) == ["소리 나는 밤"]
    assert (
        checks.flat_features(families.SOUNDS, ["바람개비", "빈 양동이", "현수막", "빈 깡통"]) == []
    )
    flat_theme = {
        **sound_theme(),
        "features": [
            *sound_theme()["features"],
            feature("소리 나는 밤", {c: "매일 밤" for c in ANIMALS}),
        ],
    }
    bad = [r for r in checks.fact_table_problems(flat_theme) if "모두 같아" in r]
    assert bad and "'소리 나는 밤'" in bad[0]
    gift = {**valid_theme(), "storyType": "GIFT"}  # 다른 종류는 그대로
    assert not [r for r in checks.fact_table_problems(gift) if "모두 같아" in r]
    request = ThemeDraftRequest.model_validate(request_body(topic=SEED))
    plan = prompts.candidate_plan_for(request)
    flat = checks.flat_features(families.SOUNDS, plan["candidates"])  # type: ignore[index]
    user = prompts.plan_user(request, [])
    assert ("features에 넣지 않는다" in user) == bool(flat)
    theme = sound_theme()
    assert any("소리가 난 자리로" in r for r in prompts.fix_rules(theme, "FRI.clue"))
    assert not any("소리가 난 자리로" in r for r in prompts.fix_rules(theme, "MON.clue"))
