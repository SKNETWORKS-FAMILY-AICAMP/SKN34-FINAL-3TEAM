"""#782 설계 v13(사용자 결정 2026-11-23 "1·2·3 추천대로").

1. 수사 날 지문은 그때 직접 본 사람의 증언 하나이고 그날 단서 내용이 들어감(TESTIMONY_MISSING,
   지문 CLUE_EARLY는 수사 날만 뺌). 예시 답은 증언 속 본 사실을 믿을 만하다고 결론
2. 돕는 사람 판정(측정 판정 억지 연결과 같은 말, 테마마다 한 번 — v13 가): 억지 부탁 날은 돕는
   사람·일 칸을 고쳐 쓰고 그 요일 미션·대화부터 다시(fix_helpers). 글 검토 HELPER_FIT은 판정 뒤
   경고로만, 부분 다시 생성·부탁 날 없는 판정도 경고
3. 같은 주 같은 약속 줄은 검토 호출 전에 코드가 세어 뒤 요일 대화만 한 번 다시(PROMISE_SAME)
"""

from typing import Any

import pytest

from app.theme_draft import checks, prompts
from app.theme_draft.nodes.review import route_fails, settle_helper_fit
from tests.theme_draft import fixtures
from tests.theme_draft.fixtures import (
    HELPER,
    MATERIAL,
    PROMISE,
    day_with,
    helper_judge,
    story_review,
    valid_theme,
)
from tests.theme_draft.test_graph import fixes, gen_llm, review_llm, run
from tests.theme_draft.test_mission_ways import TESTIMONY, way_theme

GRADE = 3


def codes(bad: list[str]) -> list[str]:
    return [r.split(" ")[0] for r in bad]


# ---------------------------------------------------------------- 1. 수사 날 증언
def test_investigate_material_must_carry_the_clue() -> None:
    """13차 hand3: 지문은 '직접 봤다'뿐인데 단서는 '대문은 갈색은 아니었어' → 글 검토가 줄거리를
    다시 만들게 함. 증언에 단서 내용이 없으면 그 지문만 고쳐 씀."""
    bare = way_theme("MON", checks.INVESTIGATE, missionMaterial=MATERIAL["MON"])
    bad = checks.check_theme(bare, GRADE)
    assert codes(bad) == ["TESTIMONY_MISSING"]
    assert list(checks.fix_targets(bad)) == ["MON.missionMaterial"]
    # 단서와 같은 내용(활용형 '젖어')이면 통과, 수사 날 지문은 단서 값이 있어도 CLUE_EARLY 아님
    ok = way_theme("MON", checks.INVESTIGATE, missionMaterial=TESTIMONY)
    assert checks.check_theme(ok, GRADE) == []


def test_old_saved_and_ask_day_material_still_hide_the_clue() -> None:
    """미션 방식 칸이 없는 예전 저장본·부탁 날 지문은 그대로 단서 결론을 막음."""
    old = day_with(valid_theme(), "MON", missionMaterial="공원 관리인의 일지: 길의 물기는 젖음.")
    assert "CLUE_EARLY" in codes(checks.check_theme(old, GRADE))
    ask = way_theme("MON", checks.ASK, missionMaterial="공원 관리인의 일지: 길의 물기는 젖음.")
    assert "CLUE_EARLY" in codes(checks.check_theme(ask, GRADE))
    assert checks.testimony_ok(old, "MON.missionMaterial") == []
    testimony = way_theme("MON", checks.INVESTIGATE, missionMaterial=TESTIMONY)
    assert checks.testimony_ok(testimony, "MON.missionMaterial") == ["젖음"]


def test_testimony_prompts_say_the_same_thing() -> None:
    """줄거리·칸 고쳐 쓰기·미션·단서·글 검토·미션 검토가 같은 말(증언에 단서 내용, 예시 답은 본
    사실을 믿을 만하다고)."""
    theme = way_theme("MON", checks.INVESTIGATE, missionMaterial=TESTIMONY)
    assert "증언 하나다" in prompts.PLAN_SYSTEM and "TESTIMONY_MISSING" in prompts.PLAN_SYSTEM
    rules = " ".join(prompts.fix_rules(theme, "MON.missionMaterial"))
    assert "증언에 그날 단서 내용" in rules and "['젖음']" in rules
    story = prompts.story_text(theme, "MON", GRADE)
    assert "오늘 지문은 그때 직접 보거나 듣거나 그때 적은 사람의 증언이다" in story
    assert "직접 본 사실을 믿기 어렵다거나 알 수 없다고 결론 내지 않는다" in story
    assert "지문 증언을 따져 확실해진 그 내용" in prompts.way_clue_rule(
        theme, checks.theme_day(theme, "MON")
    )
    assert "단서 내용이 지문(missionMaterial) 증언에 없으면 결함" in prompts.REVIEW_SYSTEM
    assert "믿기 어렵다거나 알 수 없다고 결론 내면" in prompts.MISSION_REVIEW_SYSTEM


# ---------------------------------------------------------------- 2. HELPER_FIT
def helper_fail(days: list[str]) -> list[dict[str, Any]]:
    review = story_review({"HELPER_FIT": "FAIL"}, {"HELPER_FIT": days})
    return [x.model_dump() for x in review.items if x.verdict == "FAIL"]


def ask_state(**extra: Any) -> dict[str, Any]:
    theme = way_theme("MON", checks.ASK)
    checks.theme_day(theme, "TUE")["missionWay"] = checks.INVESTIGATE
    return {"theme": theme, **extra}


def test_helper_fit_rewrites_helper_fields_and_redoes_that_day() -> None:
    state = ask_state()
    fails = helper_fail(["MON"])
    out = route_fails(state, {}, fails, ["HELPER_FIT ['MON'] 사유"])  # type: ignore[arg-type]
    assert out["review_route"] == "HELPER" and out["days_todo"] == ["MON"]
    assert out["helper_fixed"] is True
    # 아이 답의 쓰임(helperUse)은 국어 부탁 날만 쓰는 칸이라 이 월요일(국어 일 틀 없음)은 뺌
    assert set(out["fix_targets"]) == {
        f"MON.{k}" for k in ("helper", "missionHook", "missionMaterial", "sceneNote")
    }
    assert out["mission_seed"]["MON"][0].startswith("HELPER_FIT")
    rules = " ".join(prompts.fix_rules(state["theme"], "MON.sceneNote"))
    assert "HELPER_SAME·HELPER_FIT" in rules  # 장면 메모도 새 사람·새 일로


def test_helper_fit_without_ask_day_partial_or_second_time_is_a_warning() -> None:
    fails = helper_fail(["TUE"])  # 수사 날만 짚음
    keep, warns = settle_helper_fit(ask_state(), fails, [])  # type: ignore[arg-type]
    assert keep == [] and warns[0]["id"] == "HELPER_FIT"
    for extra in ({"partial": True}, {"helper_fixed": True}):
        keep, warns = settle_helper_fit(ask_state(**extra), helper_fail(["MON"]), [])  # type: ignore[arg-type]
        assert keep == [] and len(warns) == 1, extra
    keep, _ = settle_helper_fit(ask_state(), helper_fail(["MON"]), [])  # type: ignore[arg-type]
    assert len(keep) == 1


def test_avoid_words_include_negative_clue_values() -> None:
    """검사(CLUE_EARLY)는 부정형 단서면 빠지는 값을 봄 — 대화·살펴보기 피할 낱말에도 넣음."""
    theme = way_theme(
        "MON",
        checks.INVESTIGATE,
        clue="내가 본 보리 발자국 자리는 시멘트는 아니었어.",
        condition={
            "kind": "RULE",
            "feature": "땅",
            "allowed": ["모래", "흙"],
            "excluded": ["시멘트"],
        },
    )
    assert checks.clue_says(checks.theme_day(theme, "MON")) == ["시멘트"]
    assert "시멘트" in prompts.avoid_words(theme, "MON")


def test_helper_fit_in_review_prompt_matches_measure_judge() -> None:
    assert "HELPER_FIT" in checks.REVIEW_IDS
    assert "여섯 항목" in prompts.REVIEW_SYSTEM and "다섯 항목" not in prompts.REVIEW_SYSTEM
    assert "그 장소(place)에서 할 법한 일을 부탁하고" in prompts.REVIEW_SYSTEM
    # 검토 입력에 helperUse가 들어가는지는 아래 그래프 시험이 봄


def test_graph_helper_judge_fixes_fields_then_redoes_only_that_day() -> None:
    """돕는 사람 판정이 월요일을 억지로 보면 → 월요일 돕는 사람·일 칸 고쳐 쓰기 → 월요일 미션·대화만
    다시 → 글 검토. 판정은 테마마다 한 번, 줄거리 다시 생성 없음."""
    forced = lambda n, d: helper_judge({"MON": "공원 관리인의 일이 장소와 동떨어짐"})  # noqa: E731
    hook = "공원 안내문에 보리 산책 이야기가 있어. 같이 고쳐 볼래?"
    gen = gen_llm(fix=lambda n, d: fixes(("MON.missionHook", hook)))
    review = review_llm(helper=forced)
    response = run(gen, review)
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 1 and gen.count("GeneratedFixes") == 1
    assert "HELPER_FIT" in gen.users("GeneratedFixes")[0]
    assert gen.count("GeneratedDraft", "MON") == 2 and gen.count("GeneratedDialogue", "MON") == 2
    assert all(gen.count("GeneratedDialogue", d) == 1 for d in ("TUE", "WED", "THU", "FRI"))
    assert '"helperUse"' in review.users("GeneratedStoryReview")[0]
    assert review.count("GeneratedHelperJudge") == 1  # 테마마다 한 번
    assert review.count("GeneratedStoryReview") == 1
    judge = review.users("GeneratedHelperJudge")[0]
    assert '"day": "MON"' in judge and '"day": "TUE"' not in judge  # 부탁 날만(화요일은 수사)


def test_review_helper_fit_after_judge_is_only_a_warning() -> None:
    """판정이 모두 자연스러우면 글 검토 HELPER_FIT FAIL은 경고(판정은 돕는 사람 판정 호출이 함)."""
    review = review_llm(
        story=lambda n, d: story_review({"HELPER_FIT": "FAIL"}, {"HELPER_FIT": ["MON"]})
    )
    gen = gen_llm()
    response = run(gen, review)
    assert response.failure is None and gen.count("GeneratedFixes") == 0
    assert review.count("GeneratedStoryReview") == 1
    assert any(w.stage == "REVIEW" and w.item == "HELPER_FIT MON" for w in response.warnings)


# ---------------------------------------------------------------- 3. 같은 주 같은 약속
def promise_lines(day: str, text: str) -> list[dict[str, str]]:
    return [{"speaker": HELPER[day], "text": text}, {"speaker": "뭉치", "text": "좋아!"}]


def test_same_week_promises_flags_later_days_only() -> None:
    theme = way_theme("MON", checks.ASK)
    for d in ("WED", "THU"):
        checks.theme_day(theme, d)["missionWay"] = checks.ASK
    line = "그 일을 도와주면, 그때 들은 소리를 알려 줄게."
    dialogues = {
        "MON": promise_lines("MON", line),
        "WED": promise_lines(
            "WED", "그 일을 도와주면 그때 들은 소리를 알려 줄게요!"
        ),  # 부호·끝 요만 다름(14차 snd6)
        "THU": promise_lines("THU", "같이 해 주면 그때 본 것도 알려 줄게."),
    }
    same = checks.same_week_promises(theme, dialogues)
    assert list(same) == ["WED"] and "MON 요일과 같음" in same["WED"][0]
    assert checks.same_week_promises(theme, {**dialogues, "WED": []}) == {}
    # 수사 날 줄은 보지 않음(약속 줄이 아님)
    checks.theme_day(theme, "WED")["missionWay"] = checks.INVESTIGATE
    assert checks.same_week_promises(theme, dialogues) == {}


def test_graph_same_promise_redoes_later_dialogue_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """월·수 약속 줄이 같으면 검토 호출 전에 수요일 대화만 한 번 다시(같은 말이 또 나와도 한
    번만)."""
    monkeypatch.setitem(fixtures.PROMISE, "WED", PROMISE["MON"])
    gen = gen_llm()
    review = review_llm()
    response = run(gen, review)
    assert response.failure is None
    assert gen.count("GeneratedDialogue", "WED") == 2
    assert all(gen.count("GeneratedDialogue", d) == 1 for d in ("MON", "TUE", "THU", "FRI"))
    assert "PROMISE_SAME WED" in gen.users("GeneratedDialogue", "WED")[-1]
    assert review.count("GeneratedStoryReview") == 1


def test_graph_renamed_helper_fixes_next_day_step_and_redoes_that_day() -> None:
    """HELPER_FIT으로 월요일 돕는 사람 호칭이 바뀌면 화요일 오늘 온 까닭의 옛 호칭도 고쳐 쓰고
    (fix_old_names), 대화 첫 줄이 그 까닭이라 화요일 미션·대화도 다시."""
    new = "공원 안내원"
    forced = lambda n, d: helper_judge({"MON": "공원 관리인의 일이 장소와 동떨어짐"})  # noqa: E731

    def dlg(n: int, d: str | None) -> Any:
        out = fixtures.dialogue(d)
        if d == "MON" and n >= 2:  # 새 돕는 사람이 말함
            for line in out.lines:
                if line.speaker == HELPER["MON"]:
                    line.speaker = new
        return out

    step = f"{new} 말을 듣고 빵집 앞까지 왔어."
    gen = gen_llm(fix=lambda n, d: fixes(("MON.helper", new), ("TUE.dayStep", step)), dlg=dlg)
    response = run(gen, review_llm(helper=forced))
    assert response.failure is None
    assert gen.count("GeneratedFixes") == 2  # 월 돕는 사람 칸, 화 오늘 온 까닭
    assert "바뀌기 전 돕는 사람('공원 관리인')" in gen.users("GeneratedFixes")[1]
    assert gen.count("GeneratedDraft", "TUE") == 2 and gen.count("GeneratedDialogue", "TUE") == 2
    tue = next(x for x in response.dialogues if x.day == "TUE")
    assert tue.lines[0].text == step
    assert all(gen.count("GeneratedDialogue", d) == 1 for d in ("WED", "THU", "FRI"))


def test_graph_same_promise_redo_failure_keeps_original(monkeypatch: pytest.MonkeyPatch) -> None:
    """같은 주 약속 다시 만들기가 끝내 실패하면 원래 대화(약속 줄만 같음)를 그대로 둠 — 빈 대화로
    바꾸지 않음."""
    monkeypatch.setitem(fixtures.PROMISE, "WED", PROMISE["MON"])

    def dlg(n: int, d: str | None) -> Any:
        if d == "WED" and n >= 2:  # 다시 만든 대화는 줄 수가 모자라 늘 검사에 걸림
            return fixtures.dialogue(d, lines=fixtures.dialogue(d).lines[:1])
        return fixtures.dialogue(d)

    gen = gen_llm(dlg=dlg)
    response = run(gen, review_llm())
    assert response.failure is None
    assert gen.count("GeneratedDialogue", "WED") >= 2
    wed = next(x for x in response.dialogues if x.day == "WED")
    assert any(line.text == PROMISE["MON"] for line in wed.lines)
    assert not [w for w in response.warnings if w.stage == "DIALOGUE" and w.item == "WED"]


# ---------------------------------------------------------------- 4. 문제 글의 사건 때(15차 치명)
def test_mission_incident_time_must_not_be_last_night() -> None:
    """15차 snd6b 수요일 문제 '어젯밤 민박집 방에서 알 수 없는 소리가 들렸지만' — 사건은 월요일 전
    일. 그냥 '어제'는 어제 다녀간 일로도 써서 보지 않음, 월요일은 시작 이야기가 전날 밤이면 됨."""
    from tests.theme_draft.test_design_v10_c import mission_reasons

    night = "어젯밤 마을 길에서 보리가 사라졌지만, 어디로 갔는지는 아직 몰라."
    bad = mission_reasons(valid_theme(), "WED", question=night)
    assert [r for r in bad if r.startswith("INCIDENT_TIME")]
    ok = "그날 밤 마을 길에서 보리가 사라졌지만, 어디로 갔는지는 아직 몰라."
    assert not [r for r in mission_reasons(valid_theme(), "WED", question=ok) if "INCIDENT" in r]
    yesterday = "어제 들은 이야기를 떠올리며 보리가 지나간 길을 생각해 봐."
    assert not [
        r for r in mission_reasons(valid_theme(), "WED", question=yesterday) if "INCIDENT" in r
    ]
    intro_night = {**valid_theme(), "intro": "어젯밤 지호의 강아지 보리가 사라졌어요."}
    assert not [r for r in mission_reasons(intro_night, "MON", question=night) if "INCIDENT" in r]
    assert "INCIDENT_TIME" in prompts.story_text(valid_theme(), "WED", GRADE)
    assert "'어젯밤·그저께'처럼 그날 기준 지난 때로 쓰면 결함" in prompts.REVIEW_SYSTEM


def test_graph_helper_fix_llm_error_goes_on_to_review() -> None:
    """16차 hand6b: 돕는 사람 칸 고쳐 쓰기 응답이 형식 오류면 테마 전체가 오류로 끝났음 → 고치기만
    건너뛰고 글 검토로(판정은 테마마다 한 번이라 다시 부르지 않음)."""
    from app.llm.base import LlmError

    forced = lambda n, d: helper_judge({"MON": "공원 관리인의 일이 장소와 동떨어짐"})  # noqa: E731
    gen = gen_llm(fix=lambda n, d: LlmError("LLM_INVALID_OUTPUT", False))
    review = review_llm(helper=forced)
    response = run(gen, review)
    assert response.failure is None
    assert review.count("GeneratedHelperJudge") == 1 and review.count("GeneratedStoryReview") == 1
    assert gen.count("GeneratedDraft", "MON") == 1  # 고치지 못했으니 미션도 그대로


def test_graph_helper_judge_llm_error_goes_on_to_review() -> None:
    """돕는 사람 판정 호출이 실패해도(LlmUnavailable) 테마 전체를 오류로 끝내지 않고 글 검토."""
    from app.llm.base import LlmError

    review = review_llm(helper=lambda n, d: LlmError("LLM_INVALID_OUTPUT", False))
    response = run(gen_llm(), review)
    assert response.failure is None and review.count("GeneratedStoryReview") == 1
