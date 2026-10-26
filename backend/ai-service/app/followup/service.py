"""되묻기 흐름: 판정 결과로 유형 결정 → LLM 질문 생성 → 유출 검사, 실패 시 재생성 (FN-JDG-06·07).

재생성까지 유출되면 유출된 질문을 내보내지 않고 503 (중립 질문 은행 [P16]은 범위 밖).
"""

import logging

from app.config import Settings
from app.errors import ApiError
from app.followup import leak_guard, prompts
from app.followup.models import (
    FollowupRequest,
    FollowupResponse,
    FollowupType,
    LeakCheck,
    LlmVersions,
)
from app.judgment.models import JudgmentResult
from app.llm.base import LlmClient, LlmUnavailable

logger = logging.getLogger(__name__)

TYPE_BY_RESULT: dict[JudgmentResult, FollowupType] = {
    "CORRECT": "ONE_STEP_MORE",
    "PARTIAL": "TELL_MORE",
    "RETHINK": "LOOK_AGAIN",
    "HELD": "TELL_MORE",
}


class FollowupService:
    def __init__(self, llm: LlmClient, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings

    async def create(self, request: FollowupRequest) -> FollowupResponse:
        followup_type = TYPE_BY_RESULT[request.judgment.result]
        student_answers = [item.text for item in request.timeline if item.kind == "ANSWER"]
        rejected: list[str] = []
        leaks: list[str] = []
        for attempt in range(self._settings.followup_leak_max_retries + 1):
            try:
                generated = await self._llm.generate(
                    system=prompts.SYSTEM,
                    user=prompts.build_user(request, followup_type, rejected),
                    output=prompts.GeneratedQuestion,
                    call_type="FOLLOWUP",
                    prompt_version=prompts.PROMPT_VERSION,
                    max_tokens=1024,
                )
            except LlmUnavailable as exc:
                raise ApiError(
                    503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable
                ) from exc
            question = generated.data.question.strip()
            leaks = leak_guard.find_leaks(
                question,
                request.rubric,
                self._settings.followup_example_overlap_chars,
                student_answers,
            )
            if question and not leaks:
                return FollowupResponse(
                    type=followup_type,
                    question=question,
                    source="LLM" if attempt == 0 else "LLM_RETRY",
                    leak_check=LeakCheck(passed=True),
                    versions=LlmVersions(model=generated.model, prompt=prompts.PROMPT_VERSION),
                )
            rejected.append(question)
        logger.warning("되묻기 유출 검사 반복 실패: leaks=%s", leaks)
        raise ApiError(503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=True)
