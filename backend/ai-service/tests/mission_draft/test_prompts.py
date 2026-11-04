import pytest
from pydantic import ValidationError

from app.llm.providers import strict_schema
from app.mission_draft import prompts
from tests.mission_draft.helpers import make_request


def test_user_prompt_has_standards_codes_limit_and_no_student_fields() -> None:
    text = prompts.build_user(make_request(), 200)
    assert "6국01-02: 의견을 제시하고 함께 조정하며 토의한다." in text
    assert "EVALUATE_CLAIM: 주장" in text
    assert "질문 글자 수 상한: 200자" in text
    assert "학년: 초5" in text
    for absent in ("학생 답", "이름", "studentId", "성취수준"):
        assert absent not in text


def test_level_text_is_sent_only_when_present() -> None:
    standards = [
        {
            "code": "6국01-02",
            "statement": "의견을 제시하고 함께 조정하며 토의한다.",
            "level": {"grade": "B", "text": "의견을 제시하고 조정할 수 있다."},
        }
    ]
    text = prompts.build_user(make_request(standards=standards), 200)
    assert "성취수준 B: 의견을 제시하고 조정할 수 있다." in text


def test_previous_failures_become_fix_instructions_once() -> None:
    failures = [
        {"check": "LEAK", "reason": "ANSWER_KEY"},
        {"check": "LEAK", "reason": "ANSWER_KEY"},
        {"check": "ELEMENT_CODE", "reason": "rubric.elements.code"},
        {"check": "AI_CALL", "reason": "AI_TIMEOUT"},
    ]
    text = prompts.build_user(make_request(previousFailures=failures), 200)
    assert text.count("정답을 쓰지 않는다") == 1
    assert "요소 code는 주어진 목록과 입력 방식 규칙을 지킨다" in text
    assert "형식에 맞게 다시 만든다" in text


def test_grade_range_and_input_guides() -> None:
    text = prompts.build_user(make_request(gradeMin=3, gradeMax=4, inputType="CHOICE"), 200)
    assert "학년: 초3~4" in text
    assert "ANSWER_KEY 하나만" in text
    assert set(prompts.INPUT_GUIDE) == {
        "CHOICE",
        "ORDERING",
        "CLASSIFICATION",
        "NARRATIVE",
        "SOLUTION_STEPS",
        "ESSAY",
    }


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"thinkingType": "CREATE"}, "CREATE_CONNECT는 들어가면 좋은 생각"),
        ({"thinkingType": "EVALUATE"}, "EVALUATE_PERSPECTIVE는 들어가면 좋은 생각"),
        ({"inputType": "ESSAY"}, "모두 필수, 들어가면 좋은 생각은 두지 않음"),
        ({"thinkingType": "SOLVE", "inputType": "SOLUTION_STEPS"}, "SOLVE_CHECK는 들어가면"),
        ({"thinkingType": "REFLECT"}, "REFLECT_CONNECT는 들어가면 좋은 생각"),
        ({"thinkingType": "ANALYZE"}, "ANALYZE_REASON은 들어가면 좋은 생각"),
    ],
)
def test_element_rule_follows_seed_by_type(overrides, expected) -> None:
    # 실측(#354): 0~1개 자유면 12건 모두 0개 → 데모 시드의 유형별 지정을 기본값으로
    assert "요소 규칙: " in prompts.build_user(make_request(**overrides), 200)
    assert expected in prompts.build_user(make_request(**overrides), 200)
    assert "정답 요소는 항상 false" in prompts.SYSTEM


def test_closed_inputs_have_no_element_rule() -> None:
    for input_type in ("CHOICE", "ORDERING", "CLASSIFICATION"):
        assert "요소 규칙" not in prompts.build_user(make_request(inputType=input_type), 200)


def test_output_schema_is_strict_with_api_field_names() -> None:
    schema = strict_schema(prompts.GeneratedDraft)
    assert schema["required"] == list(schema["properties"])
    assert {"sceneNote", "answerKey", "exampleAnswer", "forbiddenTerms"} <= set(
        schema["properties"]
    )


def test_request_rejects_bad_grades_and_empty_inputs() -> None:
    with pytest.raises(ValidationError):
        make_request(gradeMin=6, gradeMax=5)
    with pytest.raises(ValidationError):
        make_request(inputType="ESSAY", gradeMin=4, gradeMax=6)
    with pytest.raises(ValidationError):
        make_request(standards=[])
    with pytest.raises(ValidationError):
        make_request(elementCodes=[])
