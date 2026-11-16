from app.report_explanation import checks
from app.report_explanation.models import ExplanationRequest

NARRATIVE = {
    "hol": 4,
    "task_1": 3,
    "content_1": 3,
    "content_2": 5,
    "content_3": 3,
    "organization_1": 2,
    "organization_2": 3,
    "expression_1": 5,
    "expression_2": 2,
}


def request(scores: dict[str, int], input_type: str = "NARRATIVE") -> ExplanationRequest:
    return ExplanationRequest.model_validate(
        {"grade": 5, "inputType": input_type, "text": "글", "scores": scores}
    )


def test_highest_and_lowest_items_with_table_order_on_ties_and_no_total() -> None:
    targets = checks.select_items(request({**NARRATIVE, "hol": 4}))
    assert [(t.role, t.key, t.label, t.score) for t in targets] == [
        ("STRENGTH", "content_2", "구체성", 5),  # expression_1도 5점이지만 표에서 앞
        ("DISCUSS", "organization_1", "연결성", 2),  # expression_2도 2점이지만 표에서 앞
    ]


def test_same_score_everywhere_gives_one_item_by_midpoint() -> None:
    high = checks.select_items(request({key: 3 for key in NARRATIVE}))
    assert [(t.role, t.key) for t in high] == [("STRENGTH", "task_1")]
    low = checks.select_items(request({"org": 1, "cont": 1, "exp": 1}, "ESSAY"))
    assert [(t.role, t.key, t.label) for t in low] == [("DISCUSS", "org", "구성")]


def test_clean_drops_sentences_with_numbers_or_forbidden_words_and_keeps_two() -> None:
    generated = (
        "처음과 끝이 이어지도록 썼음. 그래서 4점을 줌. 점수가 높음. "
        "까닭을 두 가지 들었음. 예를 더 들면 좋겠음."
    )
    assert checks.clean(generated) == ["처음과 끝이 이어지도록 썼음.", "까닭을 두 가지 들었음."]
    assert checks.clean("5점 만점에 3점. 등급은 보통.") == []


def test_compose_uses_parent_template() -> None:
    text = checks.compose([("STRENGTH", ["예를 잘 들었음."]), ("DISCUSS", ["끝맺음이 짧음."])])
    assert text == "잘한 점: 예를 잘 들었음.\n함께 이야기해 볼 점: 끝맺음이 짧음."


def test_quote_is_student_sentence_with_most_shared_words_or_none() -> None:
    student = "나는 강아지를 키우고 싶다. 왜냐하면 강아지는 산책을 좋아해서 운동이 된다! 끝."
    explanation = "강아지가 산책으로 운동이 된다는 까닭을 들었음."
    expected = "왜냐하면 강아지는 산책을 좋아해서 운동이 된다!"
    assert checks.pick_quote(student, explanation) == expected
    assert checks.pick_quote(student, "글자를 바르게 썼음.") is None
