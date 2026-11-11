"""테마 그래프(글 단계) 시험.

실제 LLM은 부르지 않고 출력 형식·요일로 응답을 정하는 가짜 LLM을 쓴다.
"""

import asyncio
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
from app.theme_draft.checks import DAY_KO, DAY_TYPE, DAYS
from app.theme_draft.models import (
    GeneratedDialogue,
    GeneratedExampleFix,
    GeneratedFixes,
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
    HOOK,
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
) -> ScriptedLlm:
    """fix가 없으면 칸 고쳐 쓰기 호출은 처리기가 없어 시험이 실패한다(예상 밖 호출을 드러냄)."""
    handlers: dict[type, Handler] = {
        GeneratedTheme: theme or (lambda n, d: generated_theme()),
        GeneratedDraft: draft or (lambda n, d: mission_draft(DAY_TYPE[d])),
        GeneratedDialogue: dlg or (lambda n, d: dialogue()),
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


def test_happy_path_assembles_contract_response() -> None:
    gen, review = gen_llm(), review_llm()
    response = run(gen, review)
    assert response.failure is None and response.warnings == []
    assert response.theme is not None and response.theme.answer == "텃밭"
    # LLM 출력에 없는 rulesOut을 코드가 표로 채워 응답에 넣음
    assert [d.rules_out for d in response.theme.days] == [
        [],
        [],
        ["창고", "정자"],
        ["놀이터", "창고"],
        [],
    ]
    assert [m.day for m in response.missions] == list(DAYS)
    assert [m.thinking_type for m in response.missions] == [DAY_TYPE[d] for d in DAYS]
    assert [d.day for d in response.dialogues] == list(DAYS)
    # 금요일 안내는 LLM이 만든 그대로(단서는 미션 뒤 learning이 보여 주므로 코드가 넣지 않음)
    fri = response.missions[-1].draft
    assert fri.guide is None
    # 대화 끝 두 줄 = 그날 증거 발견 줄(화자 기본 뭉치)·수사 연결 문장 그대로, 단서·요약 줄 없음
    for dlg_out in response.dialogues:
        assert [x.speaker for x in dlg_out.lines[-2:]] == ["뭉치", "뭉치"]
        assert [x.text for x in dlg_out.lines[-2:]] == [DISCOVERY[dlg_out.day], HOOK[dlg_out.day]]
        clues = [d.clue for d in response.theme.days]
        assert not any(c in line.text for c in clues for line in dlg_out.lines)
    # 증거 발견 줄·수사 연결 문장은 내부 칸이라 응답 theme에 없음
    assert "discovery" not in response.theme.days[0].model_dump(by_alias=True)
    assert response.versions.model == "gen-model" and response.versions.prompt == "theme-draft@1"
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
        assert HOOK[day] in user and DISCOVERY[day] in user
        assert "question에 다시 쓰지 않는다" in user
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
        assert DISCOVERY[day] in user


def test_story_review_sees_discovery_and_hook() -> None:
    review = review_llm()
    run(gen_llm(), review)
    user = review.users("GeneratedStoryReview")[0]
    assert all(DISCOVERY[d] in user and HOOK[d] in user for d in DAYS)


def test_theme_check_failure_regenerates_with_reason() -> None:
    gen = gen_llm(theme=lambda n, d: generated_theme(BROKEN_THEME if n == 1 else None))
    response = run(gen, review_llm())
    assert response.failure is None and gen.count("GeneratedTheme") == 2
    assert "ANSWER_LEAK" in gen.users("GeneratedTheme")[1]


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
    wed = next(x for x in response.dialogues if x.day == "WED")
    assert wed.lines[-1].text == HOOK["WED"]


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


FIXED_EXAMPLE = "처음에는 혼자 했지만 지금은 친구와 나누어 해. 까닭은 함께하면 빠르기 때문이야."


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


def test_mission_review_warn_becomes_warning() -> None:
    review = review_llm(mission=lambda n, d: mission_review({"MATERIAL": "WARN"}))
    response = run(gen_llm(), review)
    assert response.failure is None
    assert [(w.stage, w.item) for w in response.warnings] == [("MISSION", d) for d in DAYS]


def test_dialogue_failure_omits_that_day_with_warning() -> None:
    gen = gen_llm(
        dlg=lambda n, d: dialogue("할머니") if d == "MON" else dialogue()
    )  # 월요일 증거 발견 줄 화자가 등장인물 밖
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


def test_story_review_clue_logic_regenerates_plan() -> None:
    review = review_llm(
        story=lambda n, d: story_review({"CLUE_LOGIC": "FAIL"}) if n == 1 else story_review()
    )
    gen = gen_llm()
    response = run(gen, review)
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 2 and gen.count("GeneratedDraft") == 10
    assert "CLUE_LOGIC" in gen.users("GeneratedTheme")[1]


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
    from app.theme_draft import prompts

    request = ThemeDraftRequest.model_validate(request_body())
    names = prompts.names_for(request)
    assert len(names) == prompts.NAMES_PER_THEME and set(names) <= set(prompts.NAME_POOL)
    assert prompts.names_for(request) == names
    other = ThemeDraftRequest.model_validate(request_body(weekStart="2026-11-23"))
    assert prompts.names_for(other) != names
    user = prompts.plan_user(request, [])
    assert "등장인물 이름 목록" in user and all(n in user for n in names)
    assert "'마지막으로 둔 곳'만 되풀이하지 않는다" in prompts.PLAN_SYSTEM
    assert "사람을 탓하는 질문은 쓰지 않는다" in prompts.PLAN_SYSTEM
    assert "흔한 이름" not in prompts.PLAN_SYSTEM
    extra = prompts.mission_extra(valid_theme(), "MON", 3, [])
    assert "새 이름을 만들지 않는다" in extra
