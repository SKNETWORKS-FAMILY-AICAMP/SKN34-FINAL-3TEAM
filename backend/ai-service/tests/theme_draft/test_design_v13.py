"""#782 설계 v13(사용자 결정 2026-11-23 "1·2·3 추천대로").

1. 수사 날 지문은 그때 직접 본 사람의 증언 하나이고 그날 단서 내용이 들어감(TESTIMONY_MISSING,
   지문 CLUE_EARLY는 수사 날만 뺌). 예시 답은 증언 속 본 사실을 믿을 만하다고 결론
2. 판정(측정 판정과 같은 말 — v13 가). #971부터 글 검토 NEXT_FIT이 FAIL인 이어 가기 날은
   지문·다음 행동·할 일 칸을 고쳐 쓰고 그 요일 미션·대화부터 다시(fix_follow, 요일마다 한 번).
   그래프 안 따로 판정은 #971 작은 확인에서 뺌. 고친 요일 두 번째 FAIL·부분 다시 생성·이어 가기
   날 없는 판정은 경고(v13 HELPER_FIT 자리)
3. (#971에서 뺌) 같은 주 같은 약속 줄 PROMISE_SAME — 약속 줄이 없어짐
"""

from typing import Any

from app.theme_draft import checks, prompts
from app.theme_draft.nodes.review import route_fails, settle_next_fit
from tests.theme_draft import fixtures
from tests.theme_draft.fixtures import (
    HELPER,
    MATERIAL,
    day_with,
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


def test_old_saved_and_follow_day_material_still_hide_the_clue() -> None:
    """미션 방식 칸이 없는 예전 저장본·이어 가기 날 지문은 그대로 단서 결론을 막음."""
    old = day_with(valid_theme(), "MON", missionMaterial="공원 관리인의 일지: 길의 물기는 젖음.")
    assert "CLUE_EARLY" in codes(checks.check_theme(old, GRADE))
    ask = way_theme("MON", checks.FOLLOW, missionMaterial="공원 관리인의 일지: 길의 물기는 젖음.")
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


# ---------------------------------------------------------------- 2. NEXT_FIT(#971)
def next_fail(days: list[str]) -> list[dict[str, Any]]:
    review = story_review({"NEXT_FIT": "FAIL"}, {"NEXT_FIT": days})
    return [x.model_dump() for x in review.items if x.verdict == "FAIL"]


def ask_state(**extra: Any) -> dict[str, Any]:
    theme = way_theme("MON", checks.FOLLOW)
    checks.theme_day(theme, "TUE")["missionWay"] = checks.INVESTIGATE
    return {"theme": theme, **extra}


def test_next_fit_rewrites_follow_fields_and_redoes_that_day() -> None:
    state = ask_state()
    fails = next_fail(["MON"])
    out = route_fails(state, {}, fails, ["NEXT_FIT ['MON'] 사유"])  # type: ignore[arg-type]
    assert out["review_route"] == "FOLLOW" and out["days_todo"] == ["MON"]
    assert out["follow_fixed_days"] == ["MON"]
    # 아이 글이 가는 곳(helperUse)은 쓴 글을 읽을 사람 날만 쓰는 칸이라 이 월요일은 뺌
    assert set(out["fix_targets"]) == {
        f"MON.{k}"
        for k in (
            "helper",
            "missionHook",
            "missionMaterial",
            "nextTarget",
            "sceneNote",
        )
    }
    assert out["mission_seed"]["MON"][0].startswith("NEXT_FIT")
    rules = " ".join(prompts.fix_rules(state["theme"], "MON.sceneNote"))
    assert "HELPER_SAME·NEXT_FIT" in rules  # 장면 메모도 새 사람·새 지문 글로


def test_next_fit_without_follow_day_partial_or_second_time_is_a_warning() -> None:
    fails = next_fail(["TUE"])  # 수사 날만 짚음
    keep, warns = settle_next_fit(ask_state(), fails, [])  # type: ignore[arg-type]
    assert keep == [] and warns[0]["id"] == "NEXT_FIT"
    for extra in ({"partial": True}, {"follow_fixed_days": ["MON"]}):
        keep, warns = settle_next_fit(ask_state(**extra), next_fail(["MON"]), [])  # type: ignore[arg-type]
        assert keep == [] and len(warns) == 1, extra
    keep, _ = settle_next_fit(ask_state(), next_fail(["MON"]), [])  # type: ignore[arg-type]
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


def test_next_fit_in_review_prompt_matches_measure_judge() -> None:
    assert "NEXT_FIT" in checks.REVIEW_IDS and "HELPER_FIT" not in checks.REVIEW_IDS
    assert "여섯 항목" in prompts.REVIEW_SYSTEM and "다섯 항목" not in prompts.REVIEW_SYSTEM
    # 글 검토·판정이 같은 기준 글(FOLLOW_RULE — 사건 이야기·풀 만함·풀어야 고름·단서가 거기서)을 봄
    assert prompts.FOLLOW_RULE in prompts.REVIEW_SYSTEM
    assert prompts.FOLLOW_RULE in prompts.FOLLOW_JUDGE_SYSTEM
    for words in ("그 주 사건 이야기", "풀 만하다", "지문 속 사건의 한 부분", "나올 만하다"):
        assert words in prompts.FOLLOW_RULE, words
    # 작은 확인 1차·20테마 측정에서 놓친 억지 예
    for words in ("달빛이 마당에서 춤추는 이야기", "600kg보다 크면", "방파제 안쪽"):
        assert words in prompts.FOLLOW_RULE, words
    assert "promiseDays" not in prompts.REVIEW_SYSTEM


def first_next_fail(n: int, d: str | None) -> Any:
    """첫 글 검토만 월요일 NEXT_FIT FAIL, 그 뒤는 통과."""
    return story_review({"NEXT_FIT": "FAIL"}, {"NEXT_FIT": ["MON"]}) if n == 1 else story_review()


def test_graph_next_fit_fixes_fields_then_redoes_only_that_day() -> None:
    """글 검토가 월요일 NEXT_FIT을 짚으면 → 월요일 지문·다음 행동 칸 고쳐 쓰기 → 월요일 미션·대화만
    다시 → 글 검토. 줄거리 다시 생성 없음, 그래프 안에서 따로 부르던 판정은 없음(#971 작은 확인)."""
    hook = "지호 일지를 같이 읽고 중요한 걸 찾아볼래?"
    gen = gen_llm(fix=lambda n, d: fixes(("MON.missionHook", hook)))
    review = review_llm(story=first_next_fail)
    response = run(gen, review)
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 1 and gen.count("GeneratedFixes") == 1
    assert "NEXT_FIT" in gen.users("GeneratedFixes")[0]
    assert gen.count("GeneratedDraft", "MON") == 2 and gen.count("GeneratedDialogue", "MON") == 2
    assert all(gen.count("GeneratedDialogue", d) == 1 for d in ("TUE", "WED", "THU", "FRI"))
    user = review.users("GeneratedStoryReview")[0]
    assert '"nextTarget"' in user and '"nextOthers"' not in user
    assert f"{fixtures.NEXT['MON']}: " in user  # 학생이 보는 단서(다음 행동 이름표)
    assert review.count("GeneratedFollowJudge") == 0
    assert review.count("GeneratedStoryReview") == 2


def test_follow_judge_prompt_is_for_the_measure_outside_the_graph() -> None:
    """판정 지시문·입력은 측정 판정이 그래프 밖에서 따로 씀(글 검토와 같은 기준 글)."""
    theme = fixtures.valid_theme()
    for d in theme["days"]:
        d["missionWay"] = checks.FOLLOW if d["day"] != "TUE" else checks.INVESTIGATE
        d["nextKind"] = "PLACE" if d["day"] in ("MON", "THU") else "PERSON"
    user = prompts.follow_judge_user(theme, {}, {}, ["MON"])
    assert '"day": "MON"' in user and f"{fixtures.NEXT['MON']}: " in user
    assert prompts.FOLLOW_RULE in prompts.FOLLOW_JUDGE_SYSTEM


def test_review_next_fit_is_fixed_once_then_warning() -> None:
    """같은 요일 NEXT_FIT FAIL은 한 번 고치고, 고친 뒤에도 FAIL이면 경고."""
    review = review_llm(
        story=lambda n, d: story_review({"NEXT_FIT": "FAIL"}, {"NEXT_FIT": ["MON"]})
    )
    gen = gen_llm(fix=lambda n, d: fixes(("MON.missionHook", "지호 일지를 같이 읽어 볼래?")))
    response = run(gen, review)
    assert response.failure is None and gen.count("GeneratedFixes") == 1
    assert review.count("GeneratedStoryReview") == 2
    assert gen.count("GeneratedDraft", "MON") == 2
    assert any(w.stage == "REVIEW" and w.item == "NEXT_FIT MON" for w in response.warnings)


def test_graph_renamed_helper_fixes_next_day_step_and_redoes_that_day() -> None:
    """NEXT_FIT으로 월요일 그날 장소 사람 호칭이 바뀌면 화요일 오늘 온 까닭의 옛 호칭도 고쳐 쓰고
    (fix_old_names), 대화 첫 줄이 그 까닭이라 화요일 미션·대화도 다시."""
    new = "공원 안내원"

    def dlg(n: int, d: str | None) -> Any:
        out = fixtures.dialogue(d)
        if d == "MON" and n >= 2:  # 새 돕는 사람이 말함
            for line in out.lines:
                if line.speaker == HELPER["MON"]:
                    line.speaker = new
        return out

    step = f"{new} 말을 듣고 빵집 앞까지 왔어."
    gen = gen_llm(fix=lambda n, d: fixes(("MON.helper", new), ("TUE.dayStep", step)), dlg=dlg)
    response = run(gen, review_llm(story=first_next_fail))
    assert response.failure is None
    assert gen.count("GeneratedFixes") == 2  # 월 그날 장소 사람 칸, 화 오늘 온 까닭
    assert "바뀌기 전 돕는 사람('공원 관리인')" in gen.users("GeneratedFixes")[1]
    assert gen.count("GeneratedDraft", "TUE") == 2 and gen.count("GeneratedDialogue", "TUE") == 2
    tue = next(x for x in response.dialogues if x.day == "TUE")
    assert tue.lines[0].text == step
    assert all(gen.count("GeneratedDialogue", d) == 1 for d in ("WED", "THU", "FRI"))


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


def test_graph_follow_fix_llm_error_goes_on_to_review() -> None:
    """16차 hand6b: 칸 고쳐 쓰기 응답이 형식 오류면 테마 전체가 오류로 끝났음 → 고치기만 건너뛰고
    글 검토로(그 요일은 고친 것으로 쳐 다시 짚혀도 경고)."""
    from app.llm.base import LlmError

    gen = gen_llm(fix=lambda n, d: LlmError("LLM_INVALID_OUTPUT", False))
    review = review_llm(
        story=lambda n, d: story_review({"NEXT_FIT": "FAIL"}, {"NEXT_FIT": ["MON"]})
    )
    response = run(gen, review)
    assert response.failure is None and review.count("GeneratedStoryReview") == 2
    assert gen.count("GeneratedDraft", "MON") == 1  # 고치지 못했으니 미션도 그대로


def test_next_fit_is_fixed_once_per_day() -> None:
    """#971 작은 확인 3차: 월요일을 고친 뒤 처음 짚힌 금요일은 고치고, 월요일만 다시 짚히면 경고."""
    state = ask_state(follow_fixed_days=["MON"])
    checks.theme_day(state["theme"], "FRI")["missionWay"] = checks.FOLLOW
    keep, warns = settle_next_fit(state, next_fail(["MON", "FRI"]), [])  # type: ignore[arg-type]
    assert [x["days"] for x in keep] == [["FRI"]] and len(warns) == 1
    out = route_fails(state, {}, keep, ["NEXT_FIT ['FRI'] 사유"])  # type: ignore[arg-type]
    assert out["review_route"] == "FOLLOW" and out["follow_fixed_days"] == ["MON", "FRI"]
