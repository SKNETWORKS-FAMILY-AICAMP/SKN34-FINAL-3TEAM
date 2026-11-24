"""테마 그래프(글 단계) 시험.

실제 LLM은 부르지 않고 출력 형식·요일로 응답을 정하는 가짜 LLM을 쓴다.
"""

import asyncio
import json
import re
import time
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel

from app.config import get_settings
from app.errors import ApiError
from app.llm.base import LlmClient, LlmError, LlmRequest, LlmUsage, ProviderResponse, T
from app.mission_draft.prompts import GeneratedDraft
from app.prompt_versions.registry import ActiveVersions
from app.theme_draft import checks
from app.theme_draft.checks import DAY_KO, DAY_TYPE, DAYS
from app.theme_draft.models import (
    GeneratedDialogue,
    GeneratedExampleFix,
    GeneratedFixes,
    GeneratedHookFixes,
    GeneratedLine,
    GeneratedMissionReview,
    GeneratedStoryReview,
    GeneratedTheme,
    ThemeDraftRequest,
    ThemeDraftResponse,
)
from app.theme_draft.nodes import DEADLINE_REASON
from app.theme_draft.service import ThemeDraftGraphRunner
from tests.theme_draft.fixtures import (
    DISCOVERY,
    HELPER,
    HOOK,
    MATERIAL,
    NEXT,
    day_with,
    dialogue,
    generated_theme,
    mission_draft,
    mission_review,
    story_review,
    theme_with,
    valid_theme,
)
from tests.theme_draft.helpers import request_body

KO_DAY = {v: k for k, v in DAY_KO.items()}
TODAY = re.compile(r"오늘\((.)요일\)")
Reply = BaseModel | LlmError
# (그 형식 n번째 호출(1부터), 요일) → 응답
Handler = Callable[[int, str | None], Reply]


class ScriptedLlm(LlmClient):
    """출력 형식별 처리기로 응답한다. 호출은 (형식 이름, 요일, user)로 남긴다."""

    def __init__(self, model: str, handlers: dict[type, Handler]) -> None:
        self.usages: list[LlmUsage] = []
        super().__init__(model, 0, self.usages.append, backoff_seconds=0, timeout=15)
        self.handlers = handlers
        self.calls: list[tuple[str, str | None, str]] = []

    async def _request(self, request: LlmRequest[T]) -> ProviderResponse[T]:
        m = TODAY.search(request.user)
        day = KO_DAY[m.group(1)] if m else None
        name = request.output.__name__
        n = 1 + sum(1 for c in self.calls if c[0] == name and c[1] == day)
        self.calls.append((name, day, request.user))
        reply = self.handlers[request.output](n, day)
        if isinstance(reply, LlmError):
            raise reply
        return ProviderResponse(
            request.output.model_validate(reply.model_dump()), self.model, 10, 5
        )

    def count(self, name: str, day: str | None = None) -> int:
        return sum(1 for c in self.calls if c[0] == name and (day is None or c[1] == day))

    def users(self, name: str, day: str | None = None) -> list[str]:
        return [c[2] for c in self.calls if c[0] == name and (day is None or c[1] == day)]


def gen_llm(
    theme: Handler | None = None,
    draft: Handler | None = None,
    dlg: Handler | None = None,
    fix: Handler | None = None,
    example: Handler | None = None,
    hook: Handler | None = None,
) -> ScriptedLlm:
    """fix가 없으면 칸 고쳐 쓰기 호출은 처리기가 없어 시험이 실패한다(예상 밖 호출을 드러냄).
    수사 연결 문장 고쳐 쓰기(fix_hook, #535)는 요일 미션이 통과할 때마다 불려 기본은 고칠 칸
    없음."""
    handlers: dict[type, Handler] = {
        GeneratedTheme: theme or (lambda n, d: generated_theme()),
        GeneratedDraft: draft or (lambda n, d: mission_draft(DAY_TYPE[d])),
        GeneratedDialogue: dlg or (lambda n, d: dialogue(d)),
        GeneratedHookFixes: hook or (lambda n, d: GeneratedHookFixes(fixes=[])),
    }
    if fix:
        handlers[GeneratedFixes] = fix
    if example:
        handlers[GeneratedExampleFix] = example
    return ScriptedLlm("gen-model", handlers)


def review_llm(story: Handler | None = None, mission: Handler | None = None) -> ScriptedLlm:
    return ScriptedLlm(
        "review-model",
        {
            GeneratedStoryReview: story or (lambda n, d: story_review()),
            GeneratedMissionReview: mission or (lambda n, d: mission_review()),
        },
    )


HOOK_LABEL = "오늘 할 일(마지막 줄 재료, 지문·증거를 같이 보자는 말): "
FOUND_LABEL = "오늘 찾은 증거(② 재료, 이 증거 그대로): "


# 기본 요청(request_body)의 미션 방식 배정(prompts.mission_ways_for, 같은 씨앗이면 같음)
WAYS = {
    "MON": checks.FOLLOW,
    "TUE": checks.INVESTIGATE,
    "WED": checks.FOLLOW,
    "THU": checks.FOLLOW,
    "FRI": checks.FOLLOW,
}


def given(gen: "ScriptedLlm", day: str, label: str) -> str:
    """그 요일 마지막 대화 요청에 재료로 준 줄(#782 테마 짜임: 대화 모델이 풀어 씀)."""
    user = gen.users("GeneratedDialogue", day)[-1]
    return next(x for x in user.splitlines() if x.startswith(label))[len(label) :]


def run(
    gen: ScriptedLlm, review: ScriptedLlm, body: dict | None = None, deadline_in: float = 900
) -> ThemeDraftResponse:
    request = ThemeDraftRequest.model_validate(body or request_body())
    runner = ThemeDraftGraphRunner(gen, review, get_settings(), ActiveVersions())
    response = asyncio.run(runner.run(request, time.monotonic() + deadline_in))
    # 글 단계 시험은 그림 설정이 없어 그림·영상·움직임을 건너뜀. 그 경고는 test_media_graph에서 봄
    skipped = [w for w in response.warnings if (w.stage, w.reason) != ("IMAGE", "그림 설정 없음")]
    return response.model_copy(update={"warnings": skipped})


# ANSWER_LEAK(등장인물 이름에 정답): 칸 하나 고쳐 쓰기로 못 고쳐 줄거리를 다시 만듦
BROKEN_THEME = theme_with(characters=[{"name": "텃밭지기", "look": "노란 우비를 입은 아이"}])
LONG_HOOK = day_with(valid_theme(), "WED", missionHook="가" * 45)  # LENGTH WED.missionHook


def fixes(*pairs: tuple[str, str]) -> GeneratedFixes:
    return GeneratedFixes.model_validate({"fixes": [{"path": p, "text": t} for p, t in pairs]})


def hook_fixes(*pairs: tuple[str, str]) -> GeneratedHookFixes:
    return GeneratedHookFixes.model_validate({"fixes": [{"path": p, "text": t} for p, t in pairs]})


def test_happy_path_assembles_contract_response() -> None:
    gen, review = gen_llm(), review_llm()
    response = run(gen, review)
    assert response.failure is None and response.warnings == []
    assert response.theme is not None and response.theme.answer == "텃밭"
    # LLM 출력에 없는 rulesOut을 코드가 표로 채워 응답에 넣음
    # 화·목은 사건 단서(#782 테마 짜임): 빼는 후보도 특징도 없음
    assert [d.rules_out for d in response.theme.days] == [
        ["창고", "정자"],
        [],
        [],
        [],
        ["놀이터", "창고"],
    ]
    assert [d.clue_feature for d in response.theme.days] == ["물기", None, "지붕", None, "땅"]
    assert [m.day for m in response.missions] == list(DAYS)
    assert [m.thinking_type for m in response.missions] == [DAY_TYPE[d] for d in DAYS]
    assert [d.day for d in response.dialogues] == list(DAYS)
    # 금요일 안내는 LLM이 만든 그대로(단서는 미션 뒤 learning이 보여 주므로 코드가 넣지 않음)
    fri = response.missions[-1].draft
    assert fri.guide is None
    # 대화는 모델이 쓴 줄 그대로(#782 테마 짜임: 끝 두 줄을 코드가 넣지 않음). 증거 발견 줄·수사
    # 연결 문장·오늘 온 까닭은 재료로만 주고, 단서는 넣지 않음
    for dlg_out in response.dialogues:
        # #782 설계 v3: 첫 줄은 코드가 쓴 오늘 온 까닭(주인공의 말), 그 뒤는 모델 줄 그대로
        assert dlg_out.lines[0].speaker == "지호"
        assert dlg_out.lines[0].text.endswith(("왔어.", "시작했어."))
        # #782 설계 v10: 시험 자료의 약속 줄은 요일마다 다름
        assert [x.text for x in dlg_out.lines[1:]] == [x.text for x in dialogue(dlg_out.day).lines]
        assert given(gen, dlg_out.day, HOOK_LABEL) == HOOK[dlg_out.day]
        # #782 미션 방식: 수사 날만 증거를 문제 전에 줌(부탁 날은 문제 뒤 단서로 나옴)
        if WAYS[dlg_out.day] == checks.INVESTIGATE:
            assert given(gen, dlg_out.day, FOUND_LABEL) == DISCOVERY[dlg_out.day]
        else:
            assert DISCOVERY[dlg_out.day] not in gen.users("GeneratedDialogue", dlg_out.day)[-1]
        clues = [d.clue for d in response.theme.days]
        assert not any(c in line.text for c in clues for line in dlg_out.lines)
    # 증거 발견 줄·수사 연결 문장은 내부 칸이라 응답 theme에 없음
    assert "discovery" not in response.theme.days[0].model_dump(by_alias=True)
    assert response.versions.model == "gen-model" and response.versions.prompt == "theme-draft@3"
    assert response.images == response.videos == response.motions == {}
    # 생성 모델: 줄거리 1·미션 5·대화 5, 검토 모델: 미션 검토 5·글 검토 1
    assert (
        gen.count("GeneratedTheme"),
        gen.count("GeneratedDraft"),
        gen.count("GeneratedDialogue"),
    ) == (1, 5, 5)
    assert (review.count("GeneratedMissionReview"), review.count("GeneratedStoryReview")) == (5, 1)
    assert {u.call_type for u in gen.usages + review.usages} == {
        "THEME_DRAFT"
    }  # 미션 생성도 THEME_DRAFT
    assert {u.model for u in review.usages} == {"review-model"}


def test_mission_prompt_gets_hook_not_clues() -> None:
    """단서는 학생이 그날 미션을 마친 뒤 보여 주므로 미션 user 글에 그날·앞 요일 단서가 없고, 그날
    증거 발견 줄·수사 연결 문장(대화로 나가니 질문에 다시 쓰지 않는다는 규칙)이 있다. 금요일도
    큰 질문·후보·단서 목록을 주지 않는다."""
    gen = gen_llm()
    run(gen, review_llm())
    theme = valid_theme()
    clues = [d["clue"] for d in theme["days"]]
    for day in DAYS:
        user = gen.users("GeneratedDraft", day)[0]
        assert not [c for c in clues if c in user], day
        assert HOOK[day] in user
        # #782 미션 방식: 수사 날만 증거 발견 줄을 줌(부탁 날 증거는 문제 뒤 단서)
        assert (DISCOVERY[day] in user) == (WAYS[day] == checks.INVESTIGATE), day
        assert "question에 되풀이하지" in user
        others = [HOOK[d] for d in DAYS if d != day]
        assert not [h for h in others if h in user]
    fri = gen.users("GeneratedDraft", "FRI")[0]
    assert theme["bigQuestion"] not in fri
    # 후보 이름은 "쓰지 말 낱말" 줄에만(정답이 어느 것인지는 알려 주지 않음, 점검 C13)
    avoid = [line for line in fri.splitlines() if line.startswith("- 쓰지 말 낱말")]
    assert len(avoid) == 1 and all(c in avoid[0] for c in theme["candidates"])
    rest = "\n".join(line for line in fri.splitlines() if line not in avoid)
    assert not [c for c in theme["candidates"] if c in rest]
    assert "요일:" not in fri


def test_dialogue_prompt_gets_discovery_not_clues() -> None:
    gen = gen_llm()
    run(gen, review_llm())
    clues = [d["clue"] for d in valid_theme()["days"]]
    for day in DAYS:
        user = gen.users("GeneratedDialogue", day)[0]
        assert not [c for c in clues if c in user], day
        assert (DISCOVERY[day] in user) == (WAYS[day] == checks.INVESTIGATE), day


def test_story_review_sees_discovery_and_hook() -> None:
    review = review_llm()
    run(gen_llm(), review)
    user = review.users("GeneratedStoryReview")[0]
    assert all(HOOK[d] in user for d in DAYS)
    # #782 미션 방식: 증거 발견 줄은 수사 날만(부탁 날은 문제 전에 안 보이는 내부 메모)
    assert all((DISCOVERY[d] in user) == (WAYS[d] == checks.INVESTIGATE) for d in DAYS)


def test_theme_check_failure_regenerates_with_reason() -> None:
    gen = gen_llm(theme=lambda n, d: generated_theme(BROKEN_THEME if n == 1 else None))
    response = run(gen, review_llm())
    assert response.failure is None and gen.count("GeneratedTheme") == 2
    assert "ANSWER_LEAK" in gen.users("GeneratedTheme")[1]


def test_empty_plan_is_regenerated_not_crashed() -> None:
    """요일을 다 내지 않은 줄거리(#782 작은 생성: 조건을 맞출 수 없으면 모델이 빈 줄거리를 냄)는
    코드 수리를 건너뛰고 check_theme(DAYS)으로 다시 생성한다(예전에는 코드 수리가 요일을 못 찾아
    멈춤)."""
    empty = generated_theme().model_copy(update={"days": [], "title": ""})
    gen = gen_llm(theme=lambda n, d: empty if n == 1 else generated_theme())
    response = run(gen, review_llm())
    assert response.failure is None and gen.count("GeneratedTheme") == 2
    assert "DAYS 요일은" in gen.users("GeneratedTheme")[1]


def test_fixable_failure_rewrites_only_those_fields() -> None:
    """칸 하나만 고치면 되는 사유뿐이면 줄거리 전체 대신 그 칸만 고쳐 쓰고 다시 검사(받지 않은
    경로는 무시)."""
    gen = gen_llm(
        theme=lambda n, d: generated_theme(LONG_HOOK),
        fix=lambda n, d: fixes(("WED.missionHook", HOOK["WED"]), ("title", "바뀐 제목")),
    )
    response = run(gen, review_llm())
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 1 and gen.count("GeneratedFixes") == 1
    user = gen.users("GeneratedFixes")[0]
    assert (
        "path: WED.missionHook" in user
        and "지금 글(45자)" in user
        and "상한: 공백 포함 40자" in user
    )
    assert "후보 이름" in user  # 칸 종류별 지킬 점
    assert response.theme is not None and response.theme.title == valid_theme()["title"]
    assert given(gen, "WED", HOOK_LABEL) == HOOK["WED"]


def test_logic_error_repaired_by_code_without_regenerating_plan() -> None:
    """정답 논리가 틀리면 코드가 그 요일 조건만 고치고 그날 단서만 고쳐 써서 줄거리를 다시 만들지
    않음(#535 6차, repair_logic). 종료 이야기 정리는 코드가 표로 다시 붙임(#535 7차)."""
    broken = day_with(
        valid_theme(), "FRI", condition={"kind": "HINT", "feature": "땅", "allowed": ["흙"]}
    )
    gen = gen_llm(
        theme=lambda n, d: generated_theme(broken),
        fix=lambda n, d: fixes(("FRI.clue", valid_theme()["days"][4]["clue"])),
    )
    response = run(gen, review_llm())
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 1 and gen.count("GeneratedFixes") == 1
    user = gen.users("GeneratedFixes")[0]
    assert "path: FRI.clue" in user and "LOGIC_FIX FRI" in user
    assert "path: outro" not in user
    assert response.theme is not None and response.theme.days[4].rules_out
    # 종료 이야기 = 코드 정리(요일별 빠진 후보 → 남은 정답) + LLM 마무리 장면
    assert "단서로" in response.theme.outro and "만 남았어" in response.theme.outro
    assert response.theme.outro.endswith(valid_theme()["outro"])


def test_fix_cap_then_regenerates_plan() -> None:
    """칸 고쳐 쓰기가 상한까지 실패하면 그 사유를 넣어 줄거리를 다시 만듦(횟수는 따로 셈)."""
    gen = gen_llm(
        theme=lambda n, d: generated_theme(LONG_HOOK if n == 1 else None),
        fix=lambda n, d: fixes(("WED.missionHook", "나" * 44)),
    )
    response = run(gen, review_llm())
    assert response.failure is None
    assert gen.count("GeneratedFixes") == get_settings().theme_max_text_fix
    assert gen.count("GeneratedTheme") == 2
    assert "LENGTH WED.missionHook 44자 > 40" in gen.users("GeneratedTheme")[1]


def test_mixed_failure_regenerates_plan_without_fix() -> None:
    """칸 하나로 못 고치는 사유가 섞이면 칸 고쳐 쓰기 없이 줄거리를 다시 만듦."""
    mixed = day_with(BROKEN_THEME, "WED", missionHook="가" * 45)
    gen = gen_llm(theme=lambda n, d: generated_theme(mixed if n == 1 else None))
    response = run(gen, review_llm())
    assert response.failure is None and gen.count("GeneratedTheme") == 2


def test_theme_check_keeps_failing_until_cap() -> None:
    gen = gen_llm(theme=lambda n, d: generated_theme(BROKEN_THEME))
    response = run(gen, review_llm())
    assert gen.count("GeneratedTheme") == get_settings().theme_max_regen + 1
    assert response.theme is None and response.missions == [] and response.dialogues == []
    assert response.failure is not None and response.failure.stage == "THEME"
    assert any(r.startswith("ANSWER_LEAK") for r in response.failure.reasons)
    assert gen.count("GeneratedDraft") == 0


def test_deadline_stops_regeneration() -> None:
    gen = gen_llm(theme=lambda n, d: generated_theme(BROKEN_THEME))
    response = run(gen, review_llm(), deadline_in=100)  # 남은 시간 < theme_min_regen_seconds(180)
    assert gen.count("GeneratedTheme") == 1
    assert response.failure is not None and response.failure.reasons[-1] == DEADLINE_REASON


def test_mission_failure_regenerates_only_that_day() -> None:
    gen = gen_llm(
        draft=lambda n, d: mission_draft(DAY_TYPE[d], hints=2 if d == "WED" and n == 1 else 3)
    )
    response = run(gen, review_llm())
    assert response.failure is None
    assert {d: gen.count("GeneratedDraft", d) for d in DAYS} == {
        "MON": 1,
        "TUE": 1,
        "WED": 2,
        "THU": 1,
        "FRI": 1,
    }
    assert "HINT_COUNT" in gen.users("GeneratedDraft", "WED")[1]


def test_existing_mission_check_reason_goes_through_mission_prompt() -> None:
    gen = gen_llm(
        draft=lambda n, d: (
            mission_draft(DAY_TYPE[d], exampleAnswer=None)
            if d == "MON" and n == 1
            else mission_draft(DAY_TYPE[d])
        )
    )
    run(gen, review_llm())
    second = gen.users("GeneratedDraft", "MON")[1]
    assert "예시 답을 채운다" in second  # 미션 초안 FAILURE_FIX 문장으로 들어감


def test_mission_review_fail_until_cap_is_mission_failure() -> None:
    review = review_llm(
        mission=lambda n, d: mission_review({"MATERIAL": "FAIL"} if d is None else {})
    )
    # 미션 검토 user에는 '오늘(…요일)'이 없어 요일 없이 들어옴 → 다섯 요일 모두 FAIL
    response = run(gen_llm(), review)
    assert response.failure is not None and response.failure.stage == "MISSION"
    assert all(r.split()[1] == "MISSION_REVIEW" for r in response.failure.reasons)
    assert {r.split()[0] for r in response.failure.reasons} == set(DAYS)
    assert review.count("GeneratedStoryReview") == 0


# #971 EXAMPLE_NEXT: 고쳐 쓴 예시 답에도 다음 행동 낱말(공터·나비·산책)
FIXED_EXAMPLE = (
    "처음에는 공터에서 혼자 했지만 지금은 나비 쫓던 친구와 나누어 해. 산책 손님 말처럼 함께하면 "
    "빠르기 때문이야."
)


def example_fix(n: int, d: str | None) -> GeneratedExampleFix:
    return GeneratedExampleFix(exampleAnswer=FIXED_EXAMPLE, finalAnswer="9개")


def test_example_only_failure_rewrites_example_keeping_question() -> None:
    """미션 검토가 예시 답 미완성으로만 실패하면 질문은 두고 예시 답만 고쳐 써서 다시 검토(미션 다시
    생성 없음). 풀이만 최종 답도 바꿈."""
    gen = gen_llm(example=example_fix)
    review = review_llm(
        mission=lambda n, d: mission_review(
            {"EXAMPLE_COMPLETE": "FAIL"} if gen.count("GeneratedExampleFix") == 0 else {}
        )
    )
    response = run(gen, review)
    assert response.failure is None
    assert gen.count("GeneratedDraft") == 5 and gen.count("GeneratedExampleFix") >= 1
    fixed = [m for m in response.missions if m.draft.example_answer == FIXED_EXAMPLE]
    assert fixed
    for m in fixed:
        assert m.draft.question == mission_draft(m.thinking_type).question
        final = m.draft.answer_key.final_answer if m.draft.answer_key else None
        assert (final == "9개") == (m.thinking_type == "SOLVE")
    user = gen.users("GeneratedExampleFix")[0]
    assert "EXAMPLE_COMPLETE 사유" in user and "reviewReasons" in user


def test_example_fix_cap_then_regenerates_mission() -> None:
    """예시 답 고쳐 쓰기가 상한까지 실패하면 미션을 다시 만들고, 끝내 실패하면 MISSION 실패."""
    gen = gen_llm(example=example_fix)
    review = review_llm(mission=lambda n, d: mission_review({"EXAMPLE_COMPLETE": "FAIL"}))
    response = run(gen, review)
    s = get_settings()
    assert response.failure is not None and response.failure.stage == "MISSION"
    assert gen.count("GeneratedDraft") == 5 * (s.theme_max_regen + 1)
    assert gen.count("GeneratedExampleFix") == 5 * (s.theme_max_regen + 1) * s.theme_max_text_fix


def test_example_fix_carries_earlier_reasons_for_same_question() -> None:
    """같은 질문의 두 번째 예시 답 고쳐 쓰기에는 앞서 받은 사유도 함께 넘긴다(#535 닫기 3차)."""
    gen = gen_llm(example=example_fix)
    questions = [mission_draft(DAY_TYPE[d]).question for d in DAYS]
    seen: dict[str, int] = {}

    def mission(n: int, d: str | None) -> GeneratedMissionReview:
        question = next(q for q in questions if q in review.calls[-1][2])
        seen[question] = seen.get(question, 0) + 1
        if seen[question] >= 3:
            return mission_review()
        reply = mission_review({"EXAMPLE_COMPLETE": "FAIL"})
        reply.items[0].reason = f"예시사유{seen[question]}"
        return reply

    review = review_llm(mission=mission)
    response = run(gen, review)
    assert response.failure is None
    # 요일마다 지문이 달라 질문도 달라짐(#782): 월요일 미션의 고쳐 쓰기 두 번만 봄
    first, second = [u for u in gen.users("GeneratedExampleFix") if questions[0] in u]
    assert "예시사유1" in first and "예시사유2" not in first
    assert "예시사유1" in second and "예시사유2" in second


def test_mission_review_warn_becomes_warning() -> None:
    review = review_llm(mission=lambda n, d: mission_review({"MATERIAL": "WARN"}))
    response = run(gen_llm(), review)
    assert response.failure is None
    assert [(w.stage, w.item) for w in response.warnings] == [("MISSION", d) for d in DAYS]


def test_dialogue_failure_omits_that_day_with_warning() -> None:
    gen = gen_llm(
        dlg=lambda n, d: (
            dialogue(lines=[GeneratedLine(speaker="할머니", text="여기야.")] * 4)
            if d == "MON"
            else dialogue(d)
        )
    )  # 월요일 화자가 등장인물 밖
    response = run(gen, review_llm())
    assert response.failure is None
    assert [d.day for d in response.dialogues] == ["TUE", "WED", "THU", "FRI"]
    assert gen.count("GeneratedDialogue", "MON") == get_settings().theme_max_regen + 1
    assert {(w.stage, w.item) for w in response.warnings} == {("DIALOGUE", "MON")}


def test_story_review_standard_fit_regenerates_named_day() -> None:
    review = review_llm(
        story=lambda n, d: (
            story_review({"STANDARD_FIT": "FAIL"}, {"STANDARD_FIT": ["THU"]})
            if n == 1
            else story_review()
        )
    )
    gen = gen_llm()
    response = run(gen, review)
    assert response.failure is None and review.count("GeneratedStoryReview") == 2
    assert {d: gen.count("GeneratedDraft", d) for d in DAYS} == {
        "MON": 1,
        "TUE": 1,
        "WED": 1,
        "THU": 2,
        "FRI": 1,
    }
    assert gen.count("GeneratedDialogue", "THU") == 2 and gen.count("GeneratedTheme") == 1
    assert "STANDARD_FIT" in gen.users("GeneratedDraft", "THU")[1]
    assert len(response.dialogues) == 5


MON_CLUE = next(d for d in valid_theme()["days"] if d["day"] == "MON")["clue"]


def clue_fail(times: int, extra: dict[str, str] | None = None) -> Handler:
    """처음 times번은 월요일 CLUE_LOGIC FAIL(extra 항목도 함께), 그 뒤 통과."""
    return lambda n, d: (
        story_review({"CLUE_LOGIC": "FAIL", **(extra or {})}, {"CLUE_LOGIC": ["MON"]})
        if n <= times
        else story_review()
    )


def test_story_review_clue_logic_fixes_clue_only() -> None:
    """CLUE_LOGIC 처음 한 번은 지목된 요일 단서 문장만 고쳐 쓰고 다시 검토(미션·대화는 그대로)."""
    gen = gen_llm(fix=lambda n, d: fixes(("MON.clue", MON_CLUE + "!")))
    review = review_llm(story=clue_fail(1))
    response = run(gen, review)
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 1 and gen.count("GeneratedDraft") == 5
    assert gen.count("GeneratedDialogue") == 5 and gen.count("GeneratedFixes") == 1
    assert review.count("GeneratedStoryReview") == 2
    user = gen.users("GeneratedFixes")[0]
    assert "path: MON.clue" in user and "CLUE_LOGIC ['MON'] CLUE_LOGIC 사유" in user
    assert response.theme is not None
    # #971: 이어 가기 날 응답 단서는 다음 행동 이름표가 붙음
    mon = next(d for d in response.theme.days if d.day == "MON")
    assert mon.clue == f"{NEXT['MON']}: {MON_CLUE}!"


def test_story_review_clue_logic_again_regenerates_plan() -> None:
    """고쳐 쓴 뒤에도 CLUE_LOGIC이면 이야기 틀 문제로 보고 줄거리부터(고쳐 쓰기는 한 번만)."""
    gen = gen_llm(fix=lambda n, d: fixes(("MON.clue", MON_CLUE)))
    review = review_llm(story=clue_fail(2))
    response = run(gen, review)
    assert response.failure is None
    assert gen.count("GeneratedFixes") == 1 and gen.count("GeneratedTheme") == 2
    assert gen.count("GeneratedDraft") == 10 and review.count("GeneratedStoryReview") == 3
    assert "CLUE_LOGIC" in gen.users("GeneratedTheme")[1]


def test_story_review_clue_logic_with_answer_hint_regenerates_plan() -> None:
    gen = gen_llm()  # 고쳐 쓰기 처리기 없음: 부르면 시험 실패
    response = run(gen, review_llm(story=clue_fail(1, {"ANSWER_HINT": "FAIL"})))
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 2 and gen.count("GeneratedDraft") == 10


def test_fixed_clue_failing_code_check_regenerates_plan() -> None:
    """고친 단서가 대상 낱말을 빠뜨리면(CLUE_OWNER) 줄거리부터 다시."""
    gen = gen_llm(fix=lambda n, d: fixes(("MON.clue", "내가 본 발자국은 젖어 있었어.")))
    response = run(gen, review_llm(story=clue_fail(1)))
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 2 and gen.count("GeneratedDraft") == 10
    assert "CLUE_OWNER MON" in gen.users("GeneratedTheme")[1]


def test_fixed_clue_failing_only_form_gets_template_not_new_plan() -> None:
    """#782 설계 v4(B1): 고친 단서가 꼴·출처 검사(CLUE_TEXT·CLUE_SOURCE)에만 걸리면 코드 틀 문장으로
    바꿔 통과(3차 측정 auto4b·new4b: 이 길에 틀 문장이 없어 줄거리를 다시 만들다 마감)."""
    gen = gen_llm(fix=lambda n, d: fixes(("MON.clue", "보리가 어딘가를 지나갔어.")))
    response = run(gen, review_llm(story=clue_fail(1)))
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 1
    assert response.theme is not None and "젖음" in response.theme.days[0].clue


def test_story_review_shape_error_reviews_again_only() -> None:
    def story(n: int, d: str | None) -> GeneratedStoryReview:
        review = story_review()
        return GeneratedStoryReview(items=review.items[:4]) if n == 1 else review

    gen, review = gen_llm(), review_llm(story=story)
    assert run(gen, review).failure is None
    assert review.count("GeneratedStoryReview") == 2 and gen.count("GeneratedDraft") == 5


def test_story_review_keeps_failing_until_cap() -> None:
    review = review_llm(story=lambda n, d: story_review({"GRADE_VOCAB": "FAIL"}))
    response = run(gen_llm(), review)
    assert review.count("GeneratedStoryReview") == get_settings().theme_review_max_rerun + 1
    assert response.failure is not None and response.failure.stage == "REVIEW"
    assert response.theme is not None  # 줄거리는 있었으므로 함께 돌려줌(learning CHECK_FAILED)


def test_story_review_warn_is_warning() -> None:
    review = review_llm(
        story=lambda n, d: story_review({"GRADE_VOCAB": "WARN"}, {"GRADE_VOCAB": ["MON"]})
    )
    response = run(gen_llm(), review)
    assert [(w.stage, w.item) for w in response.warnings] == [("REVIEW", "GRADE_VOCAB MON")]


def test_previous_failures_seed_first_prompts() -> None:
    body = request_body(
        previousFailures=[
            {"stage": "THEME", "reasons": ["LOGIC TUE 이전 사유"]},
            {
                "stage": "MISSION",
                "reasons": ["WED LEAK ANSWER_KEY", "FRI HINT_COUNT 생각 열기 개수"],
            },
            {"stage": "IMAGE", "reasons": ["INTRO 그림 사유"]},
        ]
    )
    gen = gen_llm()
    run(gen, review_llm(), body)
    assert "LOGIC TUE 이전 사유" in gen.users("GeneratedTheme")[0]
    assert (
        "INTRO 그림 사유" not in gen.users("GeneratedTheme")[0]
    )  # 그림 사유는 글 단계에서 쓰지 않음
    assert "정답을 쓰지 않는다" in gen.users("GeneratedDraft", "WED")[0]
    assert "HINT_COUNT" in gen.users("GeneratedDraft", "FRI")[0]
    assert "정답을 쓰지 않는다" not in gen.users("GeneratedDraft", "MON")[0]


@pytest.mark.parametrize(
    ("where", "code", "status"),
    [
        ("theme", "LLM_INVALID_OUTPUT", 502),
        ("theme", "LLM_RATE_LIMITED", 503),
        ("draft", "LLM_INVALID_OUTPUT", 502),
        ("draft", "LLM_TIMEOUT", 503),
        ("story", "LLM_INVALID_OUTPUT", 502),
    ],
)
def test_llm_failures_map_to_502_503(where: str, code: str, status: int) -> None:
    def fail(n: int, d: str | None) -> Any:
        return LlmError(code, retryable=False)

    gen = (
        gen_llm(theme=fail)
        if where == "theme"
        else gen_llm(draft=fail)
        if where == "draft"
        else gen_llm()
    )
    review = review_llm(story=fail) if where == "story" else review_llm()
    with pytest.raises(ApiError) as caught:
        run(gen, review)
    assert caught.value.status == status


def test_text_substitute_and_material_rules_in_prompts() -> None:
    """글로 직접 할 수 없는 활동은 문제 글 자료로 대신하고 성취기준에 맞다고 봄(사용자 결정
    2026-11-11). 같은 원칙 글이 미션 생성·미션 검토·글 검토·예시 답 고쳐 쓰기 네 곳에 똑같이 들어가
    기준이 어긋나지 않음(실측 분석: 글 검토에만 빠져 실패). 내용을 적지 않은 자료를 살피게
    하지 않음."""
    from app.theme_draft import prompts

    extra = prompts.mission_extra(valid_theme(), "MON", 3, [])
    for text in (
        extra,
        prompts.MISSION_REVIEW_SYSTEM,
        prompts.REVIEW_SYSTEM,
        prompts.EXAMPLE_FIX_SYSTEM,
    ):
        assert prompts.TEXT_ONLY in text
    assert "내용을 적지 않은 자료" in extra
    assert "방법이나 계획을 묻지 않고" in extra and "요소 수(2~3가지)만큼만" in extra
    assert "비교 문제로 만들지 않는다" in extra
    assert "그 내용이 질문 글에 없으면 결함" in prompts.MISSION_REVIEW_SYSTEM
    # 풀이는 미션 초안 형식상 예시 답 없이 최종 답만 봄(검토와 형식 맞춤)
    assert "exampleAnswer가 없어도 되고" in prompts.MISSION_REVIEW_SYSTEM
    # 글 검토: 배울 것을 말하는 수사 연결 문장·기록 속 지나간 대상 모습은 허용
    # (줄거리 프롬프트와 맞춤)
    assert "설계상 허용" in prompts.REVIEW_SYSTEM and "지나간" in prompts.REVIEW_SYSTEM
    tue = prompts.mission_extra(valid_theme(), "TUE", 3, [])
    # 다른 관점은 질문·예시 답에 넣고 필수 여부는 관리자가 요소에서 정함(점검 C19)
    assert "다른 관점(반대 의견·예외)을 생각해 답하는 부분을" in tue and "관리자가" in tue
    assert "선택처럼 쓰였다는 이유로 결함이 아니다" in prompts.MISSION_REVIEW_SYSTEM
    assert "선택처럼 쓰였다는 이유로 결함이 아니다" in prompts.REVIEW_SYSTEM


def test_theme_missions_use_theme_question_limit() -> None:
    """테마 미션 질문 상한은 테마 설정(기준안 400자)으로 미션 프롬프트에 알리고 검사한다."""
    gen = gen_llm()
    response = run(gen, review_llm())
    assert response.failure is None
    limit = get_settings().theme_question_max_chars[3]
    assert all(f"질문 글자 수 상한: {limit}자" in u for u in gen.users("GeneratedDraft"))


def test_plan_names_and_variety_rules() -> None:
    """이름은 코드가 목록에서 고르고 같은 요청(주·학년)이면 같음, 큰 질문은 '마지막으로 둔 곳'만
    되풀이하지 않고 사람을 탓하는 질문은 금지, 인물은 장면에 맞게(실측: 큰 질문 19/19가 같은 틀,
    민지·준호 반복)."""
    from app.theme_draft import families, prompts

    request = ThemeDraftRequest.model_validate(request_body())
    names = prompts.names_for(request)
    assert len(names) == prompts.NAMES_PER_THEME and set(names) <= set(prompts.NAME_POOL)
    assert prompts.names_for(request) == names
    other = ThemeDraftRequest.model_validate(request_body(weekStart="2026-11-23"))
    assert prompts.names_for(other) != names
    user = prompts.plan_user(request, [])
    assert "등장인물 이름 목록" in user and all(n in user for n in names)
    # #634: 큰 질문 종류는 줄거리 종류 규칙(잃어버린 것 찾기)으로 옮김
    assert "'마지막으로 둔 곳'만 되풀이하지 않는다" in families.LOST.rules
    assert "사람을 탓하는 질문은 쓰지 않는다" in prompts.PLAN_SYSTEM
    assert "흔한 이름" not in prompts.PLAN_SYSTEM
    extra = prompts.mission_extra(valid_theme(), "MON", 3, [])
    assert "새 이름을 만들지 않는다" in extra


def test_clue_logic_rules_in_prompts() -> None:
    """글 검토 CLUE_LOGIC 실패 20건(실측 2026-11-11)을 줄이는 규칙: 허용 값 여럿은 그중 한 곳,
    특징 밝히기, 값끼리 겹치지 않기, 이야기 때 맞추기, 종료 정리는 코드가 씀, RULE은 단정. 미션은
    그날 특징만 알고 사건 현장의 그 값을 정하지 않음(값 낱말을 다 막으면 성취기준 개념을 못 씀)."""
    from app.theme_draft import prompts

    for rule in (
        "늘어놓지 않고 빠지는 값",  # #782 설계 v3: 허용 값 여럿은 부정형
        "무엇에 대한 것인지",
        "뜻이 겹치지 않아",
        "evidence.when이 가리키는 그때와 맞춘다",
        "정리는 코드가 특징 표로 계산해 앞에 붙이므로",  # 종료 정리는 코드가 씀(#535 7차)
        "RULE 단서는 단정해서",
    ):
        assert rule in prompts.PLAN_SYSTEM
    theme = valid_theme()
    mon = " ".join(prompts.fix_rules(theme, "MON.clue"))
    # MON은 RULE·허용 값 하나(#782부터 월 RULE). #782 설계 v3: 늘어놓기는 어느 꼴이든 하지 않음
    assert "단정해서" in mon and "'나'로 잇는다" not in mon
    wed = " ".join(prompts.fix_rules(theme, "WED.clue"))
    # 증거 종류는 그대로 두고 문장만 맞춤(CLUE_EVIDENCE 칸 고쳐 쓰기): WED는 SIGHTING, FRI는 RECORD
    assert "증거 종류가 목격" in wed
    assert "증거 종류가 기록" in " ".join(prompts.fix_rules(theme, "FRI.clue"))
    assert "중 한 곳" not in prompts.PLAN_SYSTEM  # 단서를 길게 만든 예시(40자 초과 13→26번)는 뺌
    # 증거 발견 줄·수사 연결 문장 예시가 녹음기라 초안 35%에 녹음이 들어감 → 형식만. #782 테마
    # 짜임부터 둘 다 대화 재료라 정해진 말 꼴('<증거>에 <그 부분>도 있어')을 두지 않음
    assert "녹음기" not in prompts.PLAN_SYSTEM and "<그 부분>도 있어" not in prompts.PLAN_SYSTEM
    extra = prompts.mission_extra(theme, "FRI", 3, [])
    feature_line = extra.split("오늘 단서가 다루는 특징: '땅'")[1].split("\n")[0]
    assert "흙" not in feature_line  # 단서 값 낱말은 알리지 않음


# --- #535 증거 배정·미션 소재 ---------------------------------------------------------
def test_plan_prompt_has_evidence_plan() -> None:
    """요일별 증거 종류·기록 매체는 코드가 정해 줄거리 요청에 넣음(같은 요청이면 같은 배정)."""
    from app.theme_draft import prompts

    request = ThemeDraftRequest.model_validate(request_body())
    user = prompts.plan_user(request, [])
    assert "증거 종류 배정" in user
    assert "- FRI(금): RECORD(기록), 기록 매체: 일지" in user and "- MON(월): TRACE(흔적)" in user
    assert prompts.plan_user(request, []) == user
    assert "'증거 종류 배정'을 그대로 쓴다" in prompts.PLAN_SYSTEM


def test_evidence_kind_off_plan_rewrites_that_day_only() -> None:
    """줄거리가 배정과 다른 증거 종류를 쓰면 코드가 종류를 배정대로 바꾸고 그날 단서·증거 발견 줄·
    수사 연결 문장만 고쳐 씀(줄거리를 다시 만들지 않음, CLUE_EVIDENCE 칸 고쳐 쓰기 경로)."""
    off = day_with(
        valid_theme(),
        "FRI",
        evidence={"kind": "SIGHTING", "when": "보리가 사라진 날 오후"},
        clue="보리가 지나간 길이 젖어 있었대.",
        discovery="가게 주인이 보리를 봤대! 물어보자.",
        missionHook="주인 말을 풀기 전에 이번 주를 돌아보자. 도와줄래?",
    )
    fri = next(d for d in valid_theme()["days"] if d["day"] == "FRI")
    gen = gen_llm(
        theme=lambda n, d: generated_theme(off),
        fix=lambda n, d: fixes(
            ("FRI.clue", fri["clue"]),
            ("FRI.discovery", DISCOVERY["FRI"]),
            ("FRI.missionHook", HOOK["FRI"]),
        ),
    )
    response = run(gen, review_llm())
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 1 and gen.count("GeneratedFixes") == 1
    user = gen.users("GeneratedFixes")[0]
    assert all(f"path: FRI.{k}" in user for k in ("clue", "discovery", "missionHook"))
    assert "증거 종류가 배정과 다름(배정 기록 RECORD, 지금 SIGHTING)" in user
    assert "기록 매체 '일지' 낱말을 그대로 쓴다" in user and "기록(RECORD) 증거" in user
    # #782 설계 v4: 부탁 날 기록 단서가 매체 낱말로 시작하면 코드가 '내 '를 붙임(돕는 사람의 기록)
    # #971: 응답 단서는 다음 행동 이름표 + 그 사람의 말
    assert response.theme is not None
    assert response.theme.days[4].clue == f"{NEXT['FRI']}: 내 {fri['clue']}"
    # 금요일은 부탁 날이라 대화 재료에 증거 발견 줄이 없고 수사 연결 문장만
    assert WAYS["FRI"] == checks.FOLLOW and given(gen, "FRI", HOOK_LABEL) == HOOK["FRI"]


def test_mission_prompt_and_review_tie_problem_to_story() -> None:
    """미션 이야기 조각은 문제의 주 자료를 그날 찾은 증거(수사 연결 문장이 가리킨 부분)로 삼게
    하고(#782 A안), 미션 검토는 그날 장소·증거 발견 줄·수사 연결 문장을 받아 STORY_LINK로 본다."""
    from app.theme_draft import prompts

    extra = prompts.mission_extra(valid_theme(), "THU", 3, [])  # missionWay 없음 = 수사
    assert "오늘 미션 방식: 수사. 문제의 주 자료는 오늘 돕는 사람이 가진 증거" in extra
    # 연습 글·안내 글·그림책 장면이 장면 소품으로 통과하던 허용 문구는 뺌(#782)
    assert "등장인물이 만든 자료(쓴 글·카드·연습 문제)도 이야기" not in extra
    assert "등장인물이 만든 자료" not in prompts.MISSION_REVIEW_SYSTEM
    assert "STORY_LINK" in extra and "사건 현장의 오늘 단서 특징 값은 정하지" in extra
    # 1차 글 실측(2026-11-13): 돌아보기의 자기 경험을 선택으로 돌리거나 STORY_LINK가 자기 경험을
    # 결함으로 봐서 금요일 미션이 실패함 → 자기 경험은 그대로 묻고 소재 판정에서 뺌
    assert "선택으로 두지 말고 그대로 묻는다" in extra
    assert "판정에서 뺀다" in prompts.MISSION_REVIEW_SYSTEM
    # 수사 연결 문장이 가리키는 증거의 부분은 단서 특징 값과 무관해야 문제가 그 값을 정하지 않음.
    # '풀려면 …이 필요해' 억지 연결 형식은 뺌(#782 C안)
    # #782 미션 방식: 수사 연결 문장·지문은 그날 단서 결론(allowed 값)을 말하지 않음
    assert "그날 단서 결론(allowed 값)·후보 이름·정답은 말하지 않는다" in prompts.PLAN_SYSTEM
    assert "'<증거>를 풀려면 <배울 것>이 필요해'처럼" in prompts.PLAN_SYSTEM
    assert "형식은 '<찾은 증거>를 풀려면" not in prompts.PLAN_SYSTEM
    assert (
        "STORY_LINK:" in prompts.MISSION_REVIEW_SYSTEM
        and "네 항목" in prompts.MISSION_REVIEW_SYSTEM
    )
    review = review_llm()
    run(gen_llm(), review)
    users = review.users("GeneratedMissionReview")
    assert len(users) == 5
    thu = next(u for u in users if HOOK["THU"] in u)
    story = json.loads(thu)["story"]
    assert story == {
        "place": "마을 thu 길",
        "target": "강아지 보리",
        "discovery": DISCOVERY["THU"],
        "missionHook": HOOK["THU"],
        "missionMaterial": MATERIAL["THU"],  # #782 줄거리가 정한 미션 지문
        # #782 미션 방식·#971(기본 요청 배정 목요일 이어 가기·갈 곳)과 그날 장소 사람
        "missionWay": "이어 가기(FOLLOW)",
        "helper": HELPER["THU"],
        "nextTarget": f"갈 곳: {NEXT['THU']}",
    }
    assert "텃밭" not in thu  # 정답·단서는 주지 않음


# 목요일은 부탁 날이라 할 일에 흔적 낱말(발자국)을 쓰지 않음(#782 EVIDENCE_EARLY)
NEW_HOOK = "산책 길 수를 세려면 계산이 필요해. 같이 해 볼래?!"


def story_link_review(still: bool = False, day: str = "THU") -> tuple[ScriptedLlm, list[str]]:
    """그 요일(기본 목요일) 첫 미션 검토만 STORY_LINK FAIL. still이면 수사 연결 문장을 고친 뒤 다시
    봐도 FAIL."""
    seen: list[str] = []

    def mission(n: int, d: str | None) -> GeneratedMissionReview:
        user = review.calls[-1][2]
        if HOOK[day] in user or NEW_HOOK in user:
            seen.append(user)
            if len(seen) == 1 or still:
                return mission_review({"STORY_LINK": "FAIL"})
        return mission_review()

    review = review_llm(mission=mission)
    return review, seen


def test_story_link_fail_rewrites_hook_then_rechecks() -> None:
    """미션 검토 STORY_LINK FAIL이면 미션은 다시 만들지 않고 그 요일 수사 연결 문장만 문제 소재에
    맞게 고쳐 쓴 뒤 다시 확인. 통과하면 경고가 사라지고 대화 마지막 줄이 고친 문장(#535 닫기)."""
    review, seen = story_link_review()
    gen = gen_llm(
        hook=lambda n, d: hook_fixes(("THU.missionHook", NEW_HOOK), ("THU.clue", "무시됨"))
    )
    response = run(gen, review)
    assert response.failure is None and len(seen) == 2
    assert all(gen.count("GeneratedDraft", d) == 1 for d in DAYS)
    # 요일 노드마다 그 요일 하나만 다듬고(미션이 통과한 직후), 경고 난 요일은 사유를 함께
    assert gen.count("GeneratedHookFixes") == 5 and gen.count("GeneratedFixes") == 0
    users = gen.users("GeneratedHookFixes")
    assert all(sum(f"path: {d}.missionHook" in u for u in users) == 1 for d in DAYS)
    assert all(u.count("path: ") == 1 and "오늘 문제(그대로 둠)" in u for u in users)
    assert [("THU.missionHook" in u) for u in users if "STORY_LINK 사유" in u] == [True]
    assert response.warnings == []
    assert given(gen, "THU", HOOK_LABEL) == NEW_HOOK
    assert (
        response.theme is not None
        and response.theme.days[3].clue == f"{NEXT['THU']}: {valid_theme()['days'][3]['clue']}"
    )


def test_story_link_still_failing_after_hook_rewrite_stays_warning() -> None:
    """고쳐 쓴 뒤에도 STORY_LINK가 남으면 경고만(사용자 결정 2026-11-15), 미션은 그대로."""
    review, seen = story_link_review(still=True)
    gen = gen_llm(hook=lambda n, d: hook_fixes(("THU.missionHook", NEW_HOOK)))
    response = run(gen, review)
    assert response.failure is None and len(seen) == 2
    assert all(gen.count("GeneratedDraft", d) == 1 for d in DAYS)
    assert [(w.stage, w.item, w.reason) for w in response.warnings] == [
        ("MISSION", "THU", "MISSION_REVIEW STORY_LINK STORY_LINK 사유")
    ]


def test_hook_rewrite_failing_code_check_keeps_old_hook() -> None:
    """고친 수사 연결 문장이 코드 검사(40자)에 걸리면 원래 문장을 두고 다시 확인하지 않음, 경고는
    남김."""
    review, seen = story_link_review()
    gen = gen_llm(hook=lambda n, d: hook_fixes(("THU.missionHook", "가" * 45)))
    response = run(gen, review)
    assert response.failure is None and len(seen) == 1
    assert given(gen, "THU", HOOK_LABEL) == HOOK["THU"]
    assert [(w.stage, w.item) for w in response.warnings] == [("MISSION", "THU")]


def test_hook_rewrite_telling_clue_conclusion_keeps_old_hook() -> None:
    """고친 수사 연결 문장이 그날 단서 결론(허용 값)을 말하면 원래 문장을 둠(hook_problems).
    목요일은 사건 단서라(#782 테마 짜임) 허용 값이 있는 금요일(땅 흙)로 봄."""
    review, seen = story_link_review(day="FRI")
    gen = gen_llm(
        hook=lambda n, d: hook_fixes(("FRI.missionHook", "흙 자국을 세려면 계산이 필요해."))
    )
    response = run(gen, review)
    assert response.failure is None and len(seen) == 1
    assert given(gen, "FRI", HOOK_LABEL) == HOOK["FRI"]
    assert [(w.stage, w.item) for w in response.warnings] == [("MISSION", "FRI")]


def test_story_link_with_other_fail_still_regenerates_for_the_other() -> None:
    """다른 항목 FAIL이 함께 있으면 그 항목 때문에만 다시 만들고, 다시 만든 미션에 넣는 사유에
    STORY_LINK는 없음."""

    flagged: list[str] = []

    def mission(n: int, d: str | None) -> GeneratedMissionReview:
        user = review.calls[-1][2]
        if HOOK["THU"] in user and not flagged:
            flagged.append(user)
            return mission_review({"STORY_LINK": "FAIL", "MATERIAL": "FAIL"})
        return mission_review()

    review = review_llm(mission=mission)
    gen = gen_llm()
    response = run(gen, review)
    assert response.failure is None
    assert gen.count("GeneratedDraft", "THU") == 2
    second = gen.users("GeneratedDraft", "THU")[1]
    assert "MISSION_REVIEW MATERIAL MATERIAL 사유" in second
    assert "STORY_LINK 사유" not in second


MON_HOOK = "길에서 본 것을 풀려면 환경을 알아야 해. 도와줄래?"


def test_hooks_rewritten_for_all_days_to_name_problem_material() -> None:
    """경고가 없어도 요일 미션이 통과하면 그 요일 수사 연결 문장을 문제 소재 낱말이 들어가게
    다듬고(요일마다 LLM 1번), 경고 없는 요일은 다시 검토하지 않음(#535 닫기)."""
    review = review_llm()
    gen = gen_llm(hook=lambda n, d: hook_fixes(("MON.missionHook", MON_HOOK)))
    response = run(gen, review)
    assert response.failure is None and response.warnings == []
    assert gen.count("GeneratedHookFixes") == 5
    assert review.count("GeneratedMissionReview") == 5  # 다시 확인 없음
    assert given(gen, "MON", HOOK_LABEL) == MON_HOOK
    assert given(gen, "TUE", HOOK_LABEL) == HOOK["TUE"]  # 고치지 않은 요일은 그대로


def test_field_fixes_are_called_per_day_so_days_do_not_mix() -> None:
    """칸 고쳐 쓰기는 요일마다 따로 부름(#782 실측 r782-ways-rd4: 한 호출에 목요일 지문과 금요일
    수사 연결 문장을 함께 고치다 금요일 문장에 목요일 '삼각형 카드'가 섞임)."""
    broken = valid_theme()
    broken["days"][1]["discovery"] = "가" * 50
    broken["days"][3]["discovery"] = "나" * 50
    gen = gen_llm(
        theme=lambda n, d: generated_theme(broken),
        fix=lambda n, d: fixes(
            ("TUE.discovery", DISCOVERY["TUE"]), ("THU.discovery", DISCOVERY["THU"])
        ),
    )
    response = run(gen, review_llm())
    assert response.failure is None
    users = gen.users("GeneratedFixes")
    assert len(users) == 2  # 화·목 따로
    assert sum("path: TUE.discovery" in u for u in users) == 1
    assert all(("TUE." in u) != ("THU." in u) for u in users)  # 한 호출에 한 요일만
