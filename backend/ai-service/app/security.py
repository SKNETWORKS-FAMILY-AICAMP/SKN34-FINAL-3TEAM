"""내부 호출 인증과 사용자 컨텍스트 (아키텍처 2.2·2.3)."""

import re
import secrets
from collections.abc import Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import get_settings
from app.errors import ApiError, problem

INTERNAL_TOKEN_HEADER = "X-Internal-Token"
USER_ID = "X-User-Id"
USER_ROLE = "X-User-Role"
STUDENT_SCOPE = "X-Student-Scope"
TRACEPARENT = "traceparent"

# 호출자별 내부 경로 허용 목록 (아키텍처 2.2, api-spec 4장). 정규식 전체 일치.
# 호출자 토큰은 INTERNAL_TOKEN_<호출자>(설정 internal_token_<호출자>).
# 빈 값이면 그 호출자를 받지 않음
CALLER_PATHS: dict[str, tuple[str, ...]] = {
    "core": (r"/internal/analysis(/.*)?",),
    "learning": (
        r"/internal/(judgments|followups|mission-drafts|theme-drafts|embeddings|memory-explanations|memory-queries)(/.*)?",
    ),
    "report-worker": (r"/internal/(report-narratives|report-explanations)(/.*)?",),
    "ops": (r"/internal/(embeddings|judgments|versions)(/.*)?",),
}
_CALLER_PATTERNS = {
    caller: tuple(re.compile(pattern) for pattern in patterns)
    for caller, patterns in CALLER_PATHS.items()
}


def matching_callers(token: str) -> list[str]:
    """헤더 토큰과 일치하는 호출자. 모든 호출자를 상수 시간 비교."""
    settings = get_settings()
    callers = []
    for caller in CALLER_PATHS:
        expected = getattr(settings, "internal_token_" + caller.replace("-", "_"))
        if expected and secrets.compare_digest(token.encode(), expected.encode()):
            callers.append(caller)
    return callers


def caller_permits(caller: str, path: str) -> bool:
    segments = path.split("/")
    if "." in segments or ".." in segments:
        return False
    return any(pattern.fullmatch(path) for pattern in _CALLER_PATTERNS[caller])


@dataclass(frozen=True)
class UserContext:
    """core가 권한 확인 후 헤더로 전달한 사용자 컨텍스트."""

    user_id: str | None
    role: str | None
    student_scope: frozenset[str]
    traceparent: str | None = None

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> "UserContext":
        scope = headers.get(STUDENT_SCOPE) or ""
        return cls(
            user_id=headers.get(USER_ID),
            role=headers.get(USER_ROLE),
            student_scope=frozenset(s.strip() for s in scope.split(",") if s.strip()),
            traceparent=headers.get(TRACEPARENT),
        )

    def require_student(self, student_id: str) -> None:
        """조회 대상 학생이 허용 범위 밖이면 403."""
        if student_id not in self.student_scope:
            raise ApiError(403, "FORBIDDEN", "접근 범위 밖 학생")

    def to_headers(self) -> dict[str, str]:
        """하위 서비스 호출에 그대로 전달할 헤더."""
        headers = {USER_ID: self.user_id, USER_ROLE: self.role, TRACEPARENT: self.traceparent}
        if self.student_scope:
            headers[STUDENT_SCOPE] = ",".join(sorted(self.student_scope))
        return {key: value for key, value in headers.items() if value}


_current: ContextVar[UserContext | None] = ContextVar("user_context", default=None)


def current_user_context() -> UserContext | None:
    return _current.get()


def bind_user_context(context: UserContext) -> Token[UserContext | None]:
    """사용자 요청 없는 처리(이벤트 소비 등)에서 컨텍스트 지정. 예: role=SYSTEM."""
    return _current.set(context)


def get_user_context(request: Request) -> UserContext:
    """라우터 의존성: Annotated[UserContext, Depends(get_user_context)]."""
    return request.state.user_context


class InternalAuthMiddleware(BaseHTTPMiddleware):
    """/internal 하위 요청의 호출자 토큰·경로 허용 목록 검사 후 사용자 컨텍스트 설정.

    토큰이 어느 호출자와도 맞지 않으면 401, 맞은 호출자의 허용 경로 밖이면 403.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/internal/"):
            return await call_next(request)
        callers = matching_callers(request.headers.get(INTERNAL_TOKEN_HEADER, ""))
        if not callers:
            return problem(request, 401, "UNAUTHENTICATED", "내부 인증 실패")
        if not any(caller_permits(caller, request.url.path) for caller in callers):
            return problem(request, 403, "FORBIDDEN", "내부 호출 허용 범위 밖")
        context = UserContext.from_headers(request.headers)
        request.state.user_context = context
        reset = _current.set(context)
        try:
            return await call_next(request)
        finally:
            _current.reset(reset)
