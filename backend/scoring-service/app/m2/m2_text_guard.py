"""M2 채점 전 글 정리 (11/12 c판, scoring-service 연결용) —
논술·서술 둘 다 논술 prepare_essay: ① 칸 이름 빼기("주장: " 등,
서비스 plainText 형식) → ② 지시문 베낀 문장
빼기(prompt_guard.remove_copied) → ③ 같은 문장 반복
빼기(repeat_guard.remove_repeats) → 100자 미만이면
too_short(점수 안 냄) 서술 prepare_narrative: ② → ③,
100자 미만이어도 점수는 냄(too_short는 항상 False),
short=True로 "짧은 답" 표시만 - 칸 이름을 빼는 이유: 학습 글(AI
Hub)에는 칸 이름이 없음. 붙이면 정수 점수 5~8%가 한 단계 내려감(11/12
VL 초4~6 481편). 줄바꿈은 점수에 영향 없음(정수 99.6~100% 같음) →
줄바꿈은 두고 칸 이름만 뺌 - 논술 100자: 학습 글(AI Hub 545) 가장
짧은 글 138자(초4~6 1% 지점 157자) - 서술 100자: 학습 글(AI
Hub 서술) 원본부터 100자 이상만 있음. 100자 미만으로 줄인 글도 점수가 오른
경우 2~3%뿐이라 점수는 냄 아무것도 안 걸리면 원래 글 그대로 돌려줌. 모델 입력
첫 문장은 그대로("[학년] 초N [글 종류] …" / "[학년] 초N [핵심어]
…") 쓰는 법: from m2_text_guard import
prepare_essay, prepare_narrative g =
prepare_essay(request.text, request.prompt) # 논술
(ESSAY) g = prepare_narrative(request.text,
request.prompt) # 서술 (NARRATIVE) if g.too_short:
점수 내지 않음 + 안내 (논술만 생김) else: g.text로 채점.
g.copied > 0 / g.repeated / g.short면 점수와 함께 안내
문구 긴 글은 m2_long_input.encode_head_tail로 토큰화 (앞 +
끝을 같이 읽음)
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
