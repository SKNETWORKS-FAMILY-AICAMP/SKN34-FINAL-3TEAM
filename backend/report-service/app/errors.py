"""RFC 9457 Problem Details 오류 응답 (API 명세서 1.3)."""

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

TYPE_BASE = "https://sagomungchi.dev/errors/"
STATUS_CODES = {
    400: "VALIDATION_FAILED",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    415: "UNSUPPORTED_MEDIA_TYPE",
}


class ApiError(Exception):
    """업무 오류. code는 API 명세서 1.3 오류 코드를 사용."""

    def __init__(
        self, status: int, code: str, title: str, detail: str | None = None, **extra: Any
    ) -> None:
        super().__init__(detail or title)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.extra = extra


def trace_id(request: Request) -> str:
    """traceparent 헤더의 trace-id, 없으면 요청마다 새로 생성."""
    cached = getattr(request.state, "trace_id", None)
    if cached:
        return cached
    parts = request.headers.get("traceparent", "").split("-")
    value = parts[1] if len(parts) > 1 and parts[1] else uuid.uuid4().hex
    request.state.trace_id = value
    return value


def problem(
    request: Request,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    **extra: Any,
) -> JSONResponse:
    body = {
        "type": TYPE_BASE + code.lower().replace("_", "-"),
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
        "instance": request.url.path,
        "traceId": trace_id(request),
        **extra,
    }
    return JSONResponse(
        {key: value for key, value in body.items() if value is not None},
        status_code=status,
        media_type="application/problem+json",
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ResponseValidationError)
    async def handle_response_validation(
        request: Request, exc: ResponseValidationError
    ) -> JSONResponse:
        # Validation error repr can contain student answer text; do not log its body.
        logger.error("리포트 응답 스키마 검증 실패")
        return problem(request, 500, "INTERNAL_ERROR", "응답 데이터를 확인해야 합니다")

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return problem(request, exc.status, exc.code, exc.title, exc.detail, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(part) for part in error["loc"]), "reason": error["msg"]}
            for error in exc.errors()
        ]
        return problem(request, 400, "VALIDATION_FAILED", "요청 형식 오류", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = STATUS_CODES.get(exc.status_code, "REQUEST_FAILED")
        return problem(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("처리되지 않은 예외")
        return problem(request, 500, "INTERNAL_ERROR", "서버 오류")
