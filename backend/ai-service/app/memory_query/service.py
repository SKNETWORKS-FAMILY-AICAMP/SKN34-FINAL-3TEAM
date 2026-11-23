"""추억 검색 질의 변환 흐름 (FN-RET-12, api-spec 4.2.7, #681).

1. 프롬프트 memoryQuery로 ai 기본 LLM 1회 생성(구조화 출력, 출력 512토큰, 호출 7초·재시도 없음,
   사용량 callType MEMORY_QUERY). learning→ai 8초 안에 끝나게 P12 기본값(15초·재시도 1회)을
   이 호출만 덮어씀(결정 기록 16.3). MEMORY_QUERY_PROVIDER=fake면 LLM 대신 가짜 규칙
2. 칸 규칙 검사(checks)
3. LLM 경로에서만 "N월 N째 주"를 코드가 계산해 기간을 덮어쓰고
   그 표현 조각을 키워드에서 뺌(weeks, #877).
   가짜 구현은 "period 언제나 null" 계약을 지키려고 적용하지 않음 → 응답

LLM 실패·미설정·시간 초과는 503 AI_UNAVAILABLE, 구조화 출력 실패·칸 규칙 위반은 502
AI_BAD_RESPONSE. learning은 재시도 가능한 실패(5xx·시간 초과)를 한 번 더 부르고, 끝내 실패하면
기간 낱말이 있는 질문은 503 안내, 없으면 원문 질문으로 검색한다(#878, 결정 기록 16.9).
질문·변환 결과는 저장하지 않고 로그에도 남기지 않는다(NFR-SEC-05). 로그는 사유 코드만.
"""

import logging

from app.config import Settings
from app.errors import ApiError
from app.followup.models import LlmVersions
from app.llm.base import LlmClient, LlmUnavailable
from app.memory_query import checks, prompts, weeks
from app.memory_query.fake import FAKE_MODEL, fake_generated
from app.memory_query.models import MemoryQueryRequest, MemoryQueryResponse
from app.prompt_versions.registry import ActiveVersions

logger = logging.getLogger(__name__)

CALL_TYPE = "MEMORY_QUERY"


class MemoryQueryService:
    def __init__(self, llm: LlmClient, settings: Settings, versions: ActiveVersions) -> None:
        self._llm = llm
        self._settings = settings
        self._versions = versions

    async def rewrite(self, request: MemoryQueryRequest) -> MemoryQueryResponse:
        prompt = self._versions.prompt("memoryQuery")
        if self._settings.memory_query_provider == "fake":
            generated, model = fake_generated(request), FAKE_MODEL
        else:
            try:
                result = await self._llm.generate(
                    system=prompt.body.SYSTEM,
                    user=prompt.body.build_user(request),
                    output=prompts.GeneratedMemoryQuery,
                    call_type=CALL_TYPE,
                    prompt_version=prompt.version,
                    max_tokens=self._settings.memory_query_max_tokens,
                    timeout=self._settings.memory_query_llm_timeout,
                    max_retries=0,
                )
            except LlmUnavailable as exc:
                if exc.code == "LLM_INVALID_OUTPUT":
                    logger.warning("질의 변환 형식 오류 reason=LLM_INVALID_OUTPUT")
                    raise bad_response() from exc
                logger.warning("질의 변환 LLM 실패 reason=%s", exc.code)
                raise ApiError(
                    503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable
                ) from exc
            generated, model = result.data, result.model
        checked = checks.check(generated)
        if isinstance(checked, checks.Problem):
            logger.warning("질의 변환 검사 실패 reason=%s", checked.reason)
            raise bad_response()
        if self._settings.memory_query_provider != "fake":
            checked = _apply_week(checked, request)
        return MemoryQueryResponse(
            keywords=checked.keywords,
            period=checked.period,
            search_text=checked.search_text,
            versions=LlmVersions(model=model, prompt=prompt.version),
        )


def _apply_week(checked: checks.Checked, request: MemoryQueryRequest) -> checks.Checked:
    """몇째 주 표현이 있으면 LLM 기간 대신 계산값(정할 수 없으면 null)을 쓴다.

    표현 조각과 같은 키워드는 뺀다.
    """
    week = weeks.week_of_month(request.query, request.today)
    if week is None:
        return checked
    keywords = [keyword for keyword in checked.keywords if not week.covers(keyword)]
    return checks.Checked(keywords, week.period, checked.search_text)


def bad_response() -> ApiError:
    return ApiError(502, "AI_BAD_RESPONSE", "질의 변환 응답 형식 오류", retryable=True)
