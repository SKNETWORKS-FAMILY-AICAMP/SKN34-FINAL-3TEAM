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


def test_clean_drops_sentences_that_hint_at_scores_without_numbers() -> None:
    source = "나는 할머니가 주신 필통을 가장 아낀다. 필통은 파란색이고 곰 그림이 있다."
    text = (
        "자녀는 할머니가 주신 필통을 가장 아끼는 물건으로 골랐습니다. "
        "그러나 설명의 적절성에서 낮은 평가를 받았기 때문에, 의미를 더 설명하면 좋겠습니다. "
        "필통의 색과 그림을 구체적으로 적었습니다."
    )
    cleaned = checks.clean(text, source)
    assert "평가" not in cleaned
    assert cleaned.startswith("자녀는 할머니가 주신 필통을")
    assert cleaned.endswith("구체적으로 적었습니다.")
    for hint in (
        "이 글은 높게 평가될 만합니다.",
        "내용 항목에서 기준에 못 미칩니다.",
        "채점 기준으로 보면 짜임이 약합니다.",
        "평가 결과 표현이 단조롭습니다.",
    ):
        assert checks.clean(hint, source) == ""
        assert not checks.allowed(hint, source)


def test_score_hint_keeps_plain_observations_about_the_writing() -> None:
    source = "필통은 파란색이고 곰 그림이 있다. 좋다."
    text = "문장 사이 연결이 부족해 통일성이 떨어집니다. 표현이 다소 단조롭습니다."
    assert checks.clean(text, source) == text
    assert checks.allowed(text, source)


def test_clean_drops_level_talk_and_rubric_lists_but_keeps_single_terms() -> None:
    source = "필통은 파란색이고 곰 그림이 있다. 좋다."
    text = (
        "자녀는 할머니가 주신 필통을 골랐습니다. "
        "그러나 설명의 적절성, 구체성, 명료성, 통일성에서 모두 낮은 수준을 보이고 있습니다. "
        "표현은 높은 수준입니다. "
        "문장 사이 연결이 부족해 통일성이 떨어집니다."
    )
    assert checks.clean(text, source) == (
        "자녀는 할머니가 주신 필통을 골랐습니다. 문장 사이 연결이 부족해 통일성이 떨어집니다."
    )
    assert not checks.allowed("내용의 구체성, 명료성, 타당성을 더 살리면 좋겠습니다.", source)
    assert checks.allowed("구체성과 명료성을 더 살리면 좋겠습니다.", source)


def test_cleaned_drops_repeats_across_sections_and_counts_them() -> None:
    source = "필통은 파란색이고 곰 그림이 있다. 좋다."
    same = "필통의 색과 그림은 썼지만 그 물건이 왜 소중한지는 아직 드러나지 않습니다."
    near = "필통의 색과 그림은 썼지만, 그 물건이 왜 소중한지는 아직 드러나지 않아요."
    result = checks.cleaned(
        ExplanationDetail(
            analysis=f"자녀는 필통을 골랐습니다. {same}",
            improvement_points=f"{near} 좋다는 까닭을 덧붙이면 좋겠습니다.",
            next_steps=same,
        ),
        source,
    )
    assert result.sections == [
        ("상세 분석", f"자녀는 필통을 골랐습니다. {same}"),
        ("보완할 지점", "좋다는 까닭을 덧붙이면 좋겠습니다."),
    ]
    assert (result.sentences, result.repeated) == (5, 2)


def test_short_sentences_repeat_only_when_identical() -> None:
    result = checks.cleaned(
        ExplanationDetail(analysis="좋습니다. 좋았습니다.", next_steps="좋습니다."), ""
    )
    assert result.sections == [("상세 분석", "좋습니다. 좋았습니다.")]
    assert result.repeated == 1


def test_clean_drops_research_requests_a_child_cannot_do() -> None:
    source = "스마트폰을 오래 하면 눈이 나빠진다. 내 동생도 밤늦게까지 영상을 보았다."
    text = (
        "자녀는 눈 건강을 근거로 들었습니다. "
        "이 주장을 뒷받침할 수 있는 구체적인 예시나 데이터가 부족합니다. "
        "스마트폰 사용이 시력에 미치는 영향에 대한 연구 결과나 통계 자료를 제시하면 좋겠습니다. "
        "눈이 피곤했던 경험을 덧붙이면 좋겠습니다."
    )
    assert checks.clean(text, source) == (
        "자녀는 눈 건강을 근거로 들었습니다. 눈이 피곤했던 경험을 덧붙이면 좋겠습니다."
    )


def test_research_words_written_by_the_child_are_kept() -> None:
    source = "우리 반 친구들에게 설문 조사를 해서 데이터를 모았다."
    text = '자녀는 "우리 반 친구들에게 설문 조사를 해서 데이터를 모았다"라고 썼습니다.'
    assert checks.clean(text, source) == text


def test_clean_strips_inline_bold_markers() -> None:
    source = "창가 화분의 강낭콩은 잎이 초록색으로 크게 자랐다."
    text = '**명료성**: 자녀는 "창가 화분의 강낭콩은 잎이 초록색으로 크게 자랐다"라고 썼습니다.'
    assert checks.clean(text, source) == (
        '자녀는 "창가 화분의 강낭콩은 잎이 초록색으로 크게 자랐다"라고 썼습니다.'
    )
    labelled = "관찰이 좋습니다. 설명의 적절성: 결론을 더 풀어 쓰면 좋겠습니다."
    assert checks.clean(labelled, source) == "관찰이 좋습니다. 결론을 더 풀어 쓰면 좋겠습니다."
