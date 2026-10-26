"""판정 흐름: 사전 보류 → LLM 근거 추출 → 원문 대조 → 결과 (FN-JDG-03, 04, 10).

보류 판단 순서: TOO_SHORT → UNVERIFIED_SCOPE → INSUFFICIENT_EVIDENCE → QUOTE_MISMATCH.
앞의 둘은 LLM 호출 전에 확인해 비용을 쓰지 않음.
"""

from app.config import Settings
from app.errors import ApiError
from app.judgment import extractor, prompts, verifier
from app.judgment.models import (
    HeldReason,
    JudgmentElement,
    JudgmentRequest,
    JudgmentResponse,
    JudgmentResult,
    RubricElement,
    Versions,
)
from app.llm.base import LlmClient, LlmUnavailable

LOWER_GRADES = 2  # 초1~2 서술은 판정 보류 (FN-JDG-04)


class JudgmentService:
    def __init__(self, llm: LlmClient, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings

    async def judge(self, request: JudgmentRequest) -> JudgmentResponse:
        held = self._held_before_llm(request)
        if held is not None:
            return _held(held, request.versions)

        try:
            extraction = await extractor.extract(self._llm, request)
        except LlmUnavailable as exc:
            raise ApiError(503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable) from exc
        versions = request.versions.model_copy(
            update={"model": extraction.model, "prompt": prompts.PROMPT_VERSION}
        )

        evidence: dict[str, extractor.ElementEvidence] = {}
        for item in extraction.data.elements:
            evidence.setdefault(item.element_id, item)
        found = [evidence.get(element.element_id) for element in request.rubric.elements]
        if any(item is None or item.status == "UNCLEAR" for item in found):
            return _held("INSUFFICIENT_EVIDENCE", versions)

        elements = [
            _judge_element(element.element_id, item, request.answer_text)
            for element, item in zip(request.rubric.elements, found, strict=True)
            if item is not None
        ]
        if any(item.quote is not None and not item.verified for item in elements):
            return _held("QUOTE_MISMATCH", versions)

        return JudgmentResponse(
            result=_result(request.rubric.elements, elements),
            elements=elements,
            held_reason=None,
            versions=versions,
        )

    def _held_before_llm(self, request: JudgmentRequest) -> HeldReason | None:
        if verifier.visible_length(request.answer_text) < self._settings.judge_min_answer_length:
            return "TOO_SHORT"
        if request.grade <= LOWER_GRADES:
            return "UNVERIFIED_SCOPE"
        if self._settings.judge_require_verified and not all(
            element.judge_verified for element in request.rubric.elements
        ):
            return "UNVERIFIED_SCOPE"
        return None


def _judge_element(
    element_id: str, item: extractor.ElementEvidence, answer_text: str
) -> JudgmentElement:
    if item.status != "FOUND":
        return JudgmentElement(element_id=element_id, quote=None, verified=False, satisfied=False)
    # FOUND인데 구절이 비어 있으면 빈 문자열로 두어 인용 불일치로 처리
    quote = item.quote or ""
    verified = verifier.is_verbatim(quote, answer_text)
    # 원문에서 확인되지 않은 요소는 충족으로 표시하지 않음 (FN-JDG-03)
    return JudgmentElement(
        element_id=element_id, quote=quote, verified=verified, satisfied=verified
    )


def _result(rubric: list[RubricElement], elements: list[JudgmentElement]) -> JudgmentResult:
    """충족 배점 합 = 총점 → CORRECT, 0 초과 → PARTIAL, 0 → RETHINK.

    총점이 0이면 배점 대신 충족 요소 수로 계산.
    """
    satisfied = {item.element_id for item in elements if item.satisfied}
    total = sum(element.points for element in rubric)
    if total > 0:
        earned, full = sum(e.points for e in rubric if e.element_id in satisfied), total
    else:
        earned, full = len(satisfied), len(rubric)
    if earned == full:
        return "CORRECT"
    return "PARTIAL" if earned > 0 else "RETHINK"


def _held(reason: HeldReason, versions: Versions) -> JudgmentResponse:
    return JudgmentResponse(result="HELD", elements=[], held_reason=reason, versions=versions)
