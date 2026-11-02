"""LLM이 뽑은 구절이 답변 원문에 그대로 있는지 코드로 확인 (FN-JDG-03, 기획서 5.3).

허용하는 차이는 유니코드 정규화(NFC)와 공백뿐. 글자가 하나라도 다르면 불일치.
"""

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


def is_verbatim(quote: str | None, answer_text: str) -> bool:
    if quote is None:
        return False
    normalized = normalize(quote)
    return bool(normalized) and normalized in normalize(answer_text)


def visible_length(text: str) -> int:
    """공백을 뺀 글자 수 (TOO_SHORT 기준)."""
    return len(_WHITESPACE.sub("", text))
