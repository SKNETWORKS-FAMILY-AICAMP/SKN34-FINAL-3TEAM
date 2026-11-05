import pytest

from app.mission_draft import checks
from app.mission_draft.models import Draft
from app.mission_draft.prompts import GeneratedAnswerKey, GeneratedChoice
from tests.mission_draft.helpers import (
    choice_draft,
    classification_draft,
    make_request,
    narrative_draft,
)

LIMITS = {3: 200, 4: 200, 5: 200, 6: 200}


def run(generated, **request) -> list[tuple[str, str]]:
    draft = Draft.model_validate(generated.model_dump())
    return [(f.check, f.reason) for f in checks.check(draft, make_request(**request), LIMITS, 12)]


def key(**fields) -> GeneratedAnswerKey:
    body = {"choiceIds": None, "assignments": None, "finalAnswer": None, **fields}
    return GeneratedAnswerKey(**body)


def test_complete_narrative_and_choice_drafts_pass() -> None:
    assert run(narrative_draft()) == []
    assert run(choice_draft(), inputType="CHOICE") == []
    assert run(classification_draft(), inputType="CLASSIFICATION") == []


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"title": " "}, "TITLE"),
        ({"question": ""}, "QUESTION"),
        ({"elements": []}, "ELEMENTS"),
        ({"exampleAnswer": None}, "EXAMPLE_ANSWER"),
        ({"hints": [" "]}, "HINTS"),
    ],
)
def test_required_items_for_narrative(overrides, reason) -> None:
    assert ("REQUIRED", reason) in run(narrative_draft(**overrides))


@pytest.mark.parametrize(
    ("input_type", "overrides", "reason"),
    [
        ("CHOICE", {"choices": [GeneratedChoice(id="c1", label="물")]}, "CHOICES"),
        ("CHOICE", {"answerKey": None}, "ANSWER_KEY"),
        ("ORDERING", {"answerKey": key(choiceIds=[])}, "ANSWER_KEY"),
        ("CLASSIFICATION", {"categories": None}, "CATEGORIES"),
        ("CLASSIFICATION", {"answerKey": None}, "ANSWER_KEY"),
    ],
)
def test_required_items_for_closed_types(input_type, overrides, reason) -> None:
    assert ("REQUIRED", reason) in run(choice_draft(**overrides), inputType=input_type)


def test_solution_steps_need_final_answer_but_not_example() -> None:
    steps = narrative_draft(
        exampleAnswer=None,
        answerKey=key(finalAnswer="30"),
        question="윗변 4 m, 아랫변 8 m, 높이 5 m인 사다리꼴 화단의 넓이를 구해 보자.",
    )
    assert run(steps, inputType="SOLUTION_STEPS") == []
    missing = narrative_draft(exampleAnswer=None, answerKey=None)
    assert ("REQUIRED", "ANSWER_KEY") in run(missing, inputType="SOLUTION_STEPS")


def test_question_length_limit_uses_youngest_grade() -> None:
    assert ("QUESTION_LENGTH", "TOO_LONG") in run(narrative_draft(question="가" * 201))
    assert run(narrative_draft(question="가" * 200)) == []
    draft = Draft.model_validate(narrative_draft(question="가" * 150).model_dump())
    failures = checks.check(draft, make_request(gradeMin=3, gradeMax=6), {3: 120, 6: 200}, 12)
    assert [(f.check, f.reason) for f in failures] == [("QUESTION_LENGTH", "TOO_LONG")]


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"question": "집중력 향상에 도움이 될까?"}, "FORBIDDEN_TERM"),
        ({"guide": "쉬는 시간이 길면 친구와 더 오래 놀고 다음 수업에 더 집중"}, "EXAMPLE_ANSWER"),
        ({"hints": ["집중력 향상을 떠올려 봐"]}, "FORBIDDEN_TERM"),
    ],
)
def test_leaks_in_question_guide_and_hints(overrides, reason) -> None:
    assert ("LEAK", reason) in run(narrative_draft(**overrides))


def test_example_answer_restating_question_is_not_a_leak() -> None:
    # 실측(#354): 풀이 예시 답이 질문 조건을 옮겨 써 12글자가 겹친 오탐
    question = "가로 12cm, 세로 8cm인 종이에서 가로 4cm, 세로 3cm인 직사각형을 잘라 냈어요."
    example = "가로 4cm, 세로 3cm인 직사각형의 넓이를 빼면 돼요."
    assert run(narrative_draft(question=question, exampleAnswer=example)) == []
    hint = narrative_draft(question=question, exampleAnswer=example, hints=[question])
    assert run(hint) == []
    told = narrative_draft(question=question, exampleAnswer=example, hints=["넓이를 빼면 돼요"])
    assert ("LEAK", "EXAMPLE_ANSWER") not in run(told)  # 12글자 미만
    leaked = narrative_draft(
        question=question, exampleAnswer=example, hints=["직사각형의 넓이를 빼면 돼요"]
    )
    assert ("LEAK", "EXAMPLE_ANSWER") in run(leaked)


def test_choice_answer_label_in_question_is_a_leak() -> None:
    leaked = choice_draft(question="물이 부족해서 시든 걸까? 무엇 때문일까?")
    assert ("LEAK", "ANSWER_KEY") in run(leaked, inputType="CHOICE")


def test_numeric_final_answer_uses_number_boundaries() -> None:
    base = {"exampleAnswer": None, "answerKey": key(finalAnswer="30")}
    inside = narrative_draft(question="300원으로 공책을 사요. 남은 돈은 얼마일까?", **base)
    assert run(inside, inputType="SOLUTION_STEPS") == []
    exact = narrative_draft(question="넓이가 30 m²인지 확인해 보자.", **base)
    assert ("LEAK", "ANSWER_KEY") in run(exact, inputType="SOLUTION_STEPS")


def test_ordering_key_is_not_turned_into_text() -> None:
    ordering = choice_draft(
        answerKey=key(choiceIds=["c2", "c1", "c3"]),
        question="햇빛·물·흙을 식물이 자라는 데 필요한 순서로 놓아 보자.",
    )
    assert run(ordering, inputType="ORDERING") == []
