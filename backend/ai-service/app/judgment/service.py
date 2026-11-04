"""판정 흐름: 사전 보류 → LLM 근거 추출 → 원문 대조 → 결과 → 모델 교차 확인 (FN-JDG-03, 04, 05, 10).

보류 판단 순서: TOO_SHORT → UNVERIFIED_SCOPE → INSUFFICIENT_EVIDENCE → QUOTE_MISMATCH
→ MODEL_DISAGREEMENT(M2) · LOW_CONFIDENCE(M1).
앞의 둘은 LLM 호출 전에 확인해 비용을 쓰지 않음. LLM 보류면 scoring을 부르지 않음.
M2·M1 입력이 있으면 LLM은 판정 마감에서 scoring 몫(scoring_reserve)을 뺀 시각까지만 씀 (P12).
scoring 실패는 503으로 바꾸지 않고 LLM 판정만 씀(modelScores.skipped). scoring 장애가
learning의 판정·되묻기 공용 ai 서킷을 열지 않게 하기 위함 (#305, 아키텍처 1.3).
"""

import logging
import time
from typing import Any

from app.clients.scoring_client import ScoringClient, ScoringUnavailable
from app.config import Settings
from app.errors import ApiError
from app.judgment import cross_check, extractor, verifier
from app.judgment.models import (
    CrossCheckSkipped,
    HeldReason,
    JudgmentElement,
    JudgmentRequest,
    JudgmentResponse,
    JudgmentResult,
    M1Observation,
    M2Observation,
    ModelScores,
    RubricElement,
    Versions,
)
from app.llm.base import LlmClient, LlmUnavailable
from app.prompt_versions.registry import ActiveVersions

logger = logging.getLogger(__name__)

MIN_SCORING_SECONDS = 1.0  # 남은 판정 시간이 이보다 짧으면 scoring을 부르지 않고 생략

ScoringBodies = tuple[dict[str, Any] | None, dict[str, Any] | None]  # (M2 본문, M1 본문)


class JudgmentService:
    def __init__(
        self,
        llm: LlmClient,
        settings: Settings,
        versions: ActiveVersions | None = None,
        scoring: ScoringClient | None = None,
    ) -> None:
        self._llm = llm
        self._settings = settings
        self._versions = versions or ActiveVersions()
        # None은 scoring 미연결(단위 테스트). 앱은 bootstrap에서 항상 연결
        self._scoring = scoring

    async def judge(self, request: JudgmentRequest) -> JudgmentResponse:
        deadline = time.monotonic() + self._settings.judge_deadline
        prompt = self._versions.prompt("judgment")
        trial = not all(element.judge_verified for element in request.rubric.elements)
        held = self._held_before_llm(request)
        if held is not None:
            return _held(held, request.versions, trial)

        bodies = self._scoring_bodies(request)
        llm_deadline = deadline - self._settings.scoring_reserve if bodies else deadline
        try:
            extraction = await extractor.extract(self._llm, request, prompt, llm_deadline)
        except LlmUnavailable as exc:
            raise ApiError(503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable) from exc
        versions = request.versions.model_copy(
            update={"model": extraction.model, "prompt": prompt.version}
        )

        evidence: dict[str, extractor.ElementEvidence] = {}
        for item in extraction.data.elements:
            evidence.setdefault(item.element_id, item)
        found = [evidence.get(element.element_id) for element in request.rubric.elements]
        if any(item is None or item.status == "UNCLEAR" for item in found):
            return _held("INSUFFICIENT_EVIDENCE", versions, trial)

        elements = [
            _judge_element(element.element_id, item, request.answer_text)
            for element, item in zip(request.rubric.elements, found, strict=True)
            if item is not None
        ]
        if any(item.quote is not None and not item.verified for item in elements):
            return _held("QUOTE_MISMATCH", versions, trial)

        result = _result(request.rubric.elements, elements)
        scores = await self._model_scores(bodies, result, deadline) if bodies else None
        if scores is not None:
            # 활성 모델이 응답하면 판정 버전은 그 모델, LLM 모델 ID는 사용량 이벤트에만 (#69)
            observed = scores.m2 or scores.m1
            if observed is not None:
                versions = versions.model_copy(update={"model": observed.model.label})
            held = self._held_by_model(scores)
            if held is not None:
                return _held(held, versions, trial, scores)
        return JudgmentResponse(
            result=result,
            elements=elements,
            held_reason=None,
            trial=trial,
            versions=versions,
            model_scores=scores,
        )

    def _scoring_bodies(self, request: JudgmentRequest) -> ScoringBodies | None:
        """scoring에 보낼 M2·M1 본문. scoring 미연결·교차 확인 꺼짐·부를 입력 없음이면 None."""
        if self._scoring is None:
            return None
        m2_body = cross_check.m2_body(request) if self._settings.m2_cross_check_enabled else None
        m1_body = cross_check.m1_body(request) if self._settings.m1_check_enabled else None
        if m2_body is None and m1_body is None:
            return None
        return m2_body, m1_body

    async def _model_scores(
        self, bodies: ScoringBodies, result: JudgmentResult, deadline: float
    ) -> ModelScores | None:
        """M2(서술·논술)·M1(풀이 단계) 활성 결과. 비활성이면 None, 실패면 skipped만 채움."""
        assert self._scoring is not None
        m2_body, m1_body = bodies
        timeout = min(self._settings.scoring_timeout, deadline - time.monotonic())
        try:
            if timeout < MIN_SCORING_SECONDS:
                raise ScoringUnavailable(retryable=True)
            if m2_body is not None:
                m2 = await self._scoring.m2_scores(m2_body, timeout)
                if m2 is None:
                    return None
                average = cross_check.mean(m2.scores)
                return ModelScores(
                    m2=M2Observation(
                        input_type=m2.inputType,
                        scores=m2.scores,
                        raw_scores=m2.rawScores,
                        model=m2.model,
                        mean=average,
                        disagreement=cross_check.disagrees(
                            result, m2.inputType, average, self._settings
                        ),
                    )
                )
            m1 = await self._scoring.m1_check(m1_body or {}, timeout)
        except ScoringUnavailable as exc:
            # 장애·5xx·시간 초과는 UNAVAILABLE, 4xx(입력 한도 초과 등)·계약 밖 응답은 REJECTED
            skipped: CrossCheckSkipped = (
                "SCORING_UNAVAILABLE" if exc.retryable else "SCORING_REJECTED"
            )
            logger.warning("scoring 실패, 교차 확인 생략: skipped=%s", skipped, exc_info=exc)
            return ModelScores(skipped=skipped)
        if m1 is None:
            return None
        return ModelScores(m1=M1Observation(confidence=m1.confidence, model=m1.model))

    def _held_by_model(self, scores: ModelScores) -> HeldReason | None:
        if (
            self._settings.m2_cross_check_enabled
            and scores.m2 is not None
            and scores.m2.disagreement
        ):
            return "MODEL_DISAGREEMENT"
        # 확신도 미만은 보류, 실수 위치는 보이지 않음 (P15)
        if scores.m1 is not None and scores.m1.confidence < self._settings.m1_min_confidence:
            return "LOW_CONFIDENCE"
        return None

    def _held_before_llm(self, request: JudgmentRequest) -> HeldReason | None:
        if verifier.visible_length(request.answer_text) < self._settings.judge_min_answer_length:
            return "TOO_SHORT"
        # 지원 학년이 초3~6(P03)이라 학년 보류는 없음, 미검증 요소만 확인
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
    """state-diagram 3 judgment.result 결정 (요소·배점 기준, FN-JDG-03).

    필수 요소(들어가면 좋은 생각이 아닌 요소)가 모두 충족 → CORRECT,
    충족 요소가 있고 충족 배점이 0보다 큼 → PARTIAL (좋은 생각만 충족해도 PARTIAL),
    충족 요소가 없거나 충족 배점이 0 → RETHINK.
    """
    satisfied = {item.element_id for item in elements if item.satisfied}
    total = sum(element.points for element in rubric)
    earned = sum(element.points for element in rubric if element.element_id in satisfied)
    if not satisfied or (total > 0 and earned == 0):
        return "RETHINK"
    required = [element.element_id for element in rubric if not element.good_thought]
    if all(element_id in satisfied for element_id in required):
        return "CORRECT"
    return "PARTIAL"


def _held(
    reason: HeldReason, versions: Versions, trial: bool, scores: ModelScores | None = None
) -> JudgmentResponse:
    return JudgmentResponse(
        result="HELD",
        elements=[],
        held_reason=reason,
        trial=trial,
        versions=versions,
        model_scores=scores,
    )
