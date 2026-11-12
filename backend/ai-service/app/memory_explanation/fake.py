"""개발용 가짜 설명 (MEMORY_EXPLANATION_PROVIDER=fake, #565).

외부 호출 없이 근거만으로 정해진 문장을 만든다(같은 요청 = 같은 응답). learning(#564)이 실제
LLM 없이 설명 흐름·인용 대조를 개발하는 데 쓴다. 사용량을 남기지 않는다.
- 근거마다 한 문장: `{회차} 「{테마 제목}」에서 "{학생 답 첫 구절}"라고 답했어요[n].`
- 근거가 1개면 앞에 `질문과 가까운 기록은 {회차} 「{테마 제목}」이에요[n].`를 더해 2문장
- 인용 구절은 학생 답 일부의 첫 구절(최대 40자)이라 언제나 근거 원문의 부분 문자열.
  옮길 구절이 없으면(문장부호뿐) 인용 없이 `…에서 답을 남겼어요[n].`
"""

import re

from app.memory_explanation.models import MemoryExplanationRequest
from app.memory_explanation.prompts import GeneratedMemoryExplanation, GeneratedSentence

FAKE_MODEL = "fake-memory-explanation-v1"
QUOTE_MAX_CHARS = 40
_CUT = re.compile(r'[.!?。\n"“”]')


def _quote(excerpt: str) -> str | None:
    """학생 답 일부에서 문장부호·따옴표로 끊은 첫 조각(원문의 부분 문자열). 없으면 None"""
    for piece in _CUT.split(excerpt):
        head = piece.strip()[:QUOTE_MAX_CHARS].strip()
        if head:
            return head
    return None


def _line(week: str, title: str, excerpt: str) -> str:
    quote = _quote(excerpt)
    if quote is None:
        return f"{week} 「{title}」에서 답을 남겼어요."
    return f'{week} 「{title}」에서 "{quote}"라고 답했어요.'


def fake_generated(request: MemoryExplanationRequest) -> GeneratedMemoryExplanation:
    sentences = [
        GeneratedSentence(
            text=_line(item.week_label.strip(), item.theme_title.strip(), item.answer_excerpt),
            evidence=[item.no],
        )
        for item in request.evidence
    ]
    if len(sentences) == 1:
        item = request.evidence[0]
        sentences.insert(
            0,
            GeneratedSentence(
                text=(
                    f"질문과 가까운 기록은 {item.week_label.strip()} "
                    f"「{item.theme_title.strip()}」이에요."
                ),
                evidence=[item.no],
            ),
        )
    return GeneratedMemoryExplanation(sentences=sentences)
