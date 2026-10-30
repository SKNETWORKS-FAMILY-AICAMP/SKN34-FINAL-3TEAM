import asyncio
from typing import Any

import pytest

from app.config import Settings
from app.errors import ApiError
from app.llm.base import LlmError
from app.report_narrative import prompts
from app.report_narrative.models import NarrativeRequest
from app.report_narrative.prompts import CitedQuote, GeneratedNarrative
from app.report_narrative.service import NarrativeService
from tests.fakes import FakeLlm

PERIOD = {"from": "2026-11-02", "to": "2026-11-08"}
BODY: dict[str, Any] = {
    "metrics": [
        {
            "label": "되묻기 후 생각을 더한 비율",
            "value": 0.6,
            "count": 3,
            "numerator": 3,
            "denominator": 5,
            "formula": "보완 답변 제출 시도 수 / 되묻기 받은 시도 수",
            "period": PERIOD,
            "sourceType": "RECORD",
            "state": "OK",
        },
        {
            "label": "완료한 미션 수",
            "value": None,
            "count": 2,
            "numerator": 2,
            "denominator": 2,
            "formula": "완료 시도 수",
            "period": PERIOD,
            "sourceType": "RECORD",
            "state": "INSUFFICIENT_SAMPLE",
        },
    ],
    "thinkingTypes": [
        {
            "type": "ANALYZE",
            "state": "OK",
            "missions": [{"attemptId": "t-7", "title": "쉬는 시간"}],
        },
        {"type": "CREATE", "state": "NO_RECORD"},
    ],
    "changes": [
        {
            "attemptId": "t-7",
            "followup": "왜 그렇게 생각했어?",
            "first": {"answerId": "a-101", "text": "늘리면 좋아."},
            "revised": {"answerId": "a-102", "text": "늘리면 좋아. 왜냐하면 친구와 놀 수 있어."},
            "counts": {"chars": [6, 22], "sentences": [1, 2], "reasonConnectives": [0, 1]},
        }
    ],
    "reflections": [
        {
            "attemptId": "t-7",
            "difficulty": "NORMAL",
            "text": "까닭 쓰기가 어려웠어",
            "written": True,
        },
        {"attemptId": "t-8", "difficulty": None, "text": None, "written": False},
    ],
    "quotes": [
        {
            "attemptId": "t-7",
            "answerId": "a-102",
            "answerVersion": 2,
            "text": "늘리면 좋아. 왜냐하면 친구와 놀 수 있어.",
            "verified": False,  # report가 대조 전 값으로 보냄, 무시
        },
        {"attemptId": "t-9", "answerId": "a-201", "answerVersion": 1, "text": "나는 반대야."},
    ],
}


def generated(
    cited: list[tuple[int, str]], narrative: str = "이번 주 아이는 ...", question: str = "어땠어?"
):
    return GeneratedNarrative(
        narrative=narrative,
        evening_question=question,
        cited_quotes=[CitedQuote(candidate=n, quote=quote) for n, quote in cited],
    )


def generate(llm: FakeLlm, body: dict[str, Any] = BODY):
    service = NarrativeService(llm, Settings(internal_token="t"))
    return asyncio.run(service.generate(NarrativeRequest.model_validate(body)))


def test_response_has_llm_narrative_and_versions() -> None:
    response = generate(FakeLlm(generated([], narrative=" 서술 ", question=" 질문? ")))
    assert response.model_dump(by_alias=True) == {
        "narrative": {"text": "서술", "source": "LLM", "modelExplanation": None},
        "eveningQuestion": "질문?",
        "citedQuotes": [],
        "versions": {"model": "fake-model", "prompt": "report@1"},
    }


def test_cited_quotes_come_from_input_only() -> None:
    # 범위 밖 번호(0·3), 다른 후보의 구절, 원문에 없는 구절은 버리고 중복은 한 번만
    response = generate(
        FakeLlm(
            generated(
                [
                    (1, "왜냐하면 친구와 놀 수 있어."),
                    (3, "왜냐하면 친구와 놀 수 있어."),
                    (0, "늘리면 좋아."),
                    (2, "늘리면 좋아."),
                    (1, "만든 적 없는 인용"),
                    (1, ""),
                    (1, "왜냐하면 친구와 놀 수 있어."),
                    (2, "나는 반대야."),
                ]
            )
        )
    )
    assert [quote.model_dump(by_alias=True) for quote in response.cited_quotes] == [
        {
            "attemptId": "t-7",
            "answerId": "a-102",
            "answerVersion": 2,
            "quote": "왜냐하면 친구와 놀 수 있어.",
        },
        {"attemptId": "t-9", "answerId": "a-201", "answerVersion": 1, "quote": "나는 반대야."},
    ]


def test_usage_call_type_is_report_narrative() -> None:
    llm = FakeLlm(generated([]))
    generate(llm)
    assert [(usage.call_type, usage.prompt_version) for usage in llm.usages] == [
        ("REPORT_NARRATIVE", "report@1")
    ]


def test_prompt_has_input_values_without_record_ids() -> None:
    user = prompts.build_user(NarrativeRequest.model_validate(BODY))
    assert "3/5, 개수 3, 비율 60%" in user
    assert "완료한 미션 수: 2/2, 개수 2 (" in user  # 분모 5 미만은 비율 없음
    assert "새로 만들기: 확인된 기록 없음" in user
    assert "글자 수 [6, 22], 문장 수 [1, 2], 까닭을 잇는 말 수 [0, 1]" in user
    assert "어려움 보통: 까닭 쓰기가 어려웠어" in user
    assert "- 쓰지 않음" in user
    assert "1. 늘리면 좋아. 왜냐하면 친구와 놀 수 있어." in user
    for record_id in ("t-7", "t-8", "t-9", "a-101", "a-102", "a-201"):
        assert record_id not in user


def test_empty_inputs_are_marked_none() -> None:
    body = {key: [] for key in BODY}
    user = prompts.build_user(NarrativeRequest.model_validate(body))
    assert user.count("- 없음") == 5


def test_llm_failure_is_503() -> None:
    with pytest.raises(ApiError) as caught:
        generate(FakeLlm(LlmError("LLM_SERVER_ERROR", retryable=True)))
    assert (caught.value.status, caught.value.code) == (503, "AI_UNAVAILABLE")


def test_empty_narrative_is_503() -> None:
    with pytest.raises(ApiError) as caught:
        generate(FakeLlm(generated([], narrative="  ")))
    assert (caught.value.status, caught.value.code) == (503, "AI_UNAVAILABLE")
