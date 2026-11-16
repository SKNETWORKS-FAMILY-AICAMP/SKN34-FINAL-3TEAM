"""추억 설명 흐름 (#565): 사용량·버전·오류 코드·가짜 구현."""

import asyncio
import logging

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.errors import ApiError
from app.llm.base import LlmError
from app.memory_explanation import checks
from app.memory_explanation.fake import FAKE_MODEL, fake_generated
from app.memory_explanation.models import MemoryExplanationRequest, MemoryExplanationResponse
from app.memory_explanation.prompts import GeneratedMemoryExplanation, GeneratedSentence
from app.memory_explanation.service import MemoryExplanationService
from app.prompt_versions.registry import ActiveVersions
from tests.fakes import FakeLlm

QUERY = "내가 고양이 얘기 썼던 거"
EVIDENCE = [
    {
        "no": 1,
        "themeTitle": "동물 친구들의 집",
        "missionQuestion": "고양이가 살기 좋은 집을 설계해 보세요.",
        "answerExcerpt": "고양이는 높은 곳을 좋아해서 계단을 만들었다. 창문도 달았다.",
        "weekLabel": "10월 둘째 주",
    },
    {
        "no": 2,
        "themeTitle": "사라진 별자리",
        "missionQuestion": "별자리를 찾는 순서를 정해 보세요.",
        "answerExcerpt": "북두칠성부터 찾으면 다른 별도 찾기 쉽다.",
        "weekLabel": "10월 셋째 주",
    },
]
BODY = {"query": QUERY, "evidence": EVIDENCE}
GOOD = GeneratedMemoryExplanation(
    sentences=[
        GeneratedSentence(
            text='「동물 친구들의 집」에서 "고양이는 높은 곳을 좋아해서"라고 썼어요.',
            evidence=[1],
        ),
        GeneratedSentence(text="그래서 고양이 집에 계단을 만들었어요.", evidence=[1]),
    ]
)


def with_second(evidence: list[int], text: str = "나.") -> GeneratedMemoryExplanation:
    return GeneratedMemoryExplanation(
        sentences=[GOOD.sentences[0], GeneratedSentence(text=text, evidence=evidence)]
    )


def run(llm: FakeLlm, body: dict = BODY, **settings: object) -> MemoryExplanationResponse:
    service = MemoryExplanationService(llm, Settings(**settings), ActiveVersions())  # type: ignore[arg-type]
    return asyncio.run(service.explain(MemoryExplanationRequest.model_validate(body)))


def raises(llm: FakeLlm, **settings: object) -> ApiError:
    with pytest.raises(ApiError) as exc:
        run(llm, **settings)
    return exc.value


def test_generates_text_citations_and_versions_with_usage() -> None:
    llm = FakeLlm(GOOD)
    response = run(llm)
    assert response.text == (
        '「동물 친구들의 집」에서 "고양이는 높은 곳을 좋아해서"라고 썼어요[1]. '
        "그래서 고양이 집에 계단을 만들었어요[1]."
    )
    assert response.citations == [1]
    assert (response.versions.model, response.versions.prompt) == (
        "fake-model",
        "memory-explanation@1",
    )
    [request] = llm.requests
    assert (request.call_type, request.prompt_version) == (
        "MEMORY_EXPLANATION",
        "memory-explanation@1",
    )
    assert "[근거 2]" in request.user and QUERY in request.user
    [usage] = llm.usages
    assert (usage.call_type, usage.success) == ("MEMORY_EXPLANATION", True)


def test_ids_in_request_are_rejected_before_llm() -> None:
    for body in (
        {**BODY, "studentId": "s"},
        {**BODY, "evidence": [{**EVIDENCE[0], "attemptId": "a"}]},
    ):
        with pytest.raises(ValidationError):
            MemoryExplanationRequest.model_validate(body)


def test_out_of_range_or_empty_citation_is_422() -> None:
    for evidence in ([3], []):
        error = raises(FakeLlm(with_second(evidence)))
        assert (error.status, error.code, error.extra["retryable"]) == (
            422,
            "AI_EXPLANATION_REJECTED",
            False,
        )


def test_wrong_shape_is_502() -> None:
    one = GeneratedMemoryExplanation(sentences=GOOD.sentences[:1])
    error = raises(FakeLlm(one))
    assert (error.status, error.code, error.extra["retryable"]) == (502, "AI_BAD_RESPONSE", True)
    invalid = LlmError("LLM_INVALID_OUTPUT", retryable=True)
    llm = FakeLlm(invalid, invalid, max_retries=1)
    error = raises(llm)
    assert (error.status, error.code) == (502, "AI_BAD_RESPONSE")
    assert [u.error_code for u in llm.usages] == ["LLM_INVALID_OUTPUT"] * 2


def test_llm_failure_is_503_after_one_retry() -> None:
    timeout = LlmError("LLM_TIMEOUT", retryable=True)
    llm = FakeLlm(timeout, timeout, max_retries=1)
    error = raises(llm)
    assert (error.status, error.code, error.extra["retryable"]) == (503, "AI_UNAVAILABLE", True)
    assert len(llm.requests) == 2
    auth = raises(FakeLlm(LlmError("LLM_AUTH_FAILED", retryable=False)))
    assert (auth.status, auth.extra["retryable"]) == (503, False)


def test_logs_have_no_raw_text(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        raises(FakeLlm(with_second([2], '"없는 말"이에요.')))
    assert "QUOTE_NOT_IN_EVIDENCE" in caplog.text
    for raw in (QUERY, "없는 말", "고양이", "북두칠성"):
        assert raw not in caplog.text


def test_fake_provider_skips_llm_and_passes_checks() -> None:
    llm = FakeLlm()
    response = run(llm, memory_explanation_provider="fake")
    assert llm.requests == [] and llm.usages == []
    assert response.text == (
        '10월 둘째 주 「동물 친구들의 집」에서 "고양이는 높은 곳을 좋아해서 계단을 만들었다"'
        "라고 답했어요[1]. "
        '10월 셋째 주 「사라진 별자리」에서 "북두칠성부터 찾으면 다른 별도 찾기 쉽다"'
        "라고 답했어요[2]."
    )
    assert response.citations == [1, 2]
    assert response.versions.model == FAKE_MODEL


@pytest.mark.parametrize(
    "excerpt", ["짧은 답", '"따옴표로 시작한 답"이다', "...", "가" * 100, "첫 줄\n둘째 줄"]
)
def test_fake_always_passes_checks_with_one_evidence(excerpt: str) -> None:
    request = MemoryExplanationRequest.model_validate(
        {"query": "q", "evidence": [{**EVIDENCE[0], "no": 3, "answerExcerpt": excerpt}]}
    )
    generated = fake_generated(request)
    assert len(generated.sentences) == 2
    assert checks.check(generated.sentences, request.evidence) is None
    assert checks.compose(generated.sentences).citations == [3]
