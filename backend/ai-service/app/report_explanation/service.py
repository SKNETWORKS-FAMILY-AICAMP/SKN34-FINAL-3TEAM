"""리포트 설명 흐름 (FN-RPT-09, api-spec 4.2.3, #477).

1. 설명 모델(레지스트리 MODEL report-explanation)이 explanation/grade-{학년}/{입력 유형}에
   활성이 아니면 {active:false}
2. 항목 최대 2개를 골라 항목마다 설명 전용 sLLM 1회(평문, 재시도 없음, 사용량 REPORT_EXPLANATION)
3. 규칙 후처리·검사 → 학부모 문장 틀 → 인용 구절

LLM 실패·미설정·마감 초과는 503 AI_UNAVAILABLE, 후처리 뒤 남는 문장이 없거나 검사 실패는
422 AI_EXPLANATION_REJECTED. 어느 쪽이든 report는 그 설명만 빼고 "설명 미포함"으로 둠 (P16).
"""

import logging
import time

from app.config import Settings
from app.errors import ApiError
from app.followup.models import LlmVersions
from app.llm.base import LlmClient, LlmUnavailable
from app.prompt_versions.models import EXPLANATION_MODEL, PromptChoice
from app.prompt_versions.registry import ActiveVersions
from app.report_explanation import checks
from app.report_explanation.models import (
    ActiveExplanationResponse,
    Explanation,
    ExplanationRequest,
    ExplanationResponse,
    InactiveExplanationResponse,
)

logger = logging.getLogger(__name__)


def explanation_scope(request: ExplanationRequest) -> str:
    return f"explanation/grade-{request.grade}/{request.input_type.lower()}"


class ExplanationService:
    def __init__(self, llm: LlmClient, settings: Settings, versions: ActiveVersions) -> None:
        self._llm = llm
        self._settings = settings
        self._versions = versions

    async def explain(self, request: ExplanationRequest) -> ExplanationResponse:
        model = self._versions.model(EXPLANATION_MODEL, explanation_scope(request))
        if model is None:
            return InactiveExplanationResponse()
        prompt = self._versions.prompt("reportExplanation")
        deadline = time.monotonic() + self._settings.explanation_deadline
        parts: list[tuple[checks.Role, list[str]]] = []
        for target in checks.select_items(request):
            lines = checks.clean(await self._generate(prompt, request, target, deadline))
            if not lines:
                logger.warning("리포트 설명 후처리 뒤 남는 문장 없음 item=%s", target.key)
                raise rejected()
            parts.append((target.role, lines))
        text = checks.compose(parts)
        if not checks.allowed(text):  # 후처리를 거쳐 오지만 틀 문구까지 한 번 더 확인
            raise rejected()
        quote = checks.pick_quote(request.text, " ".join(" ".join(lines) for _, lines in parts))
        return ActiveExplanationResponse(
            explanation=Explanation(text=text, quote=quote),
            versions=LlmVersions(model=f"{model.name}@{model.version}", prompt=prompt.version),
        )

    async def _generate(
        self,
        prompt: PromptChoice,
        request: ExplanationRequest,
        target: checks.Target,
        deadline: float,
    ) -> str:
        stream = self._llm.stream(
            system=prompt.body.SYSTEM,
            user=prompt.body.build_user(request.grade, target.label, target.score, request.text),
            call_type="REPORT_EXPLANATION",
            prompt_version=prompt.version,
            max_tokens=self._settings.explanation_max_tokens,
            deadline=deadline,
        )
        try:
            return "".join([chunk async for chunk in stream])
        except LlmUnavailable as exc:
            raise ApiError(503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable) from exc


def rejected() -> ApiError:
    return ApiError(422, "AI_EXPLANATION_REJECTED", "설명 검사 실패", retryable=False)
