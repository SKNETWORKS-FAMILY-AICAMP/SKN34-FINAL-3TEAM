"""상세 설명 정리·검사·조립·인용 구절 고르기. 모두 규칙이고 LLM을 부르지 않음 (#477, @3).

- 정리(clean, 2026-11-17 LoRA용 완화): 설명 전체를 버리는 대신 문장 단위로 고친다.
  · 목록 기호·Markdown 머리는 지우고, 반복된 마침표·빈 따옴표 덩어리는 줄임
  · 큰따옴표 인용은 앞뒤 공백을 다듬어 학생 글에 그대로 있으면 큰따옴표로 두고,
    없으면 작은따옴표로 바꿈(지어낸 문장을 원문 인용처럼 보이지 않게)
  · 금지어(점수·등급·사고력 등, report 검사와 같은 범위)·인사말, 학생 글에 없는 숫자·횟수
    표현, 숫자 없이 점수를 암시하는 말("낮은 평가를 받았기 때문에" 등)이 든 문장은 그 문장만 뺌
  · 문단 끝이 문장 끝 표시 없이 끝나면 그 조각을 뺌(#747). 모델이 인용 부호를 이스케이프하지
    않아 칸이 "처음에는 "처럼 짧게 끊긴 JSON도 형식은 맞아서, 이 조각만 남은 칸은 비고
    상세 분석이 비면 설명 전체가 거절됨(infra.md 9.13.9)
- 반복 제거(cleaned, 2026-11-20): 세 칸을 차례로 읽으며 앞에서 이미 나온 문장과 같거나
  거의 같은(띄어쓰기·문장부호를 빼고 85% 이상 일치) 문장을 뺌. 뺀 문장 수도 함께 돌려줘
  서비스가 재생성 여부를 정함
- 검사(allowed): 정리 뒤에도 남은 금지 요소가 있으면 거절(마지막 안전장치)
- 조립: "상세 분석 / 보완할 지점 / 개선 방안" 소제목 줄과 본문을 빈 줄로 이어 붙임
- 인용: 설명과 낱말 앞 두 글자가 가장 많이 겹치는 학생 글 문장(원문 그대로). 2개 미만이면 null
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

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
# 숫자 없이 채점 결과를 말로 드러내는 문장 (2026-11-20, LoRA가 "설명의 적절성에서 낮은 평가를
# 받았기 때문에"처럼 입력 항목 점수를 풀어 씀). 학부모 화면에 점수·등급을 보이지 않는 원칙
# (FN-RPT-08·09)이라 그 문장만 뺀다. 글 자체에 대한 "통일성이 떨어진다" 같은 관찰은 남긴다.
SCORE_HINT = re.compile(
    r"평가\s*(?:를|가|에서|결과|받|되|했|하였)"
    r"|(?:낮은|높은|좋은|나쁜|부정적인|긍정적인)\s*평가"
    r"|(?:낮게|높게)\s*(?:평가|채점|매겨)"
    r"|(?:채점|평가)\s*기준"
    r"|기준에\s*(?:못\s*미|미치지|미달)"
    r"|항목\s*점|만점|감점|배점"
    r"|(?:낮은|높은)\s*수준"
)
# 채점 항목 이름을 셋 이상 늘어놓는 문장("적절성, 구체성, 명료성 ... 에서 모두")도 점수표를
# 옮긴 것이라 뺀다. 한두 개를 근거와 함께 쓰는 관찰("통일성이 떨어집니다")은 남긴다.
RUBRIC_TERM = re.compile(r"충실성|적절성|구체성|명료성|통일성|연결성|정확성|타당성|다양성")
RUBRIC_DUMP = 3
# 초등학생이 스스로 할 수 없는 자료 조사 요구 (2026-11-20, "연구 결과나 통계 자료를 제시하면
# 좋겠습니다"). 학생 글에 같은 말이 있으면(예: 직접 조사한 이야기) 그 문장은 남긴다.
RESEARCH_ASK = re.compile(
    r"통계|연구\s*결과|연구\s*자료|데이터|논문|전문가(?:의)?\s*(?:의견|자료|말)"
    r"|객관적인\s*(?:근거|자료)|조사\s*자료|수치\s*자료|과학적\s*근거"
)
LIST_OR_MARKDOWN = re.compile(r"^\s*(?:[-*•#]+|\d+[.)])\s", re.MULTILINE)
INLINE_MARKDOWN = re.compile(r"\*\*|__|`")
# 채점표 머리말("명료성: ", "설명의 적절성: ")은 지우고 뒤 문장만 남긴다
RUBRIC_LABEL = re.compile(
    r"(?:(?<=^)|(?<=[.!?。]\s))(?:[가-힣]+의\s*)?"
    r"(?:충실성|적절성|구체성|명료성|통일성|연결성|정확성|타당성|다양성|전달력|표현력)\s*:\s*",
    re.MULTILINE,
)
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
    if SCORE_HINT.search(sentence) or len(RUBRIC_TERM.findall(sentence)) >= RUBRIC_DUMP:
        return False  # 숫자 없이 점수·평가 결과를 암시하거나 채점 항목을 늘어놓은 문장
    if any(match.group(0) not in source for match in RESEARCH_ASK.finditer(sentence)):
        return False  # 초등학생에게 통계·연구 결과 같은 자료 조사를 요구하는 문장
    if sentence.count('"') % 2 or sentence.count("'") % 2:
        return False  # 짝이 맞지 않는 따옴표(잘린 인용)
    if not set(NUMBER.findall(sentence)) <= set(NUMBER.findall(source)):
        return False  # "3"은 원문의 "30" 안에 있어도 허용하지 않음
    return all(match.group(0) in source for match in KOREAN_COUNT.finditer(sentence))


def _ended(sentence: str) -> bool:
    """닫는 따옴표·괄호를 떼고 마침표·물음표·느낌표로 끝나는지"""
    return sentence.rstrip("\"'”’」』)").endswith(tuple(SENTENCE_END))


def clean(text: str | None, source: str) -> str:
    """문장 단위로 고치고 빼서 남은 본문. 남는 문장이 없으면 빈 문자열"""
    if not text:
        return ""
    text = LIST_OR_MARKDOWN.sub("", text)
    text = INLINE_MARKDOWN.sub("", text)  # 문장 안 굵은 글씨(**명료성**) 표시
    text = RUBRIC_LABEL.sub("", text)
    text = EMPTY_QUOTES.sub(" ", text)
    text = DOUBLE_QUOTED.sub(lambda match: _requote(match, source), text)
    text = REPEATED_DOTS.sub(".", text)
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", text):
        flat = re.sub(r"\s+", " ", paragraph).strip()
        parts = _split(flat)
        if parts and not _ended(parts[-1]):
            parts.pop()  # 문장 끝 표시 없이 끝난 조각은 잘린 출력으로 봄(#747)
        kept = [s for s in parts if _keep(s, source)]
        if kept:
            paragraphs.append(" ".join(kept))
    return "\n\n".join(paragraphs)


def allowed(text: str, source: str) -> bool:
    """금지어·인사말·목록 기호가 없고, 숫자는 학생 글에 있는 수만, 큰따옴표 인용은 원문 그대로만"""
    if not text.strip() or any(word in text for word in FORBIDDEN):
        return False
    if PREFACE.search(text) or LIST_OR_MARKDOWN.search(text) or SCORE_HINT.search(text):
        return False
    if any(len(RUBRIC_TERM.findall(sentence)) >= RUBRIC_DUMP for sentence in _split(text)):
        return False
    if any(quote not in source for quote in DOUBLE_QUOTED.findall(text)):
        return False
    numbers_in_source = set(NUMBER.findall(source))
    return all(number in numbers_in_source for number in NUMBER.findall(text))


REPEAT_KEY = re.compile(r"[\s.,!?·'\"“”‘’]")
REPEAT_SIMILAR = 0.85
REPEAT_MIN_FUZZY = 10  # 이보다 짧은 문장은 글자까지 같을 때만 반복으로 봄


@dataclass(frozen=True)
class Cleaned:
    sections: list[tuple[str, str]]
    sentences: int  # 정리 뒤, 반복 제거 전 문장 수
    repeated: int  # 앞에서 나온 문장과 같거나 거의 같아 뺀 문장 수


def _repeats(key: str, earlier: str) -> bool:
    if key == earlier:
        return True
    if min(len(key), len(earlier)) < REPEAT_MIN_FUZZY:
        return False
    return SequenceMatcher(None, key, earlier).ratio() >= REPEAT_SIMILAR


def _dedupe(sections: list[tuple[str, str]]) -> Cleaned:
    seen: list[str] = []
    kept_sections: list[tuple[str, str]] = []
    total = removed = 0
    for title, body in sections:
        paragraphs = []
        for paragraph in body.split("\n\n"):
            kept = []
            for sentence in _split(paragraph):
                total += 1
                key = REPEAT_KEY.sub("", sentence)
                if any(_repeats(key, earlier) for earlier in seen):
                    removed += 1
                    continue
                seen.append(key)
                kept.append(sentence)
            if kept:
                paragraphs.append(" ".join(kept))
        if paragraphs:
            kept_sections.append((title, "\n\n".join(paragraphs)))
    return Cleaned(kept_sections, total, removed)


def cleaned(detail: ExplanationDetail, source: str = "") -> Cleaned:
    """칸마다 문장 단위로 정리한 뒤, 칸 사이·칸 안의 반복 문장을 뺌. 빈 칸은 뺌"""
    bodies = (detail.analysis, detail.improvement_points, detail.next_steps)
    pairs = zip(TITLES, bodies, strict=True)
    return _dedupe([(title, clean(body, source)) for title, body in pairs])


def parts(detail: ExplanationDetail, source: str = "") -> list[tuple[str, str]]:
    return cleaned(detail, source).sections


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
