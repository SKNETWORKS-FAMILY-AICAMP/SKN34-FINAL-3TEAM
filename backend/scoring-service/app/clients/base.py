"""서비스 간 내부 호출용 httpx 클라이언트.

내부 토큰·사용자 컨텍스트 헤더·traceparent를 자동으로 붙임.
재시도는 하지 않음 (아키텍처 1.3: 재시도는 LLM 호출에서만).
"""

import httpx

from app.config import get_settings
from app.security import INTERNAL_TOKEN_HEADER, current_user_context


async def _attach_headers(request: httpx.Request) -> None:
    request.headers[INTERNAL_TOKEN_HEADER] = get_settings().internal_token
    context = current_user_context()
    if context is not None:
        request.headers.update(context.to_headers())


def internal_client(base_url: str) -> httpx.AsyncClient:
    settings = get_settings()
    timeout = httpx.Timeout(settings.http_read_timeout, connect=settings.http_connect_timeout)
    return httpx.AsyncClient(
        base_url=base_url, timeout=timeout, event_hooks={"request": [_attach_headers]}
    )
