"""미션 초안 ai 검사 (api-spec 4.2, class-diagram 5.4 DraftChecks, #354).

ai는 REQUIRED·QUESTION_LENGTH·LEAK만 본다. 성취기준 실재·요소 code 규칙·입력 방식 모양
(선택지·정답 키가 서로 맞는지)은 성취기준 표와 게시 검사 규칙을 가진 learning이 본다
(learning.md 21절 검사 분담).
reason은 learning이 다음 시도의 previousFailures로 돌려주는 영문 코드다.
"""

import re

from app.followup.leak_guard import find_text_leaks
from app.mission_draft.models import Draft, Failure, MissionDraftRequest

CHOICE_TYPES = {"CHOICE", "ORDERING", "CLASSIFICATION"}
EXAMPLE_TYPES = {"NARRATIVE", "ESSAY"}
MIN_CHOICES = 2
MIN_CATEGORIES = 2
_DIGITS = re.compile(r"\d+")


def check(
    draft: Draft,
    request: MissionDraftRequest,
    max_question_chars: dict[int, int],
    example_overlap_chars: int,
) -> list[Failure]:
    failures = [Failure(check="REQUIRED", reason=r) for r in _required(draft, request)]
    limit = question_limit(max_question_chars, request.grade_min)
    if len(draft.question.strip()) > limit:
        failures.append(Failure(check="QUESTION_LENGTH", reason="TOO_LONG"))
    failures += [Failure(check="LEAK", reason=r) for r in _leaks(draft, example_overlap_chars)]
    return failures


def question_limit(max_question_chars: dict[int, int], grade: int) -> int:
    """학년 범위의 가장 낮은 학년 값(어린 학생 기준). 설정에 없으면 가장 작은 값."""
    return max_question_chars.get(grade, min(max_question_chars.values()))


def _required(draft: Draft, request: MissionDraftRequest) -> list[str]:
    missing = []
    if not draft.title.strip():
        missing.append("TITLE")
    if not draft.question.strip():
        missing.append("QUESTION")
    if not draft.elements or any(not e.code.strip() or not e.label.strip() for e in draft.elements):
        missing.append("ELEMENTS")
    key = draft.answer_key
    if request.input_type in CHOICE_TYPES:
        if len([c for c in draft.choices or [] if c.id.strip() and c.label.strip()]) < MIN_CHOICES:
            missing.append("CHOICES")
        if request.input_type == "CLASSIFICATION":
            categories = [c for c in draft.categories or [] if c.id.strip() and c.label.strip()]
            if len(categories) < MIN_CATEGORIES:
                missing.append("CATEGORIES")
            if key is None or not key.assignments:
                missing.append("ANSWER_KEY")
        elif key is None or not key.choice_ids:
            missing.append("ANSWER_KEY")
    final_answer = (key.final_answer or "").strip() if key else ""
    if request.input_type == "SOLUTION_STEPS" and not final_answer:
        missing.append("ANSWER_KEY")
    if request.input_type in EXAMPLE_TYPES and not (draft.example_answer or "").strip():
        missing.append("EXAMPLE_ANSWER")
    if not any(h.strip() for h in draft.hints):
        missing.append("HINTS")
    return missing


def _leaks(draft: Draft, example_overlap_chars: int) -> list[str]:
    """질문·안내·생각 열기 질문(학생에게 보이는 글)에 정답 키·금지어·예시 답이 드러나는지.

    예시 답은 질문의 조건을 옮겨 쓰기 마련이라(풀이의 "가로 8cm, 세로 3cm인 직사각형")
    질문은 예시 답과 비교하지 않고, 안내·생각 열기 질문은 질문에 이미 있는 글을 빼고
    비교한다. 되묻기가 학생 답에 있는 글을 빼는 것과 같다. 정답 키·금지어는 셋 다 본다.
    """
    answers, numeric = answer_texts(draft)
    found = find_text_leaks(draft.question, answers, draft.forbidden_terms, None, 0, [])
    for text in [draft.guide or "", *draft.hints]:
        found += find_text_leaks(
            text,
            answers,
            draft.forbidden_terms,
            draft.example_answer,
            example_overlap_chars,
            [draft.question],
        )
    for text in [draft.question, draft.guide or "", *draft.hints]:
        if numeric and any(has_number(text, n) for n in numeric):
            found.append("ANSWER_KEY")
    return list(dict.fromkeys(found))


def answer_texts(draft: Draft) -> tuple[list[str], list[str]]:
    """정답 키를 글로 바꿈. 고르기는 정답 선택지 이름, 풀이는 최종 답.

    순서·분류는 한 낱말로 정답을 나타낼 수 없어 제외한다. 숫자뿐인 최종 답은
    다른 숫자 안의 일부(30과 300)를 정답으로 보지 않게 따로 숫자 경계로 비교한다.
    """
    key = draft.answer_key
    if key is None:
        return [], []
    texts: list[str] = []
    numeric: list[str] = []
    if key.choice_ids and len(key.choice_ids) == 1:
        labels = {c.id: c.label for c in draft.choices or []}
        if key.choice_ids[0] in labels:
            texts.append(labels[key.choice_ids[0]])
    final = (key.final_answer or "").strip()
    if final:
        (numeric if final.isdigit() else texts).append(final)
    return texts, numeric


def has_number(text: str, number: str) -> bool:
    return any(match.group() == number for match in _DIGITS.finditer(text))
