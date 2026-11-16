"""담당자 제공 11/12 c판 글 정리 규칙.

논술: 칸 이름 → 지시문 복사 → 반복 제거 → 공백 제외 길이 계산.
서술: 지시문 복사 → 반복 제거. 서술 10자 하한은 service에서 적용한다.
변경이 없으면 원문과 줄바꿈을 그대로 유지한다.
"""

import re
from dataclasses import dataclass

from .prompt_guard import remove_copied
from .repeat_guard import remove_repeats

MIN_CHARS = 100
# learning-service AnswerContent.plainText 기본 칸
# 이름 (미션 inputTemplate이 4칸이면 그 이름이 대신 붙음 →
# labels로 넘기기)
ESSAY_LABELS = ("주장", "까닭 1", "까닭 2", "반대 의견에 답하기")


@dataclass
class GuardResult:
    text: str  # 채점에 쓸 글
    copied: int  # 뺀 지시문 베낀 문장 수
    repeated: bool  # 반복 규칙에 걸려 반복 문장을 뺐는지
    chars: int  # 정리한 글의 공백 뺀 글자 수
    too_short: bool  # True면 점수를 내지 않음 (논술만)
    labels_removed: int = 0  # 뺀 칸 이름 수 (논술)
    short: bool = False  # 100자 미만 ("짧은 답" 안내용, 서술은 점수는 냄)


def strip_labels(text: str, labels=ESSAY_LABELS) -> tuple[str, int]:
    """줄 맨 앞의 '칸 이름:'만 뺌 (칸 이름 뒤 공백 허용). 줄바꿈과 나머지 글은
    그대로
    """
    names = "|".join(re.escape(n).replace(r"\ ", r"\s*") for n in labels if n)
    if not names:
        return text, 0
    out, n = re.subn(rf"(?m)^[ \t]*(?:{names})[ \t]*[:：][ \t]*", "", text)
    return out, n


def _clean(text: str, prompt: str):
    t, copied = remove_copied(text, prompt) if prompt else (text, 0)
    t, repeated = remove_repeats(t)
    return t, copied, repeated, len(re.sub(r"\s", "", t))


def prepare_essay(
    text: str, prompt: str, min_chars: int = MIN_CHARS, labels=ESSAY_LABELS
) -> GuardResult:
    t, nl = strip_labels(text, labels)
    t, copied, repeated, n = _clean(t, prompt)
    return GuardResult(t, copied, repeated, n, n < min_chars, nl, n < min_chars)


def prepare_narrative(text: str, prompt: str, short_chars: int = MIN_CHARS) -> GuardResult:
    t, copied, repeated, n = _clean(text, prompt)
    return GuardResult(t, copied, repeated, n, False, 0, n < short_chars)
