"""M2 담당자 제공 content3_rule_1103.py (2026-11-03 v1.0.0) 기준 선택 보정."""

import math
import re

RULE_VERSION = "1.0.0"
W0, W_MODEL, W_RATIO = 0.9724, 0.197, 2.8891


def keyword_groups(keywords: list[str]) -> list[list[str]]:
    """괄호 밖 쉼표는 묶음 구분, 괄호 안 쉼표·슬래시는 같은 뜻 대체어."""
    out = []
    for term in re.split(r",\s*(?![^()]*\))", ", ".join(keywords)):
        term = term.strip()
        if not term:
            continue
        match = re.match(r"^(.*?)\((.*)\)$", term)
        alternatives = [match.group(1), *re.split(r"[,/]", match.group(2))] if match else [term]
        out.append([word.strip() for word in alternatives if word.strip()])
    return out


def keyword_ratio(text: str, keywords: list[str]) -> float:
    """공백을 무시하고 묶음별 하나 이상 일치 여부의 평균을 계산한다."""
    groups = keyword_groups(keywords)
    if not groups:
        return 0.0
    no_space = re.sub(r"\s+", "", text)
    hits = [any(re.sub(r"\s+", "", word) in no_space for word in group) for group in groups]
    return sum(hits) / len(groups)


def content3_score(model_raw: float, text: str, keywords: list[str]) -> tuple[float, int]:
    """정수는 응답용 소수 4자리 반올림 전 값에서 x.5 올림으로 계산한다."""
    raw = W0 + W_MODEL * model_raw + W_RATIO * keyword_ratio(text, keywords)
    raw = min(max(raw, 1.0), 5.0)
    return round(raw, 4), math.floor(raw + 0.5)
