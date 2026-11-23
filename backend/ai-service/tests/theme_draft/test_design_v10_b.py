"""#782 설계 v10 B(돕는 사람·쓰임): 일 → 사람 → 쓰임 → 장소를 모델이 정하고 코드·검토가
지킨다. 오늘 온 까닭 규칙(1.4)은 설계 v11에서 뺌.

- helperUse(국어 부탁 날 아이 답의 쓰임, 내부 칸): 응답에 안 나옴, 비면 REQUIRED(칸 고쳐 쓰기)
- USE_MISSING 쓰임 낱말은 helperUse의 마지막 '에·에다·으로·로' 앞 말에서, 예전 저장본은 dayFrames
- HELPER_SAME은 배정 호칭을 보지 않음(같은 주 같은 사람·등장인물만)
- review_helpers(돕는 사람 검토)는 설계 v11에서 뺌(v9처럼 줄거리 통과 뒤 곧바로 미션)
"""

import copy
import random
from typing import Any

from app.mission_draft.models import Draft
from app.theme_draft import checks, prompts
from tests.theme_draft.fixtures import (
    generated_theme,
    mission_draft,
    valid_theme,
)
from tests.theme_draft.helpers import request_body
from tests.theme_draft.test_checks import mission_inputs

GRADE = 3
KOREAN_MON = "4국05-02"
USE = "공원 소식 모음에 실을게"


def korean_frames() -> dict[str, dict[str, Any]]:
    return checks.day_frames(
        [("MON", [KOREAN_MON], "ANALYZE")], {"MON": checks.ASK}, random.Random(0)
    )


def korean_theme(**mon: Any) -> dict[str, Any]:
    """월요일만 국어 부탁 날(dayFrames 일 틀)인 테마."""
    theme = copy.deepcopy(valid_theme())
    theme["dayFrames"] = korean_frames()
    checks.theme_day(theme, "MON").update(missionWay=checks.ASK, **mon)
    return theme


def korean_body() -> dict[str, Any]:
    """월요일(ANALYZE)에만 국어 성취기준을 더한 요청(미션 방식·증거 배정은 기본 요청과 같고, 특징
    표의 성취기준 코드 4과02-02도 그대로 있음)."""
    body = request_body()
    for m in body["missions"]:
        if m["thinkingType"] == "ANALYZE":
            m["standards"].append({"code": KOREAN_MON, "statement": "작품 감상"})
    return body


# ---------------------------------------------------------------- 내부 칸·REQUIRED
def test_helper_use_is_internal_and_required_on_korean_ask_days() -> None:
    theme = korean_theme(helperUse=USE)
    public = checks.public_theme(checks.fill_rules_out(copy.deepcopy(theme)))
    assert "helperUse" not in public["days"][0] and USE not in str(public)
    assert not [r for r in checks.check_theme(theme, GRADE) if "helperUse" in r]
    # 비면 REQUIRED, 그 칸만 고쳐 씀
    blank = korean_theme(helperUse="")
    bad = [r for r in checks.check_theme(blank, GRADE) if "helperUse" in r]
    assert bad == ["REQUIRED MON.helperUse"]
    assert checks.fix_targets(bad) == {"MON.helperUse": bad}
    assert any("USE_MISSING" in r for r in prompts.fix_rules(blank, "MON.helperUse"))
    # 너무 길면 LENGTH도 그 칸만
    long = korean_theme(helperUse="가" * 45)
    long_bad = [r for r in checks.check_theme(long, GRADE) if "helperUse" in r]
    assert long_bad and checks.fix_targets(long_bad) == {"MON.helperUse": long_bad}
    # 국어 부탁 날이 아니면(수학·수사·예전 저장본) 보지 않음
    assert not [r for r in checks.check_theme(valid_theme(), GRADE) if "helperUse" in r]
    # 예전 저장본·모델 출력: 기본값은 빈 값
    assert generated_theme().days[0].helperUse == ""


# ---------------------------------------------------------------- 쓰임 낱말
def test_use_words_come_from_before_the_last_particle() -> None:
    assert checks.use_words("책 추천 카드에 붙일게") == ["추천", "카드"]
    assert checks.use_words("소식지에 실을게") == ["소식지"]
    assert checks.use_words("안내판·방송 글로 쓸게") == ["안내판", "방송"]
    assert checks.use_words("시집 뒤 감상 칸에다 붙일게") == ["시집", "감상"]
    assert checks.use_words("새 팻말 안내문으로 걸게") == ["팻말", "안내문"]
    # 마지막 조사 기준(앞의 '줄로'에서 자르지 않음), '에게'는 조사 '에'가 아님. 합칠 때: 동사·조사가
    # 붙은 말('줄로'·'정리해'·'손님들에게')은 쓰임 낱말에서 뺌(흔한 말로 통과하지 않게)
    assert checks.use_words("두 줄로 정리해 게시판에 붙일게") == ["게시판"]
    assert checks.use_words("손님들에게 보여 줄 게시판") == ["보여", "게시판"]
    assert checks.use_words("") == []


def test_use_missing_reads_helper_use_and_falls_back_for_old_saves() -> None:
    request = mission_inputs("ANALYZE")
    draft = Draft.model_validate(mission_draft("ANALYZE").model_dump())

    def use_missing(theme: dict[str, Any], question: str) -> list[str]:
        d = draft.model_copy(update={"question": question})
        return [
            r
            for r in checks.check_mission(theme, request, d, GRADE, {GRADE: 600}, 10)
            if r.startswith("USE_MISSING")
        ]

    theme = korean_theme(helperUse="책 추천 카드에 붙일게")
    assert checks.day_use(theme, "MON") == ("책 추천 카드에 붙일게", ["추천", "카드"])
    bad = use_missing(theme, draft.question)
    assert bad and "추천·카드" in bad[0] and "책 추천 카드에 붙일게" in bad[0]
    assert not use_missing(theme, draft.question + " 네 글은 카드에 실려.")
    # 대신용 틀 낱말(소개판)은 helperUse가 있으면 보지 않음
    assert use_missing(theme, draft.question + " 네 글은 소개판에 붙어.")
    # 예전 저장본(helperUse 없음)은 dayFrames 쓰임 낱말
    old = korean_theme()
    old["days"][0].pop("helperUse", None)
    frame = old["dayFrames"]["MON"]
    assert checks.day_use(old, "MON") == (frame["use"], frame["useWords"])
    assert use_missing(old, draft.question)
    assert not use_missing(old, draft.question + f" 네 글은 {frame['useWords'][0]}에 실려.")
    # 미션 글 지시문도 같은 쓰임
    story = prompts.story_text(theme, "MON", GRADE)
    assert "'책 추천 카드에 붙일게'" in story and "추천·카드" in story
    assert frame["use"] in prompts.story_text(old, "MON", GRADE)
    # 국어 부탁 날이 아니면 지시·검사 없음
    assert "USE_MISSING" not in prompts.story_text(valid_theme(), "MON", GRADE)


# ---------------------------------------------------------------- 돕는 사람
def test_helper_same_no_longer_requires_an_assigned_role() -> None:
    theme = korean_theme(helper="마을 낭독회 진행자", helperUse=USE)
    assert theme["dayFrames"]["MON"]["roles"]
    assert "마을 낭독회 진행자" not in theme["dayFrames"]["MON"]["roles"]
    assert not checks.helper_problems(theme)
    assert not hasattr(checks, "helper_fits_frame")
    # 같은 주 같은 사람·등장인물은 그대로 HELPER_SAME(뒤 요일이 걸림)
    same = korean_theme(helperUse=USE)
    checks.theme_day(same, "WED")["helper"] = checks.theme_day(same, "MON")["helper"]
    bad = [r for r in checks.helper_problems(same) if r.startswith("HELPER_SAME WED helper")]
    assert bad and "앞 요일과 같은 돕는 사람" in bad[0]
    character = korean_theme(helper=valid_theme()["characters"][0]["name"], helperUse=USE)
    assert any(
        r.startswith("HELPER_SAME MON helper") and "그날 성취기준의 일을 하는 다른 사람" in r
        for r in checks.helper_problems(character)
    )


def test_plan_prompt_gives_kind_of_work_not_role_names() -> None:
    from app.theme_draft.models import ThemeDraftRequest

    request = ThemeDraftRequest.model_validate(korean_body())
    plan = prompts.plan_user(request, [])
    frames = prompts.day_frames_for(request)
    assert "국어 부탁 날 그날 성취기준의 일" in plan
    assert frames["MON"]["work"] in plan and frames["MON"]["work"].startswith("문학")
    assert not any(role in plan for role in frames["MON"]["roles"])
    assert frames["MON"]["use"] not in plan
    # 대신용 틀·예전 저장본용 칸은 dayFrames에 그대로
    assert {"codes", "roles", "use", "useWords"} <= set(frames["MON"])
    system = prompts.PLAN_SYSTEM
    assert "helperUse" in system and "그날 성취기준의 일" in system
    assert "두 호칭 중 하나를 그대로" not in system


def test_review_helpers_node_is_removed() -> None:
    """#782 설계 v11: 돕는 사람 검토(review_helpers, 테마마다 검토 호출 +1)는 뺌 — 줄거리 통과 뒤
    곧바로 요일 미션(v9). 억지는 미션 검토 STORY_LINK·글 검토·측정 판정이 봄."""
    from app.theme_draft import models
    from app.theme_draft.graph import build_graph
    from app.theme_draft.nodes import plan

    nodes = set(build_graph().get_graph().nodes)
    assert "review_helpers" not in nodes
    assert not hasattr(plan, "review_helpers") and not hasattr(models, "GeneratedHelperReview")
    assert not hasattr(prompts, "HELPER_REVIEW_SYSTEM")
    edges = {(e.source, e.target) for e in build_graph().get_graph().edges}
    assert ("check_theme", "generate_mission") in edges
