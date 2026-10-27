import pytest

from app.followup.leak_guard import find_leaks
from app.followup.models import FollowupRubric

RUBRIC = FollowupRubric.model_validate(
    {
        "elements": [{"elementId": "e1", "label": "까닭"}],
        "answerKey": ["열이 높은 쪽에서 낮은 쪽으로 이동"],
        "forbiddenTerms": ["전도", "Heat"],
        "exampleAnswer": "뜨거운 물의 열이 차가운 컵으로 옮겨 가서 컵이 따뜻해져요.",
    }
)


def leaks(question: str, student_answers: list[str] | None = None) -> list[str]:
    return find_leaks(question, RUBRIC, 12, student_answers or [])


def test_clean_question_passes() -> None:
    assert leaks("컵을 만졌을 때 왜 따뜻해졌는지 네 생각을 더 말해 볼까?") == []


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("열이 높은 쪽에서 낮은 쪽으로 이동한다는 걸 알아?", ["ANSWER_KEY"]),
        ("열이  높은쪽에서 낮은 쪽으로, 이동하는 건 뭘까?", ["ANSWER_KEY"]),  # 띄어쓰기·문장부호
        ("이걸 전도라고 하는데 왜 그럴까?", ["FORBIDDEN_TERM"]),
        ("HEAT가 뭘까?", ["FORBIDDEN_TERM"]),  # 대소문자
        ("뜨거운 물의 열이 차가운 컵으로 옮겨 간다면 어떻게 될까?", ["EXAMPLE_ANSWER"]),
    ],
)
def test_leaks_are_detected(question: str, expected: list[str]) -> None:
    assert leaks(question) == expected


def test_short_shared_phrase_with_example_is_allowed() -> None:
    # 예시 답과 11글자 이하로만 겹치면 유출로 보지 않음
    assert leaks("컵이 따뜻해져요라고 했는데 왜 그럴까?") == []


def test_empty_terms_are_ignored() -> None:
    rubric = FollowupRubric.model_validate(
        {"elements": [{"elementId": "e1", "label": "주장"}], "forbiddenTerms": ["", "  "]}
    )
    assert find_leaks("네 생각을 더 말해 볼까?", rubric, 12, []) == []


def test_echoing_student_own_words_is_not_example_leak() -> None:
    # 학생이 예시 답과 같은 말을 이미 썼고, 질문이 그 말을 되받음 (실제 Claude에서 재현된 경우)
    student = ["뜨거운 물의 열이 차가운 컵으로 옮겨 가서 그래요"]
    assert leaks("뜨거운 물의 열이 차가운 컵으로 옮겨 간다고 했는데 왜 그럴까?", student) == []


def test_example_content_beyond_student_words_is_still_leak() -> None:
    # 학생은 앞부분만 썼는데 질문이 예시 답의 뒷부분(학생이 안 쓴 내용)을 말함
    student = ["뜨거운 물의 열이 차가운 컵으로 옮겨 가서 그래요"]
    question = "컵으로 옮겨 가서 컵이 따뜻해져요라는 건 무슨 뜻일까?"
    assert leaks(question, student) == ["EXAMPLE_ANSWER"]


def test_forbidden_term_is_leak_even_if_student_used_it() -> None:
    assert leaks("전도라고 했는데 그게 뭘까?", ["이건 전도 때문이에요"]) == ["FORBIDDEN_TERM"]
