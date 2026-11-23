"""낱말 물어보기 흐름 (FN-LRN-21, api-spec 4.2.8, #599).

1. 표제어: 질문이 띄어쓰기 없는 한 낱말이고 표준국어대사전에 있으면 그대로, 아니면 LLM이 고름(빈
값 → OUT_OF_SCOPE)
2. 유출 미리 검사(leak이 있을 때): 질문·표제어에 정답 키·금지어 → DEFERRED(사전·LLM 없음)
3. 표준국어대사전 → 허용된 온용어 → 웹 검색에서 확인한 대체 출처를 차례로 조회
4. LLM이 뜻 번호와 쉬운 말·예문. 맞는 뜻이 없으면 다음 출처, 모두 없으면 NOT_FOUND
5. 유출 뒤 검사 → DEFERRED

사전 조회와 LLM은 전체 마감(word_help_deadline, 기본 20초) 안에서만 부른다(learning→ai 25초,
core→learning 일반 30초 안).
대체 응답(P16): 1의 LLM 실패는 질문에서 조사를 뗀 글자로 사전을 찾아 보고, 4의 LLM 실패·형식 밖은
표준국어대사전 후보 최대 3개를 DICTIONARY_ONLY로 돌려준다.
질문·응답 원문은 저장·로그하지 않는다(NFR-SEC-05). 로그는 상태·사유 코드만.
"""

import asyncio
import logging
import re
import time

from app.config import Settings
from app.errors import ApiError
from app.followup.leak_guard import find_text_leaks
from app.llm.base import LlmClient, LlmUnavailable
from app.prompt_versions.registry import ActiveVersions
from app.word_help import fake, prompts
from app.word_help.dictionary import STDICT, Candidate, Dictionary
from app.word_help.models import (
    WordHelpRequest,
    WordHelpResponse,
    WordHelpState,
    WordHelpVersions,
    WordSense,
)
from app.word_help.web_search import WordWebSearch

logger = logging.getLogger(__name__)

CALL_TYPE = "WORD_HELP"
FALLBACK_SENSES = 3

TEXTS: dict[WordHelpState, str] = {
    "DEFERRED": "이 낱말은 문제의 답과 이어져 있어서 문제를 다 풀고 알려 줄게!",
    "NOT_FOUND": "사전에서 이 문장에 맞는 뜻을 찾지 못했어. 선생님이나 보호자께 물어보자.",
    "OUT_OF_SCOPE": "나는 문제 속 모르는 낱말의 뜻만 알려 줄 수 있어. 궁금한 낱말을 적어 줄래?",
    "DICTIONARY_ONLY": "지금은 쉬운 말로 바꾸지 못했어. 사전에 적힌 뜻을 그대로 보여 줄게.",
}
# 대체 응답(P16)에서 질문 끝의 묻는 말·조사를 뗀다. 뗀 글자가 사전에 없으면 쓰지 않는다
_ASK_TAIL = re.compile(
    r"(이|가)?\s*(뭐|무엇|무슨\s*뜻|무슨\s*말|뜻)\S*\s*$|(이란|란|이라는|라는)\s*\S*\s*$"
)
_PARTICLE = re.compile(r"(은|는|이|가|을|를|의|이란|란)$")
_PUNCT = re.compile(r"[\s?!.,~‘’'\"“”·…]+")


def _single_word(question: str) -> str | None:
    word = _PUNCT.sub("", question)
    return word if word and " " not in question.strip() and len(word) <= 20 else None


def _stripped(question: str) -> str | None:
    text = _PUNCT.sub(" ", _ASK_TAIL.sub("", question.strip())).strip()
    if not text or " " in text:
        return None
    return _PARTICLE.sub("", text) or None


class WordHelpService:
    def __init__(
        self,
        llm: LlmClient,
        dictionary: Dictionary,
        settings: Settings,
        versions: ActiveVersions,
        web_search: WordWebSearch | None = None,
    ) -> None:
        self._llm = llm
        self._dictionary = dictionary
        self._settings = settings
        self._versions = versions
        self._web_search = web_search

    async def help(self, request: WordHelpRequest) -> WordHelpResponse:
        prompt = self._versions.prompt("wordHelp")
        deadline = time.monotonic() + self._settings.word_help_deadline
        model: str | None = None
        fake_mode = self._settings.word_help_provider == "fake"

        def reply(
            state: WordHelpState,
            headword: str | None = None,
            text: str | None = None,
            example: str | None = None,
            senses: list[Candidate] | None = None,
        ) -> WordHelpResponse:
            logger.info("낱말 물어보기 state=%s", state)
            return WordHelpResponse(
                state=state,
                headword=headword,
                text=text or TEXTS[state],
                example=example or None,
                senses=[
                    WordSense(
                        definition=c.definition,
                        source=c.source,  # type: ignore[arg-type]
                        attribution=c.attribution,
                        source_url=c.source_url,
                        license=c.license,
                    )
                    for c in senses or []
                ],
                versions=WordHelpVersions(prompt=prompt.version, model=model),
            )

        if self._leaks(request, request.question):
            return reply("DEFERRED")

        # 1. 표제어
        headword = _single_word(request.question)
        if headword and not await self._dictionary.stdict(headword):
            headword = None
        if headword is None:
            if fake_mode:
                headword, model = _stripped(request.question), fake.FAKE_MODEL
            else:
                try:
                    result = await self._llm.generate(
                        system=prompt.body.HEADWORD_SYSTEM,
                        user=prompt.body.build_headword_user(request),
                        output=prompts.GeneratedHeadword,
                        call_type=CALL_TYPE,
                        prompt_version=prompt.version,
                        max_tokens=self._settings.word_help_max_tokens,
                        deadline=deadline,
                    )
                    headword, model = result.data.headword.strip() or "", result.model
                except LlmUnavailable as exc:
                    logger.warning("낱말 표제어 실패 reason=%s", exc.code)
                    headword = _stripped(request.question)
                    if not headword or not await self._dictionary.stdict(headword):
                        raise ApiError(
                            503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable
                        ) from exc
            if headword == "":
                return reply("OUT_OF_SCOPE")
        if not headword:
            return reply("NOT_FOUND")
        headword = _PUNCT.sub("", headword)[:20]

        # 2. 유출 미리 검사
        if self._leaks(request, headword):
            return reply("DEFERRED")

        async def search_alternative(word: str) -> list[Candidate]:
            if self._web_search is None or fake_mode:
                return []
            return await self._web_search.candidates(word, deadline)

        seen: set[str] = set()
        for lookup in (self._dictionary.stdict, self._dictionary.onyong, search_alternative):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                async with asyncio.timeout(remaining):
                    candidates = [
                        row for row in await lookup(headword) if row.definition not in seen
                    ]
            except TimeoutError:
                break
            if not candidates:
                continue
            seen.update(row.definition for row in candidates)
            if fake_mode:
                generated, model = fake.generated(headword, candidates), fake.FAKE_MODEL
            else:
                try:
                    result = await self._llm.generate(
                        system=prompt.body.SYSTEM,
                        user=prompt.body.build_user(request, headword, candidates),
                        output=prompts.GeneratedWordHelp,
                        call_type=CALL_TYPE,
                        prompt_version=prompt.version,
                        max_tokens=self._settings.word_help_max_tokens,
                        deadline=deadline,
                    )
                    generated, model = result.data, result.model
                except LlmUnavailable as exc:
                    logger.warning("낱말 설명 실패 reason=%s", exc.code)
                    return self._dictionary_only(request, headword, candidates, reply)
            if generated.kind == "OUT_OF_SCOPE":
                return reply("OUT_OF_SCOPE")
            if generated.sense == -1:
                continue
            if not 0 <= generated.sense < len(candidates) or not generated.easy.strip():
                logger.warning("낱말 설명 형식 오류 reason=LLM_INVALID_OUTPUT")
                return self._dictionary_only(request, headword, candidates, reply)
            chosen = candidates[generated.sense]
            text, example = generated.easy.strip(), generated.example.strip()
            if self._leaks(request, f"{text} {example} {chosen.definition}"):
                return reply("DEFERRED")
            return reply("EXPLAINED", headword, text, example, [chosen])
        return reply("NOT_FOUND", headword)

    def _dictionary_only(self, request, headword, candidates, reply) -> WordHelpResponse:
        senses = [c for c in candidates if c.source == STDICT][:FALLBACK_SENSES] or candidates[
            :FALLBACK_SENSES
        ]
        if self._leaks(request, " ".join(c.definition for c in senses)):
            return reply("DEFERRED")
        return reply("DICTIONARY_ONLY", headword, senses=senses)

    def _leaks(self, request: WordHelpRequest, text: str) -> bool:
        leak = request.leak
        if leak is None:
            return False
        return bool(
            find_text_leaks(
                text,
                leak.answer_key,
                leak.forbidden_terms,
                leak.example_answer,
                self._settings.followup_example_overlap_chars,
                [],
            )
        )
