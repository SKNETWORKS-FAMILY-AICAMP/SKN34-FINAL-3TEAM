"""설명할 항목 고르기·규칙 후처리·검사·인용 구절 고르기. 모두 규칙이고 LLM을 부르지 않음 (#477).

- 항목: 잘한 점(가장 높은 항목) 1개 + 함께 이야기해 볼 점(가장 낮은 항목) 1개. 동점은 항목 표 순서,
  모두 같은 점수면 1개만(중간 이상이면 잘한 점, 아니면 함께 이야기해 볼 점).
  서술 총점(hol)은 고르지 않음
- 후처리: 이유 문장 중 숫자·금지어(점수·등급 등)가 있는 문장은 버림.
  남는 문장이 없으면 그 항목은 실패
- 인용: 설명과 낱말 앞 두 글자가 가장 많이 겹치는 학생 글 문장(원문 그대로). 2개 미만이면 null
"""

import re
from dataclasses import dataclass
from typing import Literal

from app.analysis_agent.verification import FORBIDDEN
from app.report_explanation.models import ITEM_LABELS, SCORE_RANGES, ExplanationRequest

Role = Literal["STRENGTH", "DISCUSS"]
ROLE_PREFIX: dict[Role, str] = {"STRENGTH": "잘한 점", "DISCUSS": "함께 이야기해 볼 점"}
# 문장에 남기지 않는 표현: 숫자(점수·횟수·학년 등), 금지어(레벨·등급·점수·사고력 단정 등)
DIGIT = re.compile(r"[0-9０-９]")
SENTENCE = re.compile(r"[^.!?。\n]+[.!?。]?")
WORD = re.compile(r"[가-힣A-Za-z]{2,}")
MAX_SENTENCES_PER_ITEM = 2
MIN_QUOTE_OVERLAP = 2


@dataclass(frozen=True)
class Target:
    role: Role
    key: str
    label: str
    score: int


def select_items(request: ExplanationRequest) -> list[Target]:
    labels = ITEM_LABELS[request.input_type]
    keys = [key for key in labels if key != "hol"]
    best = max(keys, key=lambda key: (request.scores[key], -keys.index(key)))
    worst = min(keys, key=lambda key: (request.scores[key], keys.index(key)))

    def target(role: Role, key: str) -> Target:
        return Target(role, key, labels[key], request.scores[key])

    if request.scores[best] != request.scores[worst]:
        return [target("STRENGTH", best), target("DISCUSS", worst)]
    low, high = SCORE_RANGES[request.input_type][best]
    role: Role = "STRENGTH" if request.scores[best] >= (low + high) / 2 else "DISCUSS"
    return [target(role, best)]


def sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE.findall(text) if part.strip()]


def allowed(text: str) -> bool:
    return not DIGIT.search(text) and not any(word in text for word in FORBIDDEN)


def clean(generated: str) -> list[str]:
    """숫자·금지어가 있는 문장을 버리고 앞에서 최대 2문장. 빈 목록이면 그 항목은 실패"""
    return [s for s in sentences(generated) if allowed(s)][:MAX_SENTENCES_PER_ITEM]


def compose(parts: list[tuple[Role, list[str]]]) -> str:
    return "\n".join(f"{ROLE_PREFIX[role]}: {' '.join(lines)}" for role, lines in parts)


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
