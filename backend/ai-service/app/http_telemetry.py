"""내부 API 서버 span과 요청 지연·상태 지표 (아키텍처 4.6, #1029).

순수 ASGI 미들웨어라 분석 답변 스트림도 끝까지 잰다. 속성은 메서드·경로 템플릿·상태 코드만
쓴다(경로 값·질의·헤더·본문 없음). 로그인 사용자 요청의 traceparent 헤더를 부모로 삼는다.
/health는 kubelet probe라 span·지표에서 뺀다.
"""

import time
from typing import Any

from opentelemetry.trace import SpanKind, StatusCode
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import tracing

DURATION = "http.server.request.duration"
# 판정 마감 33초(JUDGE_DEADLINE)·리포트 설명 80초까지 보이게 semconv 기본 버킷에 15·30·60·120 추가
BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1,
    2.5,
    5,
    7.5,
    10,
    15,
    30,
    60,
    120,
)


def _duration(meter: Any) -> Any:
    return meter.create_histogram(
        DURATION,
        unit="s",
        description="ai-service 내부 API 요청 처리 시간",
        explicit_bucket_boundaries_advisory=BUCKETS,
    )


def _route(scope: Scope) -> str | None:
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else None


def _traceparent(scope: Scope) -> str | None:
    for name, value in scope.get("headers", ()):
        if name == b"traceparent":
            return value.decode("latin-1")
    return None


class HttpTelemetryMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith("/health"):
            await self.app(scope, receive, send)
            return
        method = scope["method"]
        status = 500
        started = time.perf_counter()

        async def send_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        with tracing.tracer().start_as_current_span(
            method,
            context=tracing.parent_context(_traceparent(scope)),
            kind=SpanKind.SERVER,
            record_exception=False,  # 예외 메시지에 원문이 섞일 수 있어 span event로 남기지 않음
            set_status_on_exception=False,
        ) as span:
            error_type: str | None = None
            try:
                await self.app(scope, receive, send_status)
            except Exception as exc:
                status, error_type = 500, type(exc).__qualname__
                raise
            finally:
                route = _route(scope)
                attributes: dict[str, str | int] = {
                    "http.request.method": method,
                    "http.response.status_code": status,
                }
                if route is not None:
                    attributes["http.route"] = route
                    span.update_name(f"{method} {route}")
                if status >= 500:
                    error_type = error_type or str(status)
                    attributes["error.type"] = error_type
                    span.set_status(StatusCode.ERROR)
                span.set_attributes(attributes)
                tracing.instrument(DURATION, _duration).record(
                    time.perf_counter() - started, attributes
                )
