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


PROBLEM_SCHEMA = {
    "type": "object",
    "required": ["type", "title", "status", "code", "instance", "traceId"],
    "properties": {
        "type": {"type": "string", "format": "uri"},
        "title": {"type": "string"},
        "status": {"type": "integer"},
        "code": {"type": "string"},
        "detail": {"type": "string"},
        "instance": {"type": "string"},
        "traceId": {"type": "string"},
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"field": {"type": "string"}, "reason": {"type": "string"}},
            },
        },
    },
}
PROBLEM_DESCRIPTIONS = {
    400: "VALIDATION_FAILED",
    401: "UNAUTHENTICATED (내부 토큰 불일치)",
    403: "FORBIDDEN (학생 범위 밖)",
    404: "NOT_FOUND",
    409: "DELETION_IN_PROGRESS (학생 기록 삭제 중)",
    503: "DATA_UNAVAILABLE (근거 원문·파일 저장소 장애)",
}


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI 오류 응답 선언. 실제 응답은 register_error_handlers의 problem+json."""
    return {
        status: {
            "description": PROBLEM_DESCRIPTIONS[status],
            "content": {
                "application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}
            },
        }
        for status in statuses
    }


def install_problem_openapi(app: FastAPI) -> None:
    """FastAPI 기본 422 대신 실제 400 problem+json 계약을 OpenAPI에 반영."""
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = generate()
            for operations in schema["paths"].values():
                for operation in operations.values():
                    operation["responses"].pop("422", None)
            schemas = schema.setdefault("components", {}).setdefault("schemas", {})
            schemas.pop("HTTPValidationError", None)
            schemas.pop("ValidationError", None)
            schemas["Problem"] = PROBLEM_SCHEMA
        return app.openapi_schema

    app.openapi = openapi


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
