"""리포트 서술 흐름: report가 넘긴 수치·기록으로 서술·저녁 질문 생성 (FN-RPT-04~07).

- 숫자 계산·대조와 대조 실패 시 템플릿 요약 전환은 report 담당 (class-diagram 5.2, P16)
- 인용은 후보 번호·구절로 받고, 구절이 그 후보 원문에 없으면 제외 (ID·버전은 입력값)
- LLM 실패·키 미설정·빈 응답이면 503 AI_UNAVAILABLE
"""

import logging
import time

from app.config import Settings
from app.errors import ApiError
from app.followup.models import LlmVersions
from app.llm.base import LlmClient, LlmUnavailable
from app.prompt_versions.registry import ActiveVersions
from app.report_narrative import prompts
from app.report_narrative.models import (
    Citation,
    Narrative,
    NarrativeRequest,
    NarrativeResponse,
)

logger = logging.getLogger(__name__)


class NarrativeService:
    def __init__(
        self, llm: LlmClient, settings: Settings, versions: ActiveVersions | None = None
    ) -> None:
        self._llm = llm
        self._settings = settings
        self._versions = versions or ActiveVersions()

    async def generate(self, request: NarrativeRequest) -> NarrativeResponse:
        prompt = self._versions.prompt("reportNarrative")
        budget = (
            self._settings.report_gemma_timeout + 3
            if self._settings.report_llm_provider == "runpod_gemma"
            else self._settings.narrative_deadline
        )
        try:
            generated = await self._llm.generate(
                system=prompt.body.SYSTEM
                + {
                    "DEFAULT": "",
                    "EASY": "\n말투: 짧고 익숙한 낱말로 쉽게 설명한다."
                    " 숫자·인용·금지 표현 규칙은 그대로 지킨다.",
                    "CONCISE": "\n말투: 핵심을 간결하게 쓴다."
                    " 숫자·인용·금지 표현 규칙은 그대로 지킨다.",
                }[request.tone],
                user=prompt.body.build_user(request),
                output=prompts.GeneratedNarrative,
                call_type="REPORT_NARRATIVE",
                prompt_version=prompt.version,
                max_tokens=2048,
                deadline=time.monotonic() + budget,
            )
        except LlmUnavailable as exc:
            raise ApiError(503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable) from exc
        narrative = generated.data.narrative.strip()
        evening_question = generated.data.evening_question.strip()
        if not narrative or not evening_question:
            logger.warning("리포트 서술 빈 응답")
            raise ApiError(503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=True)
        cited: dict[tuple[str, str], Citation] = {}  # (answerId, 구절)로 중복 제거, 순서 유지
        for item in generated.data.cited_quotes:
            if not 1 <= item.candidate <= len(request.quotes):
                continue
            source = request.quotes[item.candidate - 1]
            if item.quote and item.quote in source.text:
                cited.setdefault(
                    (source.answer_id, item.quote),
                    Citation(
                        attempt_id=source.attempt_id,
                        answer_id=source.answer_id,
                        answer_version=source.answer_version,
                        quote=item.quote,
                    ),
                )
        return NarrativeResponse(
            narrative=Narrative(text=narrative),
            evening_question=evening_question,
            cited_quotes=list(cited.values()),
            versions=LlmVersions(model=generated.model, prompt=prompt.version),
        )
