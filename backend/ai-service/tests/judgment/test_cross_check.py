"""#69 M2·M1 교차 확인 분기, #305 실패 시 생략 (api-spec 4.2.2). scoring은 대역으로 대체."""

import asyncio
import time
from typing import Any

import pytest

from app.clients.scoring_client import M1Check, M2Scores, ScoringUnavailable
from app.config import Settings
from app.judgment import service as judgment_service
from app.judgment.extractor import Extraction
from app.judgment.models import JudgmentRequest, M2Preparation
from app.judgment.service import JudgmentService
from app.llm.base import LlmError
from tests.fakes import FakeLlm

SHORT_ANSWER = "나는 찬성해. 왜냐하면 쉬는 시간이 길면 더 잘 놀 수 있기 때문이야."
# 교차 확인 글자 수 하한(서술 100·논술 140, 공백 제외)을 넘는 답. 공백 뺀 154자
ANSWER = (
    SHORT_ANSWER
    + " 친구들과 운동장에서 줄넘기도 하고 술래잡기도 할 수 있어서 몸이 튼튼해진다고 생각해."
    " 또 쉬는 시간에 충분히 쉬고 나면 다음 수업 시간에 더 집중할 수 있어."
    " 반대하는 친구는 공부할 시간이 줄어든다고 말하지만 잘 쉬어야 공부도 잘된다고 생각해."
    " 그래서 나는 쉬는 시간을 지금보다 조금 더 늘리면 좋겠어."
)
NARRATIVE_KEYS = (
    "hol",
    "task_1",
    "content_1",
    "content_2",
    "content_3",
    "organization_1",
    "organization_2",
    "expression_1",
    "expression_2",
)
MODEL = {"name": "m2-klue-narrative", "version": "3.0", "revision": 2}


class FakeScoring:
    """정해 둔 응답(None = {active:false})이나 실패를 돌려주고 받은 본문·timeout을 기록."""

    def __init__(self, m2: Any = None, m1: Any = None) -> None:
        self._m2, self._m1 = m2, m1
        self.calls: list[tuple[str, dict[str, Any], float]] = []

    async def m2_scores(self, body: dict[str, Any], timeout: float) -> M2Scores | None:
        self.calls.append(("m2", body, timeout))
        if isinstance(self._m2, Exception):
            raise self._m2
        return self._m2

    async def m1_check(self, body: dict[str, Any], timeout: float) -> M1Check | None:
        self.calls.append(("m1", body, timeout))
        if isinstance(self._m1, Exception):
            raise self._m1
        return self._m1


def narrative(score: int) -> M2Scores:
    return M2Scores.model_validate(
        {
            "active": True,
            "inputType": "NARRATIVE",
            "scores": dict.fromkeys(NARRATIVE_KEYS, score),
            "rawScores": dict.fromkeys(NARRATIVE_KEYS, score + 0.25),
            "model": MODEL,
        }
    )


def essay(score: int) -> M2Scores:
    return M2Scores.model_validate(
        {
            "active": True,
            "inputType": "ESSAY",
            "scores": dict.fromkeys(("org", "cont", "exp"), score),
            "rawScores": dict.fromkeys(("org", "cont", "exp"), float(score)),
            "model": {"name": "m2-klue-essay", "version": "3.1", "revision": 1},
        }
    )


def with_chars(scores: M2Scores, chars: int) -> M2Scores:
    """scoring이 정리한 글의 공백 뺀 글자 수를 붙인 응답."""
    preparation = M2Preparation(
        copied=0, repeated=False, chars=chars, labels_removed=0, short=False
    )
    return scores.model_copy(update={"preparation": preparation})


def make_request(**overrides: Any) -> JudgmentRequest:
    body: dict[str, Any] = {
        "answerText": ANSWER,
        "inputType": "NARRATIVE",
        "grade": 5,
        "rubric": {
            "elements": [
                {"elementId": "e1", "label": "주장", "points": 1, "judgeVerified": True},
                {"elementId": "e2", "label": "까닭", "points": 2, "judgeVerified": True},
            ]
        },
        "versions": {"mission": "m-12@3", "rubric": "r-12@2"},
        "question": "쉬는 시간을 늘리는 것에 찬성하나요?",
        "keywords": ["쉬는 시간", "놀이(놀기)"],
    }
    body.update(overrides)
    return JudgmentRequest.model_validate(body)


def both_extraction() -> Extraction:
    return Extraction.model_validate(
        {
            "elements": [
                {"elementId": "e1", "status": "FOUND", "quote": "나는 찬성해"},
                {
                    "elementId": "e2",
                    "status": "FOUND",
                    "quote": "쉬는 시간이 길면 더 잘 놀 수 있기 때문이야",
                },
            ]
        }
    )


def found_both() -> FakeLlm:
    return FakeLlm(both_extraction())


def found_none() -> FakeLlm:
    return FakeLlm(
        Extraction.model_validate(
            {
                "elements": [
                    {"elementId": "e1", "status": "NOT_FOUND", "quote": None},
                    {"elementId": "e2", "status": "NOT_FOUND", "quote": None},
                ]
            }
        )
    )


def judge(
    scoring: FakeScoring,
    request: JudgmentRequest | None = None,
    llm: FakeLlm | None = None,
    **settings: Any,
):
    """M2 교차 확인은 켠 상태가 기본. 꺼진 경우는 m2_cross_check_enabled=False로 명시."""
    settings = {"m2_cross_check_enabled": True} | settings
    service = JudgmentService(
        llm or found_both(), Settings(internal_token="t", **settings), scoring=scoring
    )
    return asyncio.run(service.judge(request or make_request()))


def test_m2_inactive_keeps_llm_judgment() -> None:
    scoring = FakeScoring(m2=None)
    response = judge(scoring, m2_cross_check_enabled=True)
    assert response.result == "CORRECT"
    assert response.model_scores is None
    assert response.versions.model == "fake-model"
    [(kind, body, _)] = scoring.calls
    assert kind == "m2"
    assert body == {
        "prompt": "쉬는 시간을 늘리는 것에 찬성하나요?",
        "text": ANSWER,
        "grade": 5,
        "inputType": "NARRATIVE",
        "keywords": ["쉬는 시간", "놀이(놀기)"],
    }


def test_m2_agreement_records_scores_and_model_version() -> None:
    response = judge(FakeScoring(m2=narrative(4)), m2_cross_check_enabled=True)
    assert response.result == "CORRECT"
    assert response.held_reason is None
    assert response.versions.model == "m2-klue-narrative@3.0"
    assert response.model_scores.skipped is None
    m2 = response.model_scores.m2
    assert (m2.mean, m2.disagreement) == (4.0, False)
    assert m2.raw_scores["content_3"] == 4.25


def test_m2_disagreement_holds_when_enabled() -> None:
    response = judge(FakeScoring(m2=narrative(2)), m2_cross_check_enabled=True)
    assert response.result == "HELD"
    assert response.held_reason == "MODEL_DISAGREEMENT"
    assert response.elements == []
    assert response.model_scores.m2.disagreement is True
    assert response.versions.model == "m2-klue-narrative@3.0"


def test_m2_is_not_called_when_cross_check_disabled() -> None:
    # 기본값(꺼짐)이면 scoring을 부르지 않아 scoring 장애와 무관 (#305)
    llm = found_both()
    scoring = FakeScoring(m2=ScoringUnavailable(retryable=True))
    service = JudgmentService(llm, Settings(internal_token="t"), scoring=scoring)
    response = asyncio.run(service.judge(make_request()))
    assert scoring.calls == []
    assert response.result == "CORRECT"
    assert response.model_scores is None
    assert response.versions.model == "fake-model"


def test_m2_cross_check_disabled_lets_llm_use_whole_deadline() -> None:
    llm = found_both()
    judge(
        FakeScoring(m2=narrative(4)),
        llm=llm,
        m2_cross_check_enabled=False,
        judge_deadline=10.0,
        scoring_reserve=3.0,
    )
    assert 9.5 < llm.requests[0].timeout <= 10.0


def test_rethink_with_high_essay_score_is_kept_by_default() -> None:
    # 논술 RETHINK 쪽은 기본 꺼짐: AI Hub 기준 못 쓴 글 판정을 너무 많이 보류 (ai.md 4.3)
    request = make_request(inputType="ESSAY", keywords=[], essayType="주장")
    scoring = FakeScoring(m2=essay(3))
    response = judge(scoring, request, llm=found_none(), m2_cross_check_enabled=True)
    assert response.result == "RETHINK"
    assert response.held_reason is None
    assert response.model_scores.m2.disagreement is False
    assert scoring.calls[0][1]["essayType"] == "주장"
    assert "keywords" not in scoring.calls[0][1]


def test_rethink_with_high_essay_score_disagrees_when_enabled() -> None:
    request = make_request(inputType="ESSAY", keywords=[], essayType="주장")
    response = judge(
        FakeScoring(m2=essay(3)), request, llm=found_none(), m2_essay_high_enabled=True
    )
    assert response.held_reason == "MODEL_DISAGREEMENT"


def test_correct_with_low_essay_score_disagrees() -> None:
    request = make_request(inputType="ESSAY", keywords=[], essayType="주장")
    response = judge(FakeScoring(m2=essay(1)), request)
    assert response.held_reason == "MODEL_DISAGREEMENT"


def test_rethink_with_high_narrative_score_disagrees() -> None:
    response = judge(FakeScoring(m2=narrative(4)), llm=found_none())
    assert response.held_reason == "MODEL_DISAGREEMENT"


@pytest.mark.parametrize(
    ("input_type", "scores", "chars", "held"),
    [
        ("NARRATIVE", narrative(2), 99, False),
        ("NARRATIVE", narrative(2), 100, True),
        ("ESSAY", essay(0), 139, False),
        ("ESSAY", essay(0), 140, True),
    ],
)
def test_short_cleaned_answer_is_not_held(input_type, scores, chars, held) -> None:
    # 정리 뒤 글자 수가 하한보다 짧으면 경계를 쓸 근거가 없어 점수만 기록
    overrides = {"inputType": "ESSAY", "essayType": "주장"} if input_type == "ESSAY" else {}
    response = judge(FakeScoring(m2=with_chars(scores, chars)), make_request(**overrides))
    assert (response.held_reason == "MODEL_DISAGREEMENT") is held
    assert response.model_scores.m2.disagreement is held
    assert response.model_scores.m2_preparation.chars == chars


def test_short_answer_without_preparation_uses_answer_length() -> None:
    response = judge(FakeScoring(m2=narrative(2)), make_request(answerText=SHORT_ANSWER))
    assert response.result == "CORRECT"
    assert response.held_reason is None
    assert response.model_scores.m2.disagreement is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"keywords": []},
        {"keywords": ["  "]},
        {"question": None},
        {"inputType": "ESSAY", "essayType": None},
    ],
)
def test_m2_is_not_called_without_inputs(overrides: dict[str, Any]) -> None:
    scoring = FakeScoring(m2=narrative(1))
    response = judge(scoring, make_request(**overrides), m2_cross_check_enabled=True)
    assert scoring.calls == []
    assert response.result == "CORRECT"
    assert response.model_scores is None


def test_llm_hold_skips_scoring() -> None:
    scoring = FakeScoring(m2=narrative(1))
    response = judge(scoring, make_request(answerText="짧아"))
    assert response.held_reason == "TOO_SHORT"
    assert scoring.calls == []


@pytest.mark.parametrize(
    ("retryable", "skipped"),
    [(True, "SCORING_UNAVAILABLE"), (False, "SCORING_REJECTED")],
)
@pytest.mark.parametrize("llm", [found_both, found_none])
def test_scoring_failure_skips_cross_check(retryable: bool, skipped: str, llm) -> None:
    # 장애·5xx·시간 초과(retryable) / 400·계약 밖 응답 모두 503 없이 LLM 판정만 씀 (#305)
    response = judge(FakeScoring(m2=ScoringUnavailable(retryable=retryable)), llm=llm())
    assert response.result == ("CORRECT" if llm is found_both else "RETHINK")
    assert response.held_reason is None
    assert response.elements
    assert response.versions.model == "fake-model"
    assert response.model_scores.model_dump(by_alias=True) == {
        "m2": None,
        "m1": None,
        "skipped": skipped,
    }


def test_m1_failure_skips_cross_check() -> None:
    scoring = FakeScoring(m1=ScoringUnavailable(retryable=True))
    response = judge(scoring, solution_request(), m1_check_enabled=True)
    assert response.result == "CORRECT"
    assert response.model_scores.skipped == "SCORING_UNAVAILABLE"


def test_scoring_timeout_uses_remaining_deadline() -> None:
    scoring = FakeScoring(m2=None)
    judge(scoring, judge_deadline=5.0, scoring_timeout=10.0)
    assert scoring.calls[0][2] <= 5.0


def test_exhausted_deadline_skips_without_calling_scoring() -> None:
    scoring = FakeScoring(m2=narrative(4))
    response = judge(scoring, judge_deadline=0.5, scoring_reserve=0)
    assert response.result == "CORRECT"
    assert response.model_scores.skipped == "SCORING_UNAVAILABLE"
    assert scoring.calls == []


def test_llm_deadline_leaves_scoring_reserve() -> None:
    llm = found_both()
    judge(FakeScoring(m2=None), llm=llm, judge_deadline=10.0, scoring_reserve=3.0)
    # LLM 1회 15초보다 (판정 마감 - scoring 몫)이 짧아 그 시각까지만 씀
    assert 6.5 < llm.requests[0].timeout <= 7.0


def test_llm_uses_whole_deadline_without_cross_check_inputs() -> None:
    llm = found_both()
    scoring = FakeScoring(m2=narrative(4))
    judge(scoring, make_request(keywords=[]), llm=llm, judge_deadline=10.0, scoring_reserve=3.0)
    assert scoring.calls == []
    assert 9.5 < llm.requests[0].timeout <= 10.0


class SlowScoring(FakeScoring):
    """받은 timeout을 거의 다 쓰고 응답하는 scoring (첫 요청 지연 등 최악 대역)."""

    async def m2_scores(self, body: dict[str, Any], timeout: float) -> M2Scores | None:
        await asyncio.sleep(timeout * 0.9)
        return await super().m2_scores(body, timeout)


def test_llm_retry_worst_path_still_leaves_scoring_reserve(monkeypatch) -> None:
    # 실제 설정(LLM 15초·대기 1초·마감 33초·scoring 몫 3초·최소 1초)을 1/10로 줄여 실제 시간 확인
    monkeypatch.setattr(judgment_service, "MIN_SCORING_SECONDS", 0.1)
    llm = FakeLlm(
        LlmError("LLM_TIMEOUT", retryable=True),
        both_extraction(),
        max_retries=1,
        timeout=1.5,
        backoff_seconds=0.1,
        hang=True,  # 첫 시도는 1.5초를 다 쓰고 시간 초과
        delay=1.3,  # 재시도는 줄어든 마감(약 1.4초) 직전에 응답
    )
    scoring = SlowScoring(m2=narrative(4))
    started = time.monotonic()
    response = judge(scoring, llm=llm, judge_deadline=3.3, scoring_reserve=0.3, scoring_timeout=1.0)
    elapsed = time.monotonic() - started
    assert response.result == "CORRECT"
    assert response.model_scores.m2 is not None
    first, second = llm.requests
    assert first.timeout == 1.5
    assert second.timeout <= 3.3 - 0.3 - 1.6 + 0.05  # 재시도는 scoring 몫 앞에서 끊김
    [(_, _, scoring_timeout)] = scoring.calls
    assert scoring_timeout >= 0.3  # LLM이 마감까지 써도 scoring 몫은 남음
    assert elapsed < 3.3


def solution_request(**overrides: Any) -> JudgmentRequest:
    body: dict[str, Any] = {
        "inputType": "SOLUTION_STEPS",
        "keywords": [],
        "answerKey": "12",
        "solution": {"steps": ["3 x 4 = 12"], "finalAnswer": "12"},
    }
    return make_request(**(body | overrides))


def m1(confidence: float) -> M1Check:
    return M1Check.model_validate(
        {
            "active": True,
            "confidence": confidence,
            "model": {"name": "m1-math", "version": "0.1", "revision": 1},
        }
    )


def test_m1_is_off_by_default() -> None:
    scoring = FakeScoring(m1=m1(0.1))
    response = judge(scoring, solution_request())
    assert scoring.calls == []
    assert response.result == "CORRECT"


def test_m1_inactive_keeps_llm_judgment() -> None:
    scoring = FakeScoring(m1=None)
    response = judge(scoring, solution_request(), m1_check_enabled=True)
    assert response.result == "CORRECT"
    assert scoring.calls[0][:2] == (
        "m1",
        {
            "problem": "쉬는 시간을 늘리는 것에 찬성하나요?",
            "answerKey": "12",
            "solution": {"steps": ["3 x 4 = 12"], "finalAnswer": "12"},
        },
    )


def test_m1_low_confidence_holds() -> None:
    response = judge(FakeScoring(m1=m1(0.79)), solution_request(), m1_check_enabled=True)
    assert response.held_reason == "LOW_CONFIDENCE"
    assert response.elements == []
    assert response.versions.model == "m1-math@0.1"


def test_m1_confident_keeps_result() -> None:
    response = judge(FakeScoring(m1=m1(0.8)), solution_request(), m1_check_enabled=True)
    assert response.result == "CORRECT"
    assert response.model_scores.m1.confidence == 0.8


def test_m1_needs_answer_key_and_solution() -> None:
    scoring = FakeScoring(m1=m1(0.1))
    judge(scoring, solution_request(answerKey=None), m1_check_enabled=True)
    assert scoring.calls == []
