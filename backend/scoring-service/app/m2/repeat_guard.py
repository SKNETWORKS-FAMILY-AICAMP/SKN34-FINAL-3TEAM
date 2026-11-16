"""담당자 제공 11/12 c판 반복 문장 제거.

반복 비율 0.1 이상이고 중복 문장이 4개 이상인 경우만 제거한다.
말을 바꾼 반복·주제 이탈은 이 규칙의 범위가 아니다.
"""

import re

THRESHOLD = 0.1
MIN_REPEATED = (
    4
    # 반복 문장이 4개 이상일 때만 (실제 글 잘못 걸림 93편 → 27편, 반복 붙인
    # 글은 그대로 100%)
)
MIN_SENT_CHARS = 5


def split_sents(text: str) -> list[str]:
    return [
        s.strip()
        for s in re.split(r"(?<=[.!?。])\s+|\n+", str(text))
        if len(s.strip()) >= MIN_SENT_CHARS
    ]


def _norm(s: str) -> str:
    """띄어쓰기·문장부호만 다른 문장도 같은 문장으로 봄"""
    return re.sub(r"[\s\W_]+", "", s)


def repeat_check(text: str, threshold: float = THRESHOLD, min_repeated: int = MIN_REPEATED) -> dict:
    """반환: rep_ratio(1 - 서로 다른 문장 수 / 문장 수), n_sents,
    n_repeated, flagged
    """
    s = [_norm(x) for x in split_sents(text)]
    s = [x for x in s if x]
    n = len(s)
    uniq = len(set(s))
    ratio = 0.0 if n < 2 else 1 - uniq / n
    return {
        "rep_ratio": round(ratio, 4),
        "n_sents": n,
        "n_repeated": n - uniq,
        "flagged": ratio >= threshold and (n - uniq) >= min_repeated,
    }


def remove_repeats(text: str) -> tuple[str, bool]:
    """11/10 추가. 반복 규칙(repeat_check)에 걸리면 같은 문장의 두 번째부터
    지운 글을, 안 걸리면 원래 글을 그대로 돌려줌. 반환: (채점에 쓸 글, 걸렸는지).
    지운 뒤 문장은 공백 한 칸으로 잇는다(줄바꿈은 사라짐). 근거(11/10, 서비스
    klue 3.1): 반복 붙인 글 300편에서 원래 글보다 정수 점수가 오른 칸
    8.6% → 0.2%, 실제 논술 글 중 걸리는 글 0.06% (claude/결과 기록
    - 11/10 M2 적용안 (새 정수 경계·반복 규칙 정책 전후).md)
    """
    if not repeat_check(text)["flagged"]:
        return text, False
    seen, keep = set(), []
    for s in split_sents(text):
        k = _norm(s)
        if k and k in seen:
            continue
        seen.add(k)
        keep.append(s)
    return " ".join(keep), True
