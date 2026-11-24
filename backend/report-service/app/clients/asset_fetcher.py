"""추억 그림책 그림 받기 (docs/proposals/memory-book.md 9장).

learning이 준 그림 URL(테마 그림 presigned URL)을 받아 `data:` URI로 바꾼다.
PDF 렌더러는 네트워크를 막으므로 그림은 여기서만 받는다. 허용 출처(scheme://host[:port]) 밖,
리디렉트, 크기 초과, 형식 불일치는 그 그림만 None으로 둔다.

로컬 kind처럼 learning이 브라우저용 주소(예: http://127.0.0.1:19000)로 서명하는 환경은
`internal_origins`로 클러스터 안 주소에 연결하되, Host 헤더는 원래 값으로 보내
서명이 그대로 맞게 한다.
"""

import base64
import logging
from urllib.parse import urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)

SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),
}


def parse_origins(value: str) -> frozenset[str]:
    return frozenset(origin.strip().rstrip("/") for origin in value.split(",") if origin.strip())


def parse_internal_origins(value: str) -> dict[str, str]:
    pairs = {}
    for item in value.split(","):
        if "=" in item:
            public, internal = (part.strip().rstrip("/") for part in item.split("=", 1))
            if public and internal:
                pairs[public] = internal
    return pairs


def origin_of(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def sniff(body: bytes) -> str | None:
    for content_type, prefixes in SIGNATURES.items():
        if any(body.startswith(prefix) for prefix in prefixes):
            if content_type == "image/webp" and body[8:12] != b"WEBP":
                continue
            return content_type
    return None


class AssetFetcher:
    def __init__(
        self,
        client: httpx.AsyncClient,
        allowed_origins: frozenset[str],
        *,
        internal_origins: dict[str, str] | None = None,
        max_bytes: int = 5 * 1024 * 1024,
        total_bytes: int = 40 * 1024 * 1024,
    ):
        self._client = client
        self._allowed = frozenset(origin.lower() for origin in allowed_origins)
        self._internal = {k.lower(): v for k, v in (internal_origins or {}).items()}
        self._max, self._total = max_bytes, total_bytes
        if not self._allowed:
            # 설정 누락이면 모든 그림책이 그림 없이 만들어진다(#974).
            # 리포트·삭제 큐도 같은 워커라 기동은 막지 않는다
            logger.warning(
                "그림책 그림 허용 출처(MEMORY_BOOK_ASSET_ORIGINS)가 비어 있어 그림 없이 만듦"
            )

    def session(self) -> "AssetSession":
        return AssetSession(self)


class AssetSession:
    """그림책 한 권의 그림들. 전체 크기 상한을 같이 센다."""

    def __init__(self, fetcher: AssetFetcher):
        self._fetcher, self._used = fetcher, 0

    async def data_uri(self, url: str | None) -> str | None:
        if not url:
            return None
        fetcher = self._fetcher
        origin = origin_of(url)
        if origin is None or origin not in fetcher._allowed:
            logger.info("그림책 그림 건너뜀: 허용 출처 밖")
            return None
        parts = urlsplit(url)
        target, headers = url, {}
        internal = fetcher._internal.get(origin)
        if internal:
            inner = urlsplit(internal)
            target = urlunsplit((inner.scheme, inner.netloc, parts.path, parts.query, ""))
            headers["Host"] = parts.netloc
        try:
            async with fetcher._client.stream(
                "GET", target, headers=headers, follow_redirects=False
            ) as response:
                if response.status_code != 200:
                    logger.info("그림책 그림 건너뜀: 상태 %s", response.status_code)
                    return None
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > fetcher._max or self._used + len(body) > fetcher._total:
                        logger.info("그림책 그림 건너뜀: 크기 상한")
                        return None
        except httpx.HTTPError:
            logger.info("그림책 그림 건너뜀: 연결 실패")
            return None
        content_type = sniff(bytes(body))
        if content_type is None:
            logger.info("그림책 그림 건너뜀: 형식")
            return None
        self._used += len(body)
        return f"data:{content_type};base64,{base64.b64encode(bytes(body)).decode()}"
