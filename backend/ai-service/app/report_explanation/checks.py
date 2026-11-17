"""상세 설명 정리·검사·조립·인용 구절 고르기. 모두 규칙이고 LLM을 부르지 않음 (#477, @3).

- 정리(clean, 2026-11-17 LoRA용 완화): 설명 전체를 버리는 대신 문장 단위로 고친다.
  · 목록 기호·Markdown 머리는 지우고, 반복된 마침표·빈 따옴표 덩어리는 줄임
  · 큰따옴표 인용은 앞뒤 공백을 다듬어 학생 글에 그대로 있으면 큰따옴표로 두고,
    없으면 작은따옴표로 바꿈(지어낸 문장을 원문 인용처럼 보이지 않게)
  · 금지어(점수·등급·사고력 등, report 검사와 같은 범위)·인사말, 학생 글에 없는 숫자·횟수
    표현이 든 문장은 그 문장만 뺌
- 검사(allowed): 정리 뒤에도 남은 금지 요소가 있으면 거절(마지막 안전장치)
- 조립: "상세 분석 / 보완할 지점 / 개선 방안" 소제목 줄과 본문을 빈 줄로 이어 붙임
- 인용: 설명과 낱말 앞 두 글자가 가장 많이 겹치는 학생 글 문장(원문 그대로). 2개 미만이면 null
"""

import re

from app.analysis_agent.verification import FORBIDDEN as ANALYSIS_FORBIDDEN
from app.report_explanation.models import ExplanationDetail

# report-service 설명 검사(FORBIDDEN·UNSUPPORTED_CLAIM)와 같은 범위까지 막아
# report에서 설명이 통째로 빠지지 않게
FORBIDDEN = (*ANALYSIS_FORBIDDEN, "순위", "백분위", "백분율", "퍼센트")
NUMBER = re.compile(r"[0-9０-９]+")
KOREAN_COUNT = re.compile(
    r"(?<![가-힣])(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|스무)\s*(?:번|회|개|건|문장|글자)"
)
SENTENCE = re.compile(r"[^.!?。\n]+[.!?。]?")
WORD = re.compile(r"[가-힣A-Za-z]{2,}")
PREFACE = re.compile(r"안녕하세요|학부모님|분석한 결과를 드립니다|지금부터 살펴보겠")
LIST_OR_MARKDOWN = re.compile(r"^\s*(?:[-*•#]+|\d+[.)])\s", re.MULTILINE)
DOUBLE_QUOTED = re.compile(r'[“"「『]([^”"」』]*)[”"」』]')
EMPTY_QUOTES = re.compile(r"(?:['\"“”‘’]\s*){3,}")
REPEATED_DOTS = re.compile(r"\.(?:\s*\.)+")
SENTENCE_END = ".!?。"
QUOTE_PAIRS = {'"': '"', "'": "'"}
MIN_QUOTE_OVERLAP = 2
TITLES = ("상세 분석", "보완할 지점", "개선 방안")


def sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE.findall(text) if part.strip()]


def _requote(match: re.Match[str], source: str) -> str:
    inner = match.group(1).strip()
    if not inner:
        return ""
    return f'"{inner}"' if inner in source else f"'{inner}'"


def _split(paragraph: str) -> list[str]:
    """따옴표 안의 마침표에서는 자르지 않는 문장 나누기"""
    parts, start, closing = [], 0, None
    for index, char in enumerate(paragraph):
        if closing is not None:
            if char == closing:
                closing = None
        elif char in QUOTE_PAIRS:
            closing = QUOTE_PAIRS[char]
        elif char in SENTENCE_END and (
            index + 1 == len(paragraph) or paragraph[index + 1].isspace()
        ):
            parts.append(paragraph[start : index + 1].strip())
            start = index + 1
    parts.append(paragraph[start:].strip())
    return [part for part in parts if part]


def _keep(sentence: str, source: str) -> bool:
    if any(word in sentence for word in FORBIDDEN) or PREFACE.search(sentence):
        return False
    if sentence.count('"') % 2 or sentence.count("'") % 2:
        return False  # 짝이 맞지 않는 따옴표(잘린 인용)
    if not set(NUMBER.findall(sentence)) <= set(NUMBER.findall(source)):
        return False  # "3"은 원문의 "30" 안에 있어도 허용하지 않음
    return all(match.group(0) in source for match in KOREAN_COUNT.finditer(sentence))


def clean(text: str | None, source: str) -> str:
    """문장 단위로 고치고 빼서 남은 본문. 남는 문장이 없으면 빈 문자열"""
    if not text:
        return ""
    text = LIST_OR_MARKDOWN.sub("", text)
    text = EMPTY_QUOTES.sub(" ", text)
    text = DOUBLE_QUOTED.sub(lambda match: _requote(match, source), text)
    text = REPEATED_DOTS.sub(".", text)
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", text):
        flat = re.sub(r"\s+", " ", paragraph).strip()
        kept = [s for s in _split(flat) if _keep(s, source)]
        if kept:
            paragraphs.append(" ".join(kept))
    return "\n\n".join(paragraphs)


def allowed(text: str, source: str) -> bool:
    """금지어·인사말·목록 기호가 없고, 숫자는 학생 글에 있는 수만, 큰따옴표 인용은 원문 그대로만"""
    if not text.strip() or any(word in text for word in FORBIDDEN):
        return False
    if PREFACE.search(text) or LIST_OR_MARKDOWN.search(text):
        return False
    if any(quote not in source for quote in DOUBLE_QUOTED.findall(text)):
        return False
    numbers_in_source = set(NUMBER.findall(source))
    return all(number in numbers_in_source for number in NUMBER.findall(text))


def parts(detail: ExplanationDetail, source: str = "") -> list[tuple[str, str]]:
    bodies = (detail.analysis, detail.improvement_points, detail.next_steps)
    pairs = zip(TITLES, bodies, strict=True)
    cleaned = ((title, clean(body, source)) for title, body in pairs)
    return [(title, body) for title, body in cleaned if body]


def compose(sections: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"{title}\n{body}" for title, body in sections)


def _stems(text: str) -> set[str]:
    # 조사·어미가 붙어도 같은 낱말로 보려고 앞 두 글자만 비교 ("주장을"·"주장이" → "주장")
    return {word[:2] for word in WORD.findall(text)}


def pick_quote(student_text: str, explanation: str) -> str | None:
    wanted = _stems(explanation)
    best, best_overlap = None, MIN_QUOTE_OVERLAP - 1
    for sentence in sentences(student_text):
        overlap = len(_stems(sentence) & wanted)
        if overlap > best_overlap:
            best, best_overlap = sentence, overlap
    return best
