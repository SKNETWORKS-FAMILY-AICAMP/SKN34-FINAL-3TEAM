"""#782 설계 v8(사용자 결정 2026-11-22 "해서 수정해 확실하게 틈없이 설계해서"): 규칙끼리 부딪힘.

3·4·5차 120번 실행의 실패 사유를 전부 나눠 보니 줄거리 지시문·코드 검사·검토 지시문이 서로 다른
말을 해서 생긴 실패가 많았다. 같은 규칙은 세 곳이 같은 말을 하게 하고, 미션·대화가 고칠 수 없는
칸 때문에 다시 만들지 않게 한다.
"""

import copy
import json
from typing import Any

from app.theme_draft import checks, families, prompts
from app.theme_draft.models import GeneratedMissionReview, MissionReviewItem
from tests.theme_draft.fixtures import (
    MATERIAL,
    day_with,
    mission_draft,
    mission_review,
    valid_theme,
)
from tests.theme_draft.test_families_in_hand import gift_theme
from tests.theme_draft.test_families_when_how import vehicle_theme
from tests.theme_draft.test_graph import fixes, gen_llm, review_llm, run
from tests.theme_draft.test_theme_structure import _draft, _request

GRADE = 3


def codes(theme: dict[str, Any]) -> list[str]:
    return sorted({r.split(" ")[0] for r in checks.check_theme(theme, GRADE)})


# ---------------------------------------------------------------- A. 부정 단서 꼴
def test_negative_clue_mixed_with_allowed_value_is_caught() -> None:
    two = {"kind": "RULE", "feature": "땅", "allowed": ["모래", "흙"]}
    mixed = day_with(
        valid_theme(), "FRI", condition=two, clue="내 일지에는 흙은 맞고 시멘트는 아니었어."
    )
    bad = [r for r in checks.check_theme(mixed, GRADE) if r.startswith("CLUE_TEXT FRI")]
    assert bad and "허용 값 ['흙']" in bad[0]


def test_review_prompt_says_negative_clue_is_the_design() -> None:
    review = prompts.REVIEW_SYSTEM
    assert "부정형 단서는 설계라 결함이 아님" in review and "excluded" in review
    assert "없었다·못 봤다·안 들렸다" in prompts.PLAN_SYSTEM


# ---------------------------------------------------------------- B. 탈것 사건 단서 날
def test_vehicle_story_day_needs_person_not_wheel() -> None:
    theme = vehicle_theme()
    story = next(d for d in theme["days"] if checks.is_story(d.get("condition") or {}))
    story["evidence"] = {"kind": "TRACE", "when": story["evidence"]["when"]}
    person = checks.clue_person(theme)
    story["clue"] = f"{person}이 온 길에 발자국이 이어져 있었어!"
    assert not [r for r in checks.check_theme(theme, GRADE) if r.startswith("CLUE_OWNER")]
    story["clue"] = f"{person}이 온 길에 바퀴 자국이 이어져 있었어!"
    bad = [r for r in checks.check_theme(theme, GRADE) if r.startswith("STORY_VALUE")]
    assert bad and "바퀴" in bad[0]


# ---------------------------------------------------------------- C. 수사 날 사건 단서
def test_review_allows_investigate_story_clue_in_material() -> None:
    assert "수사 날(missionWay INVESTIGATE) 사건 단서는" in prompts.REVIEW_SYSTEM


# ---------------------------------------------------------------- D. 시키는 말
def test_more_orders_are_caught_in_material_and_dialogue() -> None:
    for text in (
        "이 자료를 그래프로 나타내고 가장 많은 것을 살펴봐 주세요.",
        "그래프를 만들어 줄래?",
        "줄자로 다시 재 보세요.",
    ):
        assert checks.act_orders(text), text
    assert not checks.act_orders("그래프로 나타낸 표가 게시판에 붙어 있어.")
    lines = [
        {"speaker": "행사 준비 담당자", "text": "막대그래프로 정리해 줘."},
        {"speaker": "뭉치", "text": "같이 해 보자!"},
    ]
    theme = checks.finalize_texts(valid_theme())
    draft = _draft("ANALYZE")
    out = {"lines": checks.with_first_line(theme, "MON", lines, GRADE)}
    bad = checks.check_dialogue(theme, "MON", out, draft, GRADE, 20)
    assert any(r.startswith("ACT_NAME 대화") for r in bad)


# ---------------------------------------------------------------- E. 지문 끝 부탁 문장
def test_material_request_sentence_may_be_reworded() -> None:
    material = "산책길 안내판에는 '물을 아껴요'라고 적혀 있어요. 이 글을 경험 모음에 실으려 해요."
    theme = day_with(valid_theme(), "MON", missionMaterial=material)
    question = (
        "경험 모음에 실을 글이 필요해. 산책길 안내판에는 '물을 아껴요'라고 적혀 있어요. "
        "이 글을 읽고 무엇을 알 수 있는지 써 줘."
    )
    draft = _draft("ANALYZE", question=question)
    assert not [r for r in checks.material_problems(theme, _request("ANALYZE"), draft)]
    assert "부탁·쓰임 문장" in prompts.PLAN_SYSTEM


# ---------------------------------------------------------------- F. 지문 탓이면 지문만 고쳐 씀
def test_graph_material_fault_fixes_material_not_mission() -> None:
    """미션 검토가 '[지문]'으로 지문 자체를 짚으면 미션 사유로 다시 만들지 않고 그 요일 지문만
    고쳐 쓴 뒤(칸 고쳐 쓰기 1번) 그 지문으로 미션을 다시 만듦. 가짜 검토는 요일을 모르므로 첫
    미션 검토만 지문 탓으로 FAIL하고, 고쳐 쓰기 가짜는 어느 요일 지문이든 받아 줌."""
    suffix = " 그때 바로 적어 둔 것이다."
    first = {"done": False}

    def review(n: int, d: str | None) -> Any:
        if not first["done"]:
            first["done"] = True
            items = [
                MissionReviewItem(id=i, verdict="PASS", reason=f"{i} 사유")  # type: ignore[arg-type]
                for i in ("EXAMPLE_COMPLETE", "STANDARD_FIT", "STORY_LINK")
            ]
            items.append(
                MissionReviewItem(id="MATERIAL", verdict="FAIL", reason="[지문] 조건이 서로 어긋남")
            )
            return GeneratedMissionReview(verdict="FAIL", items=items)  # type: ignore[arg-type]
        return mission_review()

    every = [(f"{d}.missionMaterial", MATERIAL[d] + suffix) for d in MATERIAL]

    def draft(n: int, d: str | None) -> Any:  # 다시 만들 때는 고친 지문을 씀
        base = mission_draft(checks.DAY_TYPE[d or "MON"])
        if n == 1 or not d:
            return base
        return base.model_copy(
            update={"question": base.question.replace(MATERIAL[d], MATERIAL[d] + suffix)}
        )

    gen = gen_llm(draft=draft, fix=lambda n, d: fixes(*every))
    response = run(gen, review_llm(mission=review))
    assert response.failure is None
    assert gen.count("GeneratedFixes") == 1
    redone = [d for d in MATERIAL if gen.count("GeneratedDraft", d) == 2]
    assert len(redone) == 1 and suffix.strip() in gen.users("GeneratedDraft", redone[0])[-1]
    assert "[지문]" in prompts.MISSION_REVIEW_SYSTEM


# ---------------------------------------------------------------- G. 답 샘 오탐
def test_fraction_digit_in_material_is_not_answer_leak() -> None:
    """5차 new5: 지문 '3/4 … 2/3'의 2를 답 2로 봄."""
    material = "안내띠는 3/4m짜리가 4개, 그중 2/3만 쓸 거야."
    theme = day_with(valid_theme(), "THU", missionMaterial=material)
    request = _request("SOLVE", "SOLUTION_STEPS")
    draft = _draft("SOLVE")
    draft = draft.model_copy(
        update={
            "question": f"{material} 필요한 길이를 구해 줘.",
            "answer_key": draft.answer_key.model_copy(update={"final_answer": "2"}),
        }
    )
    assert not checks.material_number_leak(theme, request, draft)
    leaked = draft.model_copy(update={"question": f"{material} 답은 2야."})
    assert checks.material_number_leak(theme, request, leaked)


# ---------------------------------------------------------------- H. 예시 답
def test_example_limits_reach_review_and_poem_lines_are_not_counted() -> None:
    user = json.loads(
        prompts.mission_review_user(_request("ANALYZE"), _draft("ANALYZE"), GRADE, None)
    )
    assert user["maxSentences"] == checks.EXAMPLE_SENTENCES[GRADE]
    assert "maxSentences가 있으면" in prompts.MISSION_REVIEW_SYSTEM
    poem = "\n".join(f"{i}번째 줄이에요." for i in range(1, 8))
    s = checks.check_mission(
        valid_theme(),
        _request("CREATE", "NARRATIVE"),
        _draft("CREATE", exampleAnswer=poem),
        GRADE,
        {g: 400 for g in (3, 4, 5, 6)},
        20,
    )
    assert not [r for r in s if r.startswith("EXAMPLE_LONG")]


# ---------------------------------------------------------------- I. 대화 약속 줄
def test_long_request_and_promise_line_is_split() -> None:
    line = "알림 글을 나눌 방법을 같이 정리해 줄래요? 도와주면 그때 본 걸 알려 줄게요."
    assert len(line) > checks.LINE_MAX
    lines = [{"speaker": "안내원", "text": line}, {"speaker": "뭉치", "text": "좋아!"}]
    out = checks.split_long_lines(lines, GRADE)
    assert [x["text"] for x in out[:2]] == [
        "알림 글을 나눌 방법을 같이 정리해 줄래요?",
        "도와주면 그때 본 걸 알려 줄게요.",
    ]
    full = [{"speaker": "안내원", "text": line}] + [{"speaker": "뭉치", "text": "응"}] * 3
    assert checks.split_long_lines(full, GRADE) == full  # 줄 수 상한을 넘으면 나누지 않음


def test_promise_matches_sense() -> None:
    theme = copy.deepcopy(valid_theme())
    d = checks.theme_day(theme, "MON")
    d["condition"] = {**d["condition"], "feature": "들린 소리"}
    d["evidence"] = {"kind": "SIGHTING", "when": "그때"}
    # #782 설계 v9: '그때 들은 걸'은 전해 들은 말로 읽혀 '내가 들은 소리를'
    assert prompts.ask_promise(theme, d) == "도와주면 그때 내가 들은 소리를 알려 줄게"
    assert not checks.ask_promise_missing(
        {**d, "missionWay": checks.ASK, "helper": "관리인"},
        [{"speaker": "관리인", "text": "도와주면 그때 내가 들은 소리를 알려 줄게."}],
    )


# ---------------------------------------------------------------- J. 손에 든 것 예시
def test_in_hand_examples_do_not_say_helper_kept_it() -> None:
    for t in (families.ORIGIN, families.GIFT, families.ROUTE):
        assert "맡아 두며" not in t.rules and "맡아 둔 사람" not in t.rules, t.code
    assert checks.KEPT_SELF.search("내가 맡아 두며 보니 상자에 꽃가루가 묻어 있었어!")
    theme = day_with(gift_theme(), "MON", missionWay=checks.ASK, clue="상자 안쪽에서 꽃향이 났어!")
    checks.normalize_clue_source(theme)
    assert "맡아 보니" in checks.theme_day(theme, "MON")["clue"]


# ---------------------------------------------------------------- K. 감각·틀 문장
def test_hyang_in_direction_is_not_smell() -> None:
    assert checks.sense_of("발자국이 창고 쪽을 향해 있었어!") is None
    assert checks.sense_of("상자 안쪽에 꽃향이 배어 있었어!") == ("향", "맡아 보니")


# ---------------------------------------------------------------- L. 지어냄 검사 오탐
def test_day_step_made_does_not_catch_true_sentences() -> None:
    # '어제 사진에서 본 골목'은 어제 단서가 그 사진일 때만 참말(#782 설계 v12: 앞 요일 기록에 없는
    # 것을 대면 DAY_STEP_MADE — 9차 new4 '일지에 나온 포장방 문턱')
    photo = day_with(valid_theme(), "MON", clue="내 사진에 골목 쪽으로 가는 보리가 찍혀 있어!")
    for text in (
        "강아지가 가져갔을지 몰라 빵집 앞에 와 봤어.",
        "어제 사진에서 본 골목으로 와 봤어.",
        "사람이 많다고 해서 장터 쉼터로 와 봤어.",
    ):
        assert "DAY_STEP_MADE" not in codes(day_with(photo, "TUE", dayStep=text)), text
    made = day_with(valid_theme(), "TUE", dayStep="어제 사진에서 본 골목으로 와 봤어.")
    assert "DAY_STEP_MADE" in codes(made)  # 월요일 단서는 발자국 흔적(사진 아님, 골목 없음)


# ---------------------------------------------------------------- M·N. 글자 수·시각
def test_person_clue_types_get_trace_length_and_korean_clock() -> None:
    theme = vehicle_theme()
    d = theme["days"][1]
    assert checks.day_text_max(d, "clue", theme) == checks.TRACE_CLUE_MAX
    lost = {
        **valid_theme(),
        "storyType": "LOST",
        "intro": "오후 세 시, 지호는 보리가 없어진 걸 알았어요.",
    }
    assert "INTRO_CLOCK" in codes(lost)
    assert "INTRO_CLOCK" not in codes({**lost, "intro": "세 시간 동안 지호는 보리를 찾았어요."})
