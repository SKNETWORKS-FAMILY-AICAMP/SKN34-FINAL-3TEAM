"""미션 초안 1회 생성·검사 (api-spec 4.2, class-diagram 5.4, #354).

- 요청 1번에 LLM 생성 1회(재시도 규칙은 LlmClient 그대로, P12)와 검사만 하고 반복하지 않는다.
  반복·상한은 learning 주기 작업이 이전 실패 사유를 넣어 다시 부른다.
- 전체를 mission_draft_deadline(33초) 안에 끝내 learning→ai 35초(P12)에 걸리지 않게 한다.
- 검사 실패도 200(checks.passed=false). 형식에 맞는 초안을 끝내 못 받으면 502,
  그 밖의 LLM 실패는 503.
"""

import time

from app.config import Settings
from app.errors import ApiError
from app.followup.models import LlmVersions
from app.llm.base import LlmClient, LlmUnavailable
from app.mission_draft import checks
from app.mission_draft.models import Checks, Draft, MissionDraftRequest, MissionDraftResponse
from app.mission_draft.prompts import GeneratedDraft
from app.prompt_versions.registry import ActiveVersions


class MissionDraftService:
    def __init__(
        self, llm: LlmClient, settings: Settings, versions: ActiveVersions | None = None
    ) -> None:
        self._llm = llm
        self._settings = settings
        self._versions = versions or ActiveVersions()

    async def generate(
        self,
        request: MissionDraftRequest,
        *,
        extra_user: str | None = None,
        call_type: str = "MISSION_DRAFT",
        deadline: float | None = None,
        timeout: float | None = None,
        question_max_chars: dict[int, int] | None = None,
    ) -> MissionDraftResponse:
        """extra_user·call_type·deadline·timeout·question_max_chars는 주간 테마(#437)가 부를 때만
        준다.

        테마는 이야기 조각·학년별 생각 열기 개수·테마 실패 사유를 덧붙이고
        사용량을 THEME_DRAFT로 남기며 그래프 마감 안에서 부른다.
        주지 않으면 기존 /internal/mission-drafts와 같다.
        """
        prompt = self._versions.prompt("missionDraft")
        max_chars = question_max_chars or self._settings.mission_draft_question_max_chars
        limit = checks.question_limit(max_chars, request.grade_min)
        user = prompt.body.build_user(request, limit)
        if extra_user:
            user += "\n" + extra_user
        try:
            generated = await self._llm.generate(
                system=prompt.body.SYSTEM,
                user=user,
                output=GeneratedDraft,
                call_type=call_type,
                prompt_version=prompt.version,
                max_tokens=self._settings.mission_draft_max_tokens,
                deadline=deadline or time.monotonic() + self._settings.mission_draft_deadline,
                timeout=timeout or self._settings.mission_draft_llm_timeout,
                max_retries=self._settings.mission_draft_llm_retries,
            )
        except LlmUnavailable as exc:
            if exc.code == "LLM_INVALID_OUTPUT":
                raise ApiError(502, "AI_BAD_RESPONSE", "초안 형식 오류", retryable=True) from exc
            raise ApiError(503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable) from exc
        draft = Draft.model_validate(generated.data.model_dump())
        failures = checks.check(
            draft,
            request,
            max_chars,
            self._settings.followup_example_overlap_chars,
        )
        return MissionDraftResponse(
            draft=draft,
            checks=Checks(passed=not failures, failures=failures),
            versions=LlmVersions(model=generated.model, prompt=prompt.version),
        )
