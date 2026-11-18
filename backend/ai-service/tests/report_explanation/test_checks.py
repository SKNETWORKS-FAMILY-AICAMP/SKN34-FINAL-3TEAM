from app.report_explanation import checks
from app.report_explanation.models import ExplanationDetail

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
SOURCE = "책을 빌리려면 버스를 타고 30분이나 가야 한다."


def test_numbers_only_when_they_appear_in_the_student_text() -> None:
    assert checks.allowed("버스로 30분 걸린다는 근거를 들었습니다.", SOURCE)
    assert not checks.allowed("근거를 3개 들었습니다.", SOURCE)
    assert not checks.allowed("5점 만점에 가까운 글입니다.", SOURCE)


def test_forbidden_words_preface_and_list_markers_are_rejected() -> None:
    assert not checks.allowed("사고력이 높은 글입니다.", SOURCE)
    assert not checks.allowed("안녕하세요, 학부모님. 글을 살펴봤습니다.", SOURCE)
    assert not checks.allowed("- 원인과 결과를 이어 써 보세요.", SOURCE)
    assert not checks.allowed("  ", SOURCE)
    assert checks.allowed("'왜 그렇게 생각했니?'라고 물어봐 주세요.", SOURCE)


def test_compose_keeps_titles_and_drops_null_improvement() -> None:
    detail = ExplanationDetail(
        analysis=" 근거를 들었습니다. ",
        improvement_points=None,
        next_steps="앞으로 까닭을 더 물어봐 주세요.",
    )
    assert checks.compose(checks.parts(detail)) == (
        "상세 분석\n근거를 들었습니다.\n\n개선 방안\n앞으로 까닭을 더 물어봐 주세요."
    )


def test_quote_is_student_sentence_with_most_shared_words_or_none() -> None:
    student = "나는 강아지를 키우고 싶다. 왜냐하면 강아지는 산책을 좋아해서 운동이 된다! 끝."
    explanation = "강아지가 산책으로 운동이 된다는 까닭을 들었음."
    expected = "왜냐하면 강아지는 산책을 좋아해서 운동이 된다!"
    assert checks.pick_quote(student, explanation) == expected
    assert checks.pick_quote(student, "글자를 바르게 썼음.") is None


def test_lenient_detail_ignores_extra_fields_and_joins_lists() -> None:
    raw = (
        '{"analysis": "근거를 들었습니다.", "additionalImprovements": "무시", '
        '"next_steps": ["물어봐 주세요.", "써 보게 해 주세요."]}'
    )
    detail = ExplanationDetail.model_validate_json(raw)
    assert detail.improvement_points is None
    assert detail.next_steps == "물어봐 주세요. 써 보게 해 주세요."


def test_clean_requotes_trims_and_drops_only_bad_sentences() -> None:
    source = "밤늦게까지 영상을 보다가 아침에 늦게 일어난 적이 있다. 30분 걸린다."
    generated = (
        '- "밤늦게까지 영상을 보다가 아침에 늦게 일어난 적이 있다. "라는 문장이 좋습니다. '
        '"어떤 책을 읽고 싶니?"라고 물어보세요. 사고력이 자랍니다. 근거를 3개 들었습니다. '
        '버스로 30분 걸린다고 썼습니다. . . " " " "'
    )
    assert checks.clean(generated, source) == (
        '"밤늦게까지 영상을 보다가 아침에 늦게 일어난 적이 있다."라는 문장이 좋습니다. '
        "'어떤 책을 읽고 싶니?'라고 물어보세요. 버스로 30분 걸린다고 썼습니다."
    )
    assert checks.clean("점수가 낮습니다.", source) == ""
    assert checks.clean(None, source) == ""


def test_parts_cleans_each_section_and_drops_empty_ones() -> None:
    detail = ExplanationDetail(
        analysis="근거를 들었습니다.",
        improvement_points="등급은 보통입니다.",
        next_steps="앞으로 물어봐 주세요.",
    )
    assert checks.parts(detail, SOURCE) == [
        ("상세 분석", "근거를 들었습니다."),
        ("개선 방안", "앞으로 물어봐 주세요."),
    ]


def test_clean_drops_a_trailing_fragment_cut_by_an_unescaped_quote() -> None:
    source = "처음에는 아무도 순서를 정하지 않았다."
    # 모델이 인용 부호를 이스케이프하지 않아 칸이 짧게 끊긴 형태(infra.md 9.13.9)
    assert checks.clean("처음에는 ", source) == ""
    assert checks.clean("근거를 들었습니다. 특히 ", source) == "근거를 들었습니다."
    assert checks.clean("'좋아요?'라고 물어보세요.", source) == "'좋아요?'라고 물어보세요."
    assert checks.clean('"처음에는 아무도 순서를 정하지 않았다."', source) == (
        '"처음에는 아무도 순서를 정하지 않았다."'
    )
    cut = ExplanationDetail(analysis="처음에는 ", improvement_points=None, next_steps="물어봐 ")
    assert checks.parts(cut, source) == []
