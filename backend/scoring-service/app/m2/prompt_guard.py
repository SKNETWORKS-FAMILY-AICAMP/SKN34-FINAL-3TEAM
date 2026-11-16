"""담당자 제공 11/12 c판 지시문 복사 제거.

공백 제외 10자 이상 문장의 바이그램 겹침이 0.9 이상이면 제거한다.
제거가 없으면 원문을 그대로 반환한다.
"""

import re

from .repeat_guard import split_sents

THRESHOLD = 0.9
# 이 비율 이상 겹치면 베낀 문장. 11/10 실제 글 5,000편: 0.9면 문장
# 0.44%·글 2.8%가
# 걸림(0.8이면 글 6.7%), 지시문 문장 자체는 1.0
MIN_CHARS = 10  # 이보다 짧은 문장은 판단 안 함


def _bigrams(s: str) -> set:
    s = re.sub(r"[\s\W_]+", "", s)
    return {s[i : i + 2] for i in range(len(s) - 1)}


def copy_ratio(sent: str, prompt_bigrams: set) -> float:
    b = _bigrams(sent)
    return len(b & prompt_bigrams) / len(b) if b else 0.0


def remove_copied(text: str, prompt: str, threshold: float = THRESHOLD) -> tuple[str, int]:
    """지시문을 베낀 문장을 뺀 글과 뺀 문장 수. 하나도 없으면 원래 글 그대로"""
    pb = _bigrams(prompt)
    sents = split_sents(text)
    keep = [
        s for s in sents if len(re.sub(r"\s", "", s)) < MIN_CHARS or copy_ratio(s, pb) < threshold
    ]
    n = len(sents) - len(keep)
    return (text, 0) if n == 0 else (" ".join(keep), n)
