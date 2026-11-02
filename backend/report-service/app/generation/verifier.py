"""Conservative numeric-subset and exact-source quote checks; no ability diagnosis."""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.clients.ai_client import NarrativeResponse
from app.generation.models import GenerationResult, ItemType
from app.generation.records import EvidenceRecord

NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")
KOREAN_COUNT = re.compile(
    r"(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|스무)\s*(?:번|회|개|건|문장|글자)"
)
UNSUPPORTED_CLAIM = re.compile(r"레벨|등급|순위|점수|사고력.{0,12}향상|상위\s*\d")
QUOTED = re.compile(r'[“「『"]([^”」』"]+)[”」』"]')


@dataclass(frozen=True)
class Verification:
    numbers_matched: bool
    quotes_matched: bool
    content_allowed: bool

    @property
    def passed(self):
        return self.numbers_matched and self.quotes_matched and self.content_allowed

    def payload(self):
        return {
            "numbersMatched": self.numbers_matched,
            "quotesMatched": self.quotes_matched,
            "contentAllowed": self.content_allowed,
        }


def allowed_numbers(result: GenerationResult) -> set[Decimal]:
    numbers = set()
    for item in result.items:
        if item.type == ItemType.METRIC:
            for key in ("count", "numerator", "denominator", "value"):
                value = item.payload.get(key)
                if value is not None:
                    number = Decimal(str(value))
                    numbers.add(number)
                    numbers.add(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                    if key == "value":
                        for precision in ("1", "0.01"):
                            numbers.add(
                                (number * 100).quantize(Decimal(precision), rounding=ROUND_HALF_UP)
                            )
        elif item.type == ItemType.CHANGE:
            numbers.update(
                Decimal(str(n)) for pair in item.payload["counts"].values() for n in pair
            )
    return numbers


class ReportVerifier:
    def verify(
        self,
        response: NarrativeResponse,
        result: GenerationResult,
        evidence: tuple[EvidenceRecord, ...],
    ) -> Verification:
        by_id = {e.answer_id: e for e in evidence}
        quoted = True
        text = response.narrative.text + "\n" + response.evening_question
        quoted_phrases = QUOTED.findall(text)
        for citation in response.cited_quotes:
            original = by_id.get(citation.answer_id)
            if (
                original is None
                or not original.available
                or (original.attempt_id, original.version)
                != (citation.attempt_id, citation.answer_version)
                or (original.text is None or citation.quote not in original.text)
            ):
                quoted = False
            text = text.replace(citation.quote, "")
        if any(
            quoted_text not in {c.quote for c in response.cited_quotes}
            for quoted_text in quoted_phrases
        ):
            quoted = False
        numbers = all(
            Decimal(token.replace(",", "")) in allowed_numbers(result)
            for token in NUMBER.findall(text)
        ) and not KOREAN_COUNT.search(text)
        numbers = numbers and not re.search(r"\d[eE][+-]?\d", text)
        numbers = numbers and not any(c.isnumeric() and c not in "0123456789" for c in text)
        return Verification(bool(numbers), quoted, not bool(UNSUPPORTED_CLAIM.search(text)))
