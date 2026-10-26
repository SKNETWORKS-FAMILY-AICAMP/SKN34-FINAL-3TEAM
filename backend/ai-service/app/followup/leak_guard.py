"""되묻기 질문의 정답·금지어·예시 답 유출 검사 (FN-JDG-06).

띄어쓰기·문장부호·대소문자 차이는 무시하고 비교. 결과는 유출 종류만 반환하고
유출된 내용은 반환하지 않음 (운영 로그에 정답·학생 원문 미기록, NFR-SEC-05).

예시 답과 겹치더라도 학생이 이번 시도에서 이미 쓴 말을 되받은 부분은 유출로 보지 않음.
정답 키·금지어는 학생이 썼더라도 질문에 쓰면 유출.
"""

import re
import unicodedata

from app.followup.models import FollowupRubric

_IGNORED = re.compile(r"[\W_]+")


def _compact(text: str) -> str:
    return _IGNORED.sub("", unicodedata.normalize("NFC", text)).lower()


def find_leaks(
    question: str,
    rubric: FollowupRubric,
    example_overlap_chars: int,
    student_answers: list[str],
) -> list[str]:
    compact_question = _compact(question)
    leaks = []
    if _contains_any(compact_question, rubric.answer_key):
        leaks.append("ANSWER_KEY")
    if _contains_any(compact_question, rubric.forbidden_terms):
        leaks.append("FORBIDDEN_TERM")
    if rubric.example_answer and _overlaps(
        compact_question,
        _compact(rubric.example_answer),
        [_compact(answer) for answer in student_answers],
        example_overlap_chars,
    ):
        leaks.append("EXAMPLE_ANSWER")
    return leaks


def _contains_any(compact_question: str, terms: list[str] | None) -> bool:
    return any(
        compact_term and compact_term in compact_question
        for compact_term in (_compact(term) for term in terms or [])
    )


def _overlaps(
    compact_question: str, compact_example: str, compact_answers: list[str], size: int
) -> bool:
    """예시 답의 연속 size글자가 질문에 있고, 학생 답에는 없는지."""
    if len(compact_example) < size:
        fragments = [compact_example] if compact_example else []
    else:
        fragments = [
            compact_example[start : start + size]
            for start in range(len(compact_example) - size + 1)
        ]
    return any(
        fragment in compact_question and not any(fragment in answer for answer in compact_answers)
        for fragment in fragments
    )
