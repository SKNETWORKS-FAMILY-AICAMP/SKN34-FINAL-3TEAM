"""Find alternate sources without relying on model-written definitions or license claims."""

import asyncio
import logging
import re
import time
from collections.abc import Iterable
from urllib.parse import urlsplit

import httpx
import openai

from app.llm.base import LlmUsage, UsageRecorder
from app.word_help.dictionary import CC_BY_SA, KOGL_1, ONYONG, Candidate, _headword, clean

logger = logging.getLogger(__name__)
_HOST = "kli.korean.go.kr"
_PATH = "/term/trgtWord/indexTrgtWord.do"
_WORD = re.compile(r"[가-힣a-zA-Z0-9]{1,20}")
_STUDENT_SEARCH_TIMEOUT = 6.0
_PAGE_LIMIT = 6
_MODEL = "gpt-6-luna"


def _entry_url(url: str) -> str | None:
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.netloc != _HOST or parts.path != _PATH:
        return None
    match = re.fullmatch(r"trgtWordNo=([0-9]{1,12})", parts.query)
    return f"https://{_HOST}{_PATH}?trgtWordNo={match[1]}" if match else None


def _field(markup: str, pattern: str) -> str:
    match = re.search(pattern, markup, re.DOTALL)
    return clean(match[1]) if match else ""


def _verified_entry(word: str, url: str, markup: str) -> Candidate | None:
    title = _field(markup, r'<h2 class="trgtWord">(.+?)</h2>')
    attribution = _field(markup, r'class="cont_src_dl"[^>]*>.*?<dd>(.+?)</dd>')
    rights = _field(markup, r'<div class="kogl_type">(.+?)</div>')
    if _headword(title) != word or not attribution:
        return None
    if re.search(r"공공누리\s*1유형", rights):
        license_url = KOGL_1
    elif attribution == "우리말샘 / 국립국어원" and "동일조건변경허락 2.0 대한민국" in rights:
        license_url = CC_BY_SA
    else:
        return None
    definition = _field(markup, r'<p class="mean">(.+?)</p>')
    definition = re.sub(r"\s*《[^》]+》$", "", definition)
    if not definition or len(definition) > 1000:
        return None
    return Candidate(ONYONG, definition, "", attribution, url, license_url)


class WordWebSearch:
    def __init__(
        self,
        client: openai.AsyncOpenAI,
        http: httpx.AsyncClient,
        recorder: UsageRecorder | None = None,
    ) -> None:
        self._client = client
        self._http = http
        self._recorder = recorder

    async def candidates(self, word: str, deadline: float) -> list[Candidate]:
        remaining = min(_STUDENT_SEARCH_TIMEOUT, deadline - time.monotonic())
        if remaining <= 0 or not _WORD.fullmatch(word):
            return []
        try:
            async with asyncio.timeout(remaining):
                response = await self._search(word, remaining)
                urls = dict.fromkeys(
                    url for raw in _source_urls(response) if (url := _entry_url(raw))
                )
                results = await asyncio.gather(
                    *(self._read(word, url) for url in list(urls)[:_PAGE_LIMIT])
                )
                return [row for row in results if row is not None]
        except (TimeoutError, openai.APIError):
            logger.info("낱말 대체 검색 실패")
            return []

    async def _search(self, word: str, remaining: float) -> openai.types.responses.Response:
        started = time.monotonic()
        response = None
        try:
            response = await self._client.responses.create(
                model=_MODEL,
                tools=[{"type": "web_search", "filters": {"allowed_domains": [_HOST]}}],
                tool_choice={"type": "web_search"},
                include=["web_search_call.action.sources"],
                instructions=(
                    "온용어에서 입력과 표제어가 정확히 일치하는 용어 상세 페이지를 찾고 "
                    "출처를 인용해. 출처가 다른 항목도 찾아. 뜻풀이를 작성하지 마."
                ),
                input=word,
                reasoning={"effort": "low"},
                max_output_tokens=512,
                store=False,
                timeout=remaining,
            )
            return response
        finally:
            if self._recorder is not None:
                usage = response.usage if response else None
                self._recorder(
                    LlmUsage(
                        call_type="WORD_HELP",
                        model=(response.model if response else None) or _MODEL,
                        prompt_version="word-help-search@1",
                        input_tokens=usage.input_tokens if usage else None,
                        output_tokens=usage.output_tokens if usage else None,
                        latency_ms=round((time.monotonic() - started) * 1000),
                        success=response is not None,
                        error_code=None if response else "LLM_WEB_SEARCH_FAILED",
                    )
                )

    async def _read(self, word: str, url: str) -> Candidate | None:
        try:
            response = await self._http.get(url, follow_redirects=False)
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        return _verified_entry(word, url, response.text)


def _source_urls(response: object) -> Iterable[str]:
    for item in getattr(response, "output", ()):
        if item.type == "web_search_call":
            for source in getattr(item.action, "sources", None) or ():
                yield source.url
        elif item.type == "message":
            for content in item.content:
                for annotation in getattr(content, "annotations", ()):
                    if annotation.type == "url_citation":
                        yield annotation.url
