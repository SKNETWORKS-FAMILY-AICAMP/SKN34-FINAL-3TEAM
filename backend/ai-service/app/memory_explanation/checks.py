"""LLM 출력 검사와 본문 조립. 모두 규칙이고 LLM을 부르지 않음 (#565, api-spec 4.2.6).

- 형식(502 AI_BAD_RESPONSE): 문장 2~3개, 빈 문장 없음
- 내용(422 AI_EXPLANATION_REJECTED): 문장마다 근거 번호 1개 이상이고 모두 요청 번호 안,
  큰따옴표 인용은 그 문장 근거 글의 부분 문자열(원문 그대로). learning이 인용을 한 번 더 대조함
- 본문: 문장 끝 문장부호 앞에 근거 번호 "[1][2]"를 붙여 공백으로 이음
"""

import re
from dataclasses import dataclass
from typing import Literal

from app.memory_explanation.models import MemoryEvidence
from app.memory_explanation.prompts import GeneratedSentence

MIN_SENTENCES = 2
MAX_SENTENCES = 3
MARK = re.compile(r"\s*\[\d+\]")  # LLM이 규칙을 어기고 넣은 번호 표시는 지우고 evidence로만 붙임
QUOTE = re.compile(r'"([^"]+)"|“([^”]+)”')
END = re.compile(r"[.!?。…~]+$")


@dataclass(frozen=True)
class Composed:
    text: str
    citations: list[int]


@dataclass(frozen=True)
class Problem:
    kind: Literal["FORMAT", "REJECTED"]
    reason: str  # 로그용 사유 코드(원문 없음)


def quotes(text: str) -> list[str]:
    return [a or b for a, b in QUOTE.findall(text)]


def check(sentences: list[GeneratedSentence], evidence: list[MemoryEvidence]) -> Problem | None:
    if not MIN_SENTENCES <= len(sentences) <= MAX_SENTENCES:
        return Problem("FORMAT", "SENTENCE_COUNT")
    if any(not MARK.sub("", sentence.text).strip() for sentence in sentences):
        return Problem("FORMAT", "BLANK_SENTENCE")
    by_no = {item.no: item for item in evidence}
    for sentence in sentences:
        if not sentence.evidence:
            return Problem("REJECTED", "NO_CITATION")
        if any(no not in by_no for no in sentence.evidence):
            return Problem("REJECTED", "CITATION_OUT_OF_RANGE")
        sources = [
            text
            for no in sentence.evidence
            for text in (
                by_no[no].answer_excerpt,
                by_no[no].mission_question,
                by_no[no].theme_title,
            )
        ]
        for quote in quotes(sentence.text):
            if not any(quote in source for source in sources):
                return Problem("REJECTED", "QUOTE_NOT_IN_EVIDENCE")
    return None


def compose(sentences: list[GeneratedSentence]) -> Composed:
    parts = []
    cited: set[int] = set()
    for sentence in sentences:
        body = MARK.sub("", sentence.text).strip()
        numbers = sorted(set(sentence.evidence))
        cited.update(numbers)
        marks = "".join(f"[{no}]" for no in numbers)
        end = END.search(body)
        punct = end.group(0) if end else "."
        parts.append(f"{body[: end.start()] if end else body}{marks}{punct}")
    return Composed(" ".join(parts), sorted(cited))
