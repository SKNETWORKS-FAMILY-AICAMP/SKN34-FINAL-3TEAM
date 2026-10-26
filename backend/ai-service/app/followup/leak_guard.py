"""되묻기 질문의 정답·금지어·예시 답 유출 검사 (FN-JDG-06).

띄어쓰기·문장부호·대소문자 차이는 무시하고 비교. 결과는 유출 종류만 반환하고
유출된 내용은 반환하지 않음 (운영 로그에 정답·학생 원문 미기록, NFR-SEC-05).
"""

import re
import unicodedata

from app.followup.models import FollowupRubric

_IGNORED = re.compile(r"[\W_]+")


def _compact(text: str) -> str:
    return _IGNORED.sub("", unicodedata.normalize("NFC", text)).lower()


def find_leaks(question: str, rubric: FollowupRubric, example_overlap_chars: int) -> list[str]:
    compact_question = _compact(question)
    leaks = []
    if _contains_any(compact_question, rubric.answer_key):
        leaks.append("ANSWER_KEY")
    if _contains_any(compact_question, rubric.forbidden_terms):
        leaks.append("FORBIDDEN_TERM")
    if rubric.example_answer and _overlaps(
        compact_question, _compact(rubric.example_answer), example_overlap_chars
    ):
        leaks.append("EXAMPLE_ANSWER")
    return leaks


def _contains_any(compact_question: str, terms: list[str] | None) -> bool:
    return any(
        compact_term and compact_term in compact_question
        for compact_term in (_compact(term) for term in terms or [])
    )


def _overlaps(compact_question: str, compact_example: str, size: int) -> bool:
    """예시 답의 연속 size글자가 질문에 그대로 들어 있는지."""
    if len(compact_example) < size:
        return bool(compact_example) and compact_example in compact_question
    return any(
        compact_example[start : start + size] in compact_question
        for start in range(len(compact_example) - size + 1)
    )
