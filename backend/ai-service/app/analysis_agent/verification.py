"""LLM 답변의 숫자·인용 대조 (FN-AGT-06). 하나라도 어긋나면 규칙 응답 모드로 (P16).

- 숫자: 답변의 모든 아라비아 숫자가 계산 결과(개수·분자·분모·비율%)·기록 수·기간 날짜에 있어야 함.
  따옴표 인용과 미션 제목 안의 숫자는 원문 그대로라 빼고 셈. "세 번"처럼 한글로 쓴 수는 대조할 수
  없으므로 실패로 봄 (프롬프트에서 아라비아 숫자를 쓰도록 지시).
- 인용: 본문 따옴표 안 문장이 모두 원문에 그대로 있어야 함 (공백 차이만 허용).
  처음 들어맞는 원문을 근거로 연결하고, 같은 원문은 근거 하나로 (core가 중복 근거를 거부).
- 표현: 레벨·등급·점수·사고력 단정 금지 (FN-AGT-09, FN-RPT-08).
"""

import re
from dataclasses import dataclass

from app.analysis_agent.calculators import Computation
from app.analysis_agent.models import Evidence, Verification

NUMBER = re.compile(r"\d+(?:\.\d+)?")
QUOTED = re.compile(r"[\"“”]([^\"“”]+)[\"“”]|['‘’]([^'‘’]+)['‘’]|「([^」]+)」")
KOREAN_COUNT = re.compile(
    r"(?<![가-힣])(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|스무)\s?(번|개|건|가지|문장|회|시도)"
)
FORBIDDEN = ("레벨", "등급", "점수", "사고력", "IQ", "상위", "하위", "뒤처", "영재")
WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class VerifiedAnswer:
    verification: Verification
    evidence: list[Evidence]

    @property
    def passed(self) -> bool:
        v = self.verification
        return v.numbers_matched and v.quotes_matched and v.content_allowed


def verify(answer: str, computation: Computation) -> VerifiedAnswer:
    cited: dict[int, Evidence] = {}  # 원문 순서 → 근거 (원문마다 첫 인용 하나)
    quotes_ok = True
    for match in QUOTED.finditer(answer):
        quote = next(group for group in match.groups() if group).strip()
        index = next(
            (i for i, s in enumerate(computation.sources) if quote and _contains(s.text, quote)),
            None,
        )
        if index is None:
            quotes_ok = False
        elif index not in cited:
            cited[index] = computation.sources[index].evidence.model_copy(update={"quote": quote})
    evidence = list(cited.values())

    stripped = QUOTED.sub(" ", answer)
    for source in computation.sources:
        stripped = stripped.replace(source.evidence.mission_title, " ")
    allowed = allowed_numbers(computation)
    numbers_ok = not KOREAN_COUNT.search(stripped) and all(
        _normalize_number(number) in allowed for number in NUMBER.findall(stripped)
    )
    content_ok = not any(word in answer for word in FORBIDDEN)
    return VerifiedAnswer(
        Verification(
            numbers_matched=numbers_ok, quotes_matched=quotes_ok, content_allowed=content_ok
        ),
        evidence,
    )


def allowed_numbers(computation: Computation) -> set[str]:
    allowed = {str(computation.record_count), *computation.extra_numbers}
    for metric in computation.metrics:
        allowed.update(str(n) for n in (metric.count, metric.numerator, metric.denominator))
        if metric.value is not None:
            allowed.add(_normalize_number(f"{metric.value * 100:.1f}"))
            allowed.add(str(round(metric.value * 100)))
    return allowed


def _normalize_number(text: str) -> str:
    return text.rstrip("0").rstrip(".") if "." in text else text


def _contains(text: str, quote: str) -> bool:
    return WHITESPACE.sub(" ", quote).strip() in WHITESPACE.sub(" ", text)
