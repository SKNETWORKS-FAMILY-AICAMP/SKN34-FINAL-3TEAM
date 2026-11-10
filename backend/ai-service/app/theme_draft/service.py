"""주간 테마 초안 1회 생성 (api-spec 4.2, class-diagram 5.5, #437).

- 요청 1번에 그래프를 한 번 끝까지 실행한다. 그래프 안에서 실패한 부분만 실패 사유를 넣어 상한까지
  다시 만들고, 마감(theme_draft_deadline)까지 남은 시간이 부족하면 다음 재생성을 시작하지 않는다.
- 끝내 실패하면 200 + failure. 형식 밖 LLM 응답은 502, 그 밖 실패·마감 초과는 503.
- 테마 모델 설정이 틀리면(검토 모델 = 생성 모델, 키 없음) 이 경로만 503(NotReadyRunner).
- 지금은 글 단계(줄거리·미션·대화·글 검토)까지. images·videos·motions는 빈 값.
"""

import re
import time
from typing import Any, Protocol

from app.config import Settings
from app.errors import ApiError
from app.followup.models import LlmVersions
from app.llm.base import LlmClient, LlmUnavailable
from app.mission_draft.service import MissionDraftService
from app.prompt_versions.registry import ActiveVersions
from app.theme_draft.checks import DAY_TYPE, DAYS, public_theme
from app.theme_draft.graph import build_graph
from app.theme_draft.models import (
    ThemeDraftRequest,
    ThemeDraftResponse,
    ThemeFailureResult,
    ThemeWarning,
)
from app.theme_draft.nodes import ThemeContext, ThemeState

DAY_PREFIX = re.compile(r"^(MON|TUE|WED|THU|FRI)\s+(.+)$")


class ThemeDraftRunner(Protocol):
    async def run(self, request: ThemeDraftRequest, deadline: float) -> ThemeDraftResponse: ...


class NotReadyRunner:
    """테마 모델 설정이 틀린 동안의 자리. 재시도해도 결과가 같으므로 retryable=False."""

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail

    async def run(self, request: ThemeDraftRequest, deadline: float) -> ThemeDraftResponse:
        raise ApiError(
            503, "AI_UNAVAILABLE", "테마 초안 생성 준비 안 됨", self.detail, retryable=False
        )


def initial_state(request: ThemeDraftRequest) -> ThemeState:
    """previousFailures → 처음부터 넣을 사유. THEME·REVIEW는 줄거리, MISSION은 요일별 미션.

    MISSION 사유는 "<요일> <검사 코드> <자세히>"이고 요일이 없으면 다섯 요일 모두에 넣는다.
    IMAGE는 그림 단계가 붙을 때 쓴다(글 단계는 무시).
    """
    plan_feedback: list[tuple[str, list[str]]] = []
    seed: dict[str, list[str]] = {}
    for failure in request.previous_failures:
        if failure.stage in ("THEME", "REVIEW"):
            plan_feedback.append((failure.stage, list(failure.reasons)))
        elif failure.stage == "MISSION":
            for reason in failure.reasons:
                m = DAY_PREFIX.match(reason.strip())
                for day in [m.group(1)] if m else DAYS:
                    seed.setdefault(day, []).append(m.group(2) if m else reason.strip())
    return {
        "plan_feedback": plan_feedback,
        "plan_attempts": 0,
        "request_seed": seed,
        "mission_seed": {},
        "review_runs": 0,
    }


def warnings_of(state: ThemeState) -> list[ThemeWarning]:
    out: list[ThemeWarning] = []
    for day in DAYS:
        out += [
            ThemeWarning(stage="MISSION", item=day, reason=r)
            for r in (state.get("mission_warnings") or {}).get(day) or []
        ]
    for day in DAYS:
        out += [
            ThemeWarning(stage="DIALOGUE", item=day, reason=r)
            for r in (state.get("dialogue_omitted") or {}).get(day) or []
        ]
    for item in state.get("review_warnings") or []:
        days = item.get("days") or []
        out.append(
            ThemeWarning(
                stage="REVIEW", item=" ".join([item["id"], *days]), reason=item.get("reason") or ""
            )
        )
    return out


def assemble(state: ThemeState, model: str, prompt_version: str) -> ThemeDraftResponse:
    theme = state.get("theme")
    drafts = state.get("drafts") or {}
    dialogues = state.get("dialogues") or {}
    failure = state.get("failure")
    payload: dict[str, Any] = {
        "theme": public_theme(theme) if theme else None,
        "missions": [
            {"day": d, "thinkingType": DAY_TYPE[d], "draft": drafts[d]}
            for d in DAYS
            if theme and d in drafts
        ],
        "dialogues": [
            {"day": d, "lines": dialogues[d]} for d in DAYS if theme and dialogues.get(d)
        ],
        "images": {},
        "videos": {},
        "motions": {},
        "warnings": warnings_of(state),
        "failure": ThemeFailureResult(**failure) if failure else None,
        "versions": LlmVersions(model=model, prompt=prompt_version),
    }
    return ThemeDraftResponse.model_validate(payload)


class ThemeDraftGraphRunner:
    """테마 그래프 실행과 응답 조립. 미션은 미션 초안 장치를 테마 생성 모델로 재사용한다."""

    def __init__(
        self,
        llm: LlmClient,
        review_llm: LlmClient,
        settings: Settings,
        versions: ActiveVersions | None = None,
    ) -> None:
        self._llm = llm
        self._review_llm = review_llm
        self._settings = settings
        self._versions = versions or ActiveVersions()

    async def run(self, request: ThemeDraftRequest, deadline: float) -> ThemeDraftResponse:
        prompt = self._versions.prompt("themeDraft")
        context = ThemeContext(
            request=request,
            settings=self._settings,
            llm=self._llm,
            review_llm=self._review_llm,
            missions=MissionDraftService(self._llm, self._settings, self._versions),
            prompt=prompt,
            deadline=deadline,
            clock=time.monotonic,
        )
        try:
            state = await build_graph().ainvoke(initial_state(request), context=context)
        except LlmUnavailable as exc:
            if exc.code == "LLM_INVALID_OUTPUT":
                raise ApiError(
                    502, "AI_BAD_RESPONSE", "테마 초안 형식 오류", retryable=True
                ) from exc
            raise ApiError(503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable) from exc
        return assemble(state, self._llm.model, prompt.version)


class ThemeDraftService:
    def __init__(self, runner: ThemeDraftRunner, settings: Settings) -> None:
        self._runner = runner
        self._settings = settings

    async def generate(self, request: ThemeDraftRequest) -> ThemeDraftResponse:
        deadline = time.monotonic() + self._settings.theme_draft_deadline
        return await self._runner.run(request, deadline)
