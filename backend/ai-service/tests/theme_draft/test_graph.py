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
    theme: Handler | None = None, draft: Handler | None = None, dlg: Handler | None = None
) -> ScriptedLlm:
    return ScriptedLlm(
        "gen-model",
        {
            GeneratedTheme: theme or (lambda n, d: generated_theme()),
            GeneratedDraft: draft or (lambda n, d: mission_draft(DAY_TYPE[d])),
            GeneratedDialogue: dlg or (lambda n, d: dialogue()),
        },
    )


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


BROKEN_THEME = theme_with(title="텃밭의 비밀")  # ANSWER_LEAK


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
    # 대화 마지막 줄 = 그날 증거 발견 줄 그대로(화자 기본 뭉치), 단서·요약 줄 없음
    for dlg_out in response.dialogues:
        assert dlg_out.lines[-1].speaker == "뭉치"
        assert dlg_out.lines[-1].text == DISCOVERY[dlg_out.day]
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
    증거 발견 줄·수사 연결 문장과 '질문은 수사 연결 문장으로 시작' 규칙이 있다. 금요일도 큰 질문·
    후보·단서 목록을 주지 않는다."""
    gen = gen_llm()
    run(gen, review_llm())
    theme = valid_theme()
    clues = [d["clue"] for d in theme["days"]]
    for day in DAYS:
        user = gen.users("GeneratedDraft", day)[0]
        assert not [c for c in clues if c in user], day
        assert HOOK[day] in user and DISCOVERY[day] in user
        assert "수사 연결 문장으로 그대로 시작" in user
        others = [HOOK[d] for d in DAYS if d != day]
        assert not [h for h in others if h in user]
    fri = gen.users("GeneratedDraft", "FRI")[0]
    assert theme["bigQuestion"] not in fri
    assert not [c for c in theme["candidates"] if c in fri]
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
        mission=lambda n, d: mission_review({"EXAMPLE_COMPLETE": "FAIL"} if d is None else {})
    )
    # 미션 검토 user에는 '오늘(…요일)'이 없어 요일 없이 들어옴 → 다섯 요일 모두 FAIL
    response = run(gen_llm(), review)
    assert response.failure is not None and response.failure.stage == "MISSION"
    assert all(r.split()[1] == "MISSION_REVIEW" for r in response.failure.reasons)
    assert {r.split()[0] for r in response.failure.reasons} == set(DAYS)
    assert review.count("GeneratedStoryReview") == 0


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
