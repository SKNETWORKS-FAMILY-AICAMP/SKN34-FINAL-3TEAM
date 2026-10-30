"""되묻기 흐름: 판정 결과로 유형 결정 → LLM 질문 생성 → 유출 검사, 실패 시 재생성 (FN-JDG-06·07).

- 첫 생성이 LLM 실패면 503 (처리 실패, 재요청)
- 유출이면 1회 재생성(LLM_RETRY). 재생성도 유출이거나 실패·마감 초과면 question 없이
  leakCheck.passed = false → learning이 질문 은행(BANK)에서 같은 유형 질문 선택 (P16)
- 전체를 followup_deadline 안에 끝내 learning→ai 타임아웃(P12)에 걸리지 않게 함
"""

import logging
import time

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
from app.versions import ActiveVersions

logger = logging.getLogger(__name__)

TYPE_BY_RESULT: dict[JudgmentResult, FollowupType] = {
    "CORRECT": "ONE_STEP_MORE",
    "PARTIAL": "TELL_MORE",
    "RETHINK": "LOOK_AGAIN",
    "HELD": "TELL_MORE",
}


class FollowupService:
    def __init__(
        self, llm: LlmClient, settings: Settings, versions: ActiveVersions | None = None
    ) -> None:
        self._llm = llm
        self._settings = settings
        self._versions = versions or ActiveVersions()

    async def create(self, request: FollowupRequest) -> FollowupResponse:
        prompt = self._versions.prompt("followup")
        deadline = time.monotonic() + self._settings.followup_deadline
        followup_type = TYPE_BY_RESULT[request.judgment.result]
        student_answers = [item.text for item in request.timeline if item.kind == "ANSWER"]
        versions = LlmVersions(model=self._llm.model, prompt=prompt.version)
        rejected: list[str] = []
        leaks: list[str] = []
        for attempt in range(self._settings.followup_leak_max_retries + 1):
            try:
                generated = await self._llm.generate(
                    system=prompt.body.SYSTEM,
                    user=prompt.body.build_user(request, followup_type, rejected),
                    output=prompts.GeneratedQuestion,
                    call_type="FOLLOWUP",
                    prompt_version=prompt.version,
                    max_tokens=1024,
                    deadline=deadline,
                )
            except LlmUnavailable as exc:
                if attempt == 0:
                    raise ApiError(
                        503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable
                    ) from exc
                logger.warning("되묻기 재생성 실패, 질문 은행으로: code=%s", exc.code)
                break
            versions = LlmVersions(model=generated.model, prompt=prompt.version)
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
                    versions=versions,
                )
            rejected.append(question)
        logger.warning("되묻기 유출 검사 재실패, 질문 은행으로: leaks=%s", leaks)
        return FollowupResponse(
            type=followup_type,
            question=None,
            source="LLM_RETRY",
            leak_check=LeakCheck(passed=False),
            versions=versions,
        )
