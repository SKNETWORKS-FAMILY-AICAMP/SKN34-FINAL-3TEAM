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


def leaks(question: str) -> list[str]:
    return find_leaks(question, RUBRIC, example_overlap_chars=12)


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
    assert find_leaks("네 생각을 더 말해 볼까?", rubric, 12) == []
