"""국립국어원 사전 조회 (api-spec 4.2.7, #599).

- 표준국어대사전 search.do: key·q·req_type=json·num. 표제어마다 첫 뜻 하나만 준다(검색 응답의 한계)
- 온용어 search.do: key·apiSearchWord·start·num. 용어마다 공공누리 유형(kr_gvrn_lcns_ty)이
다르고 4유형은 변경 금지
두 사전 모두 표제어가 정확히 같은 항목만 쓰고, 뜻풀이의 HTML 조각(<I>·&#44;)을 지운다.
키·주소는 설정에서만 읽고 로그·예외 메시지에 남기지 않는다(키가 URL 쿼리에 들어가므로 httpx 예외
문구도 버림).
결과는 표제어 단위로 프로세스 메모리에 캐시한다(일일 호출 한도 대비).
"""

import html
import logging
import re
import time
from dataclasses import dataclass

import httpx

from app.errors import ApiError

logger = logging.getLogger(__name__)

STDICT = "표준국어대사전"
ONYONG = "온용어"
STDICT_MAX = 50
ONYONG_MAX = 3
NO_CHANGE_LICENSE = "4"  # 공공누리 4유형: 출처표시·상업적 이용금지·변경금지


@dataclass(frozen=True)
class Candidate:
    source: str
    definition: str
    detail: str  # 품사(표준국어대사전) 또는 분야(온용어). 없으면 빈 글
    no_change: bool = False


def clean(text: str | None) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _headword(text: str | None) -> str:
    """표제어 표기의 붙임표·어깨번호 표시(-, ^)와 띄어쓰기를 뗀다"""
    return re.sub(r"[-^\s]", "", clean(text))


class DictionaryUnavailable(ApiError):
    def __init__(self) -> None:
        super().__init__(503, "DICTIONARY_UNAVAILABLE", "사전 조회 실패", retryable=True)


class Dictionary:
    def __init__(
        self,
        stdict_url: str,
        stdict_key: str,
        onyong_url: str,
        onyong_key: str,
        timeout: float = 5.0,
        ttl: float = 12 * 3600,
        max_entries: int = 2000,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._stdict = (stdict_url, stdict_key)
        self._onyong = (onyong_url, onyong_key)
        self._timeout = timeout
        self._ttl = ttl
        self._max = max_entries
        self._transport = transport
        self._cache: dict[str, tuple[float, list[Candidate]]] = {}

    @property
    def configured(self) -> bool:
        return all(self._stdict)

    async def stdict(self, word: str) -> list[Candidate]:
        return await self._cached("std:" + word, lambda: self._fetch_stdict(word))

    async def onyong(self, word: str) -> list[Candidate]:
        if not all(self._onyong):
            return []  # 온용어는 보완용이라 설정이 없으면 건너뜀
        try:
            return await self._cached("on:" + word, lambda: self._fetch_onyong(word))
        except DictionaryUnavailable:
            return []  # 보완 사전 장애는 표준국어대사전 결과만으로 이어 감

    async def candidates(self, word: str) -> list[Candidate]:
        rows = await self.stdict(word) + await self.onyong(word)
        seen: set[str] = set()
        unique = []
        for row in rows:
            if row.definition and row.definition not in seen:
                seen.add(row.definition)
                unique.append(row)
        # 변경 금지(공공누리 4유형) 뜻은 쉬운 말로 바꿀 수 없어 다른 후보가 있으면 뺀다.
        # 다른 후보가 없을 때만 원문 그대로 보여 준다(11-13 실측: "증발"에서 어려운 원문을 고름)
        changeable = [row for row in unique if not row.no_change]
        return changeable or unique

    async def _cached(self, key, fetch) -> list[Candidate]:
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < self._ttl:
            return hit[1]
        value = await fetch()
        if len(self._cache) >= self._max:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = (time.monotonic(), value)
        return value

    async def _get(self, url: str, params: dict[str, str | int], name: str) -> object:
        if not url or not params.get("key"):
            logger.warning("사전 미설정 dictionary=%s", name)
            raise DictionaryUnavailable()
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.get(url, params=params)
            response.raise_for_status()
            if not response.text.strip():
                return {}  # 표준국어대사전은 결과가 없으면 빈 본문을 준다
            return response.json()
        except (httpx.HTTPError, ValueError):
            # 예외 문구에 키가 담긴 URL이 들어 있어 종류만 남긴다
            logger.warning("사전 호출 실패 dictionary=%s", name)
            raise DictionaryUnavailable() from None

    async def _fetch_stdict(self, word: str) -> list[Candidate]:
        url, key = self._stdict
        data = await self._get(
            url, {"key": key, "q": word, "req_type": "json", "num": STDICT_MAX}, "stdict"
        )
        channel = data.get("channel", {}) if isinstance(data, dict) else {}
        items = channel.get("item") or []
        rows = []
        for item in items if isinstance(items, list) else [items]:
            if not isinstance(item, dict) or _headword(item.get("word")) != word:
                continue
            sense = item.get("sense") or {}
            sense = sense[0] if isinstance(sense, list) and sense else sense
            definition = clean(sense.get("definition") if isinstance(sense, dict) else "")
            if definition:
                rows.append(Candidate(STDICT, definition, clean(item.get("pos"))))
        return rows

    async def _fetch_onyong(self, word: str) -> list[Candidate]:
        url, key = self._onyong
        data = await self._get(
            url, {"key": key, "apiSearchWord": word, "start": 1, "num": 10}, "onyong"
        )
        channel = data.get("channel", {}) if isinstance(data, dict) else {}
        objects = channel.get("return_object") or []
        rows = []
        for obj in objects if isinstance(objects, list) else [objects]:
            for item in (obj.get("resultlist") or []) if isinstance(obj, dict) else []:
                if not isinstance(item, dict) or _headword(item.get("word")) != word:
                    continue
                definition = clean(item.get("definition"))
                if definition:
                    rows.append(
                        Candidate(
                            ONYONG,
                            definition,
                            clean(item.get("category_sub")),
                            str(item.get("kr_gvrn_lcns_ty") or "") == NO_CHANGE_LICENSE,
                        )
                    )
        rows.sort(key=lambda row: row.no_change)  # 바꿀 수 있는 뜻을 먼저 남긴다
        return rows[:ONYONG_MAX]
