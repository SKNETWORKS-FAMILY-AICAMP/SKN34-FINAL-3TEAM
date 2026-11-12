"""추억 설명 흐름 (FN-RET-13, api-spec 4.2.6, #565).

1. 프롬프트 memoryExplanation으로 ai 기본 LLM 1회 생성(P12 15초·재시도 1회, 구조화 출력,
   사용량 callType MEMORY_EXPLANATION). MEMORY_EXPLANATION_PROVIDER=fake면 LLM 대신 가짜 규칙
2. 규칙 검사(checks) → 문장 끝에 근거 번호를 붙여 본문 조립

LLM 실패·미설정·시간 초과는 503 AI_UNAVAILABLE, 형식 밖 응답(구조화 출력 실패·문장 수·빈 문장)은
502 AI_BAD_RESPONSE, 근거 번호 없음·범위 밖·인용 불일치는 422 AI_EXPLANATION_REJECTED.
learning은 422·5xx를 모두 설명 FAILED로 돌려 검색 결과를 유지한다(P27).
질문·근거·설명 원문은 저장하지 않고 로그에도 남기지 않는다(NFR-SEC-05). 로그는 사유 코드만.
"""

import logging

from app.config import Settings
from app.errors import ApiError
from app.followup.models import LlmVersions
from app.llm.base import LlmClient, LlmUnavailable
from app.memory_explanation import checks, prompts
from app.memory_explanation.fake import FAKE_MODEL, fake_generated
from app.memory_explanation.models import MemoryExplanationRequest, MemoryExplanationResponse
from app.prompt_versions.registry import ActiveVersions

logger = logging.getLogger(__name__)

CALL_TYPE = "MEMORY_EXPLANATION"


class MemoryExplanationService:
    def __init__(self, llm: LlmClient, settings: Settings, versions: ActiveVersions) -> None:
        self._llm = llm
        self._settings = settings
        self._versions = versions

    async def explain(self, request: MemoryExplanationRequest) -> MemoryExplanationResponse:
        prompt = self._versions.prompt("memoryExplanation")
        if self._settings.memory_explanation_provider == "fake":
            generated, model = fake_generated(request), FAKE_MODEL
        else:
            try:
                result = await self._llm.generate(
                    system=prompt.body.SYSTEM,
                    user=prompt.body.build_user(request),
                    output=prompts.GeneratedMemoryExplanation,
                    call_type=CALL_TYPE,
                    prompt_version=prompt.version,
                    max_tokens=self._settings.memory_explanation_max_tokens,
                )
            except LlmUnavailable as exc:
                if exc.code == "LLM_INVALID_OUTPUT":
                    logger.warning("추억 설명 형식 오류 reason=LLM_INVALID_OUTPUT")
                    raise bad_response() from exc
                raise ApiError(
                    503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable
                ) from exc
            generated, model = result.data, result.model
        problem = checks.check(generated.sentences, request.evidence)
        if problem is not None:
            logger.warning("추억 설명 검사 실패 kind=%s reason=%s", problem.kind, problem.reason)
            raise bad_response() if problem.kind == "FORMAT" else rejected()
        composed = checks.compose(generated.sentences)
        return MemoryExplanationResponse(
            text=composed.text,
            citations=composed.citations,
            versions=LlmVersions(model=model, prompt=prompt.version),
        )


def bad_response() -> ApiError:
    return ApiError(502, "AI_BAD_RESPONSE", "설명 응답 형식 오류", retryable=True)


def rejected() -> ApiError:
    return ApiError(422, "AI_EXPLANATION_REJECTED", "설명 검사 실패", retryable=False)
