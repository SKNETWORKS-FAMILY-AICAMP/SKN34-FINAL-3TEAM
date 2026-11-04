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
    return find_text_leaks(
        question,
        rubric.answer_key,
        rubric.forbidden_terms,
        rubric.example_answer,
        example_overlap_chars,
        student_answers,
    )


def find_text_leaks(
    text: str,
    answer_key: list[str] | None,
    forbidden_terms: list[str] | None,
    example_answer: str | None,
    example_overlap_chars: int,
    student_answers: list[str],
) -> list[str]:
    """find_leaks와 같은 검사를 기준표 객체 없이 (미션 초안 검사 #354가 학생 답 없이 씀)."""
    compact_question = _compact(text)
    leaks = []
    if _contains_any(compact_question, answer_key):
        leaks.append("ANSWER_KEY")
    if _contains_any(compact_question, forbidden_terms):
        leaks.append("FORBIDDEN_TERM")
    if example_answer and _overlaps(
        compact_question,
        _compact(example_answer),
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
