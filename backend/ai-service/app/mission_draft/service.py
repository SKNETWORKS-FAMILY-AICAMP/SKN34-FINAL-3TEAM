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

    async def generate(self, request: MissionDraftRequest) -> MissionDraftResponse:
        prompt = self._versions.prompt("missionDraft")
        limit = checks.question_limit(
            self._settings.mission_draft_question_max_chars, request.grade_min
        )
        try:
            generated = await self._llm.generate(
                system=prompt.body.SYSTEM,
                user=prompt.body.build_user(request, limit),
                output=GeneratedDraft,
                call_type="MISSION_DRAFT",
                prompt_version=prompt.version,
                max_tokens=self._settings.mission_draft_max_tokens,
                deadline=time.monotonic() + self._settings.mission_draft_deadline,
            )
        except LlmUnavailable as exc:
            if exc.code == "LLM_INVALID_OUTPUT":
                raise ApiError(502, "AI_BAD_RESPONSE", "초안 형식 오류", retryable=True) from exc
            raise ApiError(503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable) from exc
        draft = Draft.model_validate(generated.data.model_dump())
        failures = checks.check(
            draft,
            request,
            self._settings.mission_draft_question_max_chars,
            self._settings.followup_example_overlap_chars,
        )
        return MissionDraftResponse(
            draft=draft,
            checks=Checks(passed=not failures, failures=failures),
            versions=LlmVersions(model=generated.model, prompt=prompt.version),
        )
