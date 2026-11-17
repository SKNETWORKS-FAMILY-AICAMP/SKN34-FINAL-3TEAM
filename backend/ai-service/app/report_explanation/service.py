"""리포트 상세 설명 흐름 (FN-RPT-09, api-spec 4.2.3, #477, @2 로컬 Gemma 상세 설명).

1. 설명 모델(레지스트리 MODEL report-explanation)이 explanation/grade-{학년}/{입력 유형}에
   활성이 아니면 {active:false}
2. 답변 1개에 설명 전용 sLLM(Gemma LoRA) 호출(JSON 세 칸, 중복 접수 없이 1회 호출,
   사용량 REPORT_EXPLANATION)
3. 문장 단위 정리(checks.clean) → 규칙 검사 → "상세 분석 / 보완할 지점 / 개선 방안" 조립 → 인용

로컬 전용: 환경변수 EXPLANATION_LOCAL_SKIP_REGISTRY=1이면 1의 레지스트리 확인을 건너뛰고
바로 부른다(로컬 Docker 시연용, 2026-11-17 사용자 결정).
기본은 꺼짐이며 운영에서는 레지스트리 승인 검사를 유지한다.
이때 versions.model은 "{REPORT_GEMMA_MODEL 설정값}@local-unregistered"로
남겨 승인 모델과 구분한다.

LLM 실패·미설정·마감 초과는 503 AI_UNAVAILABLE, 검사 실패는 422 AI_EXPLANATION_REJECTED.
어느 쪽이든 report는 그 설명만 빼고 "설명 미포함"으로 둠 (P16).
"""

import logging
import os
import time

from app.config import Settings
from app.errors import ApiError
from app.followup.models import LlmVersions
from app.llm.base import LlmClient, LlmUnavailable
from app.prompt_versions.models import EXPLANATION_MODEL
from app.prompt_versions.registry import ActiveVersions
from app.report_explanation import checks
from app.report_explanation.models import (
    ActiveExplanationResponse,
    Explanation,
    ExplanationDetail,
    ExplanationRequest,
    ExplanationResponse,
    InactiveExplanationResponse,
)

logger = logging.getLogger(__name__)
LOCAL_SKIP_REGISTRY = "EXPLANATION_LOCAL_SKIP_REGISTRY"


def skip_registry() -> bool:
    return os.environ.get(LOCAL_SKIP_REGISTRY) == "1"


def explanation_scope(request: ExplanationRequest) -> str:
    return f"explanation/grade-{request.grade}/{request.input_type.lower()}"


class ExplanationService:
    def __init__(self, llm: LlmClient, settings: Settings, versions: ActiveVersions) -> None:
        self._llm = llm
        self._settings = settings
        self._versions = versions

    async def explain(self, request: ExplanationRequest) -> ExplanationResponse:
        if skip_registry():
            model_label = f"{self._settings.report_gemma_model}@local-unregistered"
        else:
            model = self._versions.model(EXPLANATION_MODEL, explanation_scope(request))
            if model is None:
                return InactiveExplanationResponse()
            model_label = f"{model.name}@{model.version}"
        prompt = self._versions.prompt("reportExplanation")
        try:
            result = await self._llm.generate(
                system=prompt.body.SYSTEM,
                user=prompt.body.build_user(request.grade, request.topic, request.text),
                output=ExplanationDetail,
                call_type="REPORT_EXPLANATION",
                prompt_version=prompt.version,
                max_tokens=self._settings.explanation_max_tokens,
                deadline=time.monotonic() + self._settings.explanation_deadline,
                # A serverless job is never resubmitted within this request.
                max_retries=0,
            )
        except LlmUnavailable as exc:
            raise ApiError(503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable) from exc
        sections = checks.parts(result.data, request.text)
        if not sections or sections[0][0] != "상세 분석":
            raise rejected()
        if not all(checks.allowed(body, request.text) for _, body in sections):
            logger.warning("리포트 상세 설명 검사 실패")
            raise rejected()
        text = checks.compose(sections)
        quote = checks.pick_quote(request.text, " ".join(body for _, body in sections[:2]))
        return ActiveExplanationResponse(
            explanation=Explanation(text=text, quote=quote),
            versions=LlmVersions(model=model_label, prompt=prompt.version),
        )


def rejected() -> ApiError:
    return ApiError(422, "AI_EXPLANATION_REJECTED", "설명 검사 실패", retryable=False)
