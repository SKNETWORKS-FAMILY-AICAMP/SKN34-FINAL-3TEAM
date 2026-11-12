"""지시문 베끼기 검사 (11/10 저녁 새 파일, repeat_guard.py와 같은
방식, CPU) 학생 글 문장마다 지시문과 글자 2개 묶음(바이그램)이 얼마나 겹치는지
봄. 겹침 = (문장 바이그램 중 지시문에도 있는 것의 비율). 기준 이상인 문장 =
지시문을 거의 그대로 옮긴 문장 → 채점 전에 뺌. 쓰는 법:
text_for_score, n_copied = remove_copied(text,
prompt)
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
