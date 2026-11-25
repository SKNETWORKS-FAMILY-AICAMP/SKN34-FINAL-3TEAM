"""Regression for paired #883 answers and a complete answer, using fixed model output."""

import json

import pytest

from app.llm.report import PlainTextOutput
from app.report_explanation.models import ExplanationRequest
from app.report_explanation.prompts import build_user
from app.report_explanation.staged import select_target
from tests.fakes import FakeLlm
from tests.report_explanation.test_service import BODY, active, detail, explain

BAG_QUESTION = (
    "비 오는 날 등굣길에 가방이 젖어서 속상했던 적이 있나요? 비닐, 종이, 천, 고무 같은 "
    "여러 물질의 성질을 생각해서, 비 오는 날 가방을 지켜 줄 물건을 하나 만들어 보세요. "
    "어떤 물질로 어떻게 만들지, 왜 그 물질을 골랐는지 써 보세요."
)
BAG_QUOTE = "종이를 접어서 지붕처럼 만들고 양옆을 가방 끈에 묶을 거예요"
BAG_TEXT = f"가방을 덮는 모자를 만들고 싶어요. {BAG_QUOTE}."
BAG_ADDED = "종이는 쉽게 접혀서 빗물이 가방 옆으로 흐르게 지붕 모양을 만들기 좋아요."
PHONE_QUESTION = (
    "지우는 쉬는 시간에 학교에서 휴대폰을 자유롭게 쓰게 해야 한다고 주장하며 "
    "두 가지 까닭을 말했어요.\n"
    "- 까닭 1: 급한 일이 있을 때 부모님께 바로 연락할 수 있다.\n"
    "- 까닭 2: 다른 학교 친구들도 다 쓰니까 우리도 써야 한다.\n"
    "지우의 까닭이 타당한지 따져 보고, 내 주장을 논술 틀에 맞춰 써 보세요."
)
PHONE_QUOTE = "다른 학교 친구들도 다 쓴다고 했지만, 제 생각은 달라요"
PHONE_ESSAY = {
    "claim": "쉬는 시간에 휴대폰을 자유롭게 쓰는 것에 반대해요.",
    "reasons": [
        "친구와 하던 놀이가 알림 때문에 끊길 수 있어요.",
        "급한 연락은 교무실에서 할 수 있어요.",
    ],
    "rebuttal": f"{PHONE_QUOTE}.",
}
PHONE_ADDED = "학교마다 상황이 달라서 다른 학교에서 쓴다는 사실만으로는 충분하지 않아요."


def criterion(label, requirement, quote=None, *, satisfied=False, required=True):
    return dict(
        label=label, requirement=requirement, quote=quote, satisfied=satisfied, required=required
    )


def essay_text(essay):
    return "\n".join((essay["claim"], *essay["reasons"], essay["rebuttal"]))


@pytest.mark.parametrize("revised", [False, True], ids=["original", "revised"])
def test_material_choice_paired_answers(revised):
    text = f"{BAG_TEXT} {BAG_ADDED}" if revised else BAG_TEXT
    body = {
        "grade": 4,
        "inputType": "NARRATIVE",
        "question": BAG_QUESTION,
        "text": text,
        "criteria": [
            criterion("재료", "만들 물건의 재료를 밝힘", "종이를", satisfied=True),
            criterion(
                "재료 선택 이유",
                "종이의 성질과 가방 보호 방법을 연결함",
                BAG_QUOTE,
                satisfied=revised,
            ),
        ],
    }
    assert_gap(
        body,
        detail(
            analysis="자녀는 종이를 지붕처럼 접어 가방 끈에 묶는 방법을 설명합니다.",
            improvement_points=(
                f'다만, "{BAG_QUOTE}"라고 쓴 뒤 종이를 고른 이유를 덧붙일 수 있어요.'
            ),
            next_steps="‘종이의 어떤 성질 때문에 지붕을 만들기 좋았을까?’라고 물어보세요.",
            gap_criterion=2,
            gap_quote=BAG_QUOTE,
        ),
        expected=not revised,
    )


@pytest.mark.parametrize("revised", [False, True], ids=["original", "revised"])
def test_phone_paired_answers_keep_question_speaker_and_essay_fields_separate(revised):
    essay = dict(PHONE_ESSAY)
    if revised:
        essay["rebuttal"] += f" {PHONE_ADDED}"
    body = {
        "grade": 5,
        "inputType": "ESSAY",
        "question": PHONE_QUESTION,
        "text": essay_text(essay),
        "essay": essay,
        "criteria": [
            criterion(
                "주장", "휴대폰 자유 사용에 대한 자기 입장을 밝힘", essay["claim"], satisfied=True
            ),
            criterion(
                "근거 평가",
                "지우의 타당하지 않은 까닭을 찾아 왜 타당하지 않은지 설명함",
                PHONE_QUOTE,
                satisfied=revised,
            ),
        ],
    }
    request = ExplanationRequest.model_validate(body)
    lines = build_user(request).splitlines()
    assert json.loads(lines[2]) == PHONE_QUESTION
    assert json.loads(lines[4]) == {
        "주장": essay["claim"],
        "까닭": essay["reasons"],
        "반박": essay["rebuttal"],
    }
    assert_gap(
        body,
        detail(
            analysis="자녀는 알림이 친구와의 놀이를 끊을 수 있다며 자유 사용에 반대해요. "
            "급한 연락에는 교무실이라는 대안을 냈어요.",
            improvement_points=f'다만, "{PHONE_QUOTE}"라고 했으니 왜 그 까닭이 성립하지 '
            "않는지 이어서 설명해 볼 수 있어요.",
            next_steps="‘우리 학교에서도 허용할지 정하려면 무엇을 살펴봐야 할까?’라고 물어보세요.",
            gap_criterion=2,
            gap_quote=PHONE_QUOTE,
        ),
        expected=not revised,
    )


def test_complete_dog_park_answer_uses_full_analysis_without_inventing_a_gap():
    essay = {
        "claim": "목줄을 하는 조건으로 공원에 반려견이 들어오게 해야 해요.",
        "reasons": [
            "동네 신문에 나온 설문을 보면 주민들 중 반려견과 공원을 함께 "
            "걷고 싶은 사람이 더 많았어요.",
            "보도에서 산책하면 걷는 사람과 자주 부딪히는데 공원에 잘 보이는 산책길을 만들면 "
            "서로 피해 갈 수 있어요.",
        ],
        "rebuttal": "개가 가까이 올까 걱정되는 어린이를 위해 놀이터 주위는 "
        "반려견이 들어오지 않게 표시하면 돼요.",
    }
    body = {
        "grade": 6,
        "inputType": "ESSAY",
        "question": "공원에 반려견 출입을 허용해야 할지 내 주장을 정하고, 까닭 두 가지와 "
        "반대 의견에 대한 내 답을 써 보세요.",
        "text": essay_text(essay),
        "essay": essay,
        "criteria": [
            criterion("주장", "허용에 대한 주장을 밝힘", satisfied=True),
            criterion("까닭", "주장을 뒷받침하는 까닭을 설명함", satisfied=True),
            criterion("다른 관점", "안전 우려에 답함", satisfied=True),
            criterion("좋은 생각", "놀이터 구역과 산책로를 이어 설명함", required=False),
        ],
    }
    assert_gap(
        body,
        detail(
            analysis="자녀는 목줄을 조건으로 공원에 반려견 출입을 허용하자고 제안했어요. "
            "신문 속 주민 의견으로 함께 산책하고 싶은 사람이 있다는 점을 짚었어요. "
            "산책길을 두어 보도에서 부딪히는 일을 줄일 수 있다고 설명했어요. "
            "놀이터 주변은 별도로 표시해 어린이의 안전 우려에도 답했어요.",
            improvement_points='다만, "놀이터 주위"와 산책길을 더 연결해 볼 수 있어요.',
            next_steps="‘산책길을 어디에 두면 좋을까?’라고 물어보세요.",
            gap_criterion=4,
            gap_quote="놀이터 주위",
        ),
        expected=False,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"requirement": None},
        {"quote": "이전 답안의 내용"},
        {"required": False},
    ],
)
def test_missing_requirement_conflicting_quote_or_optional_element_has_no_gap(change):
    body = {**BODY, "criteria": [{**BODY["criteria"][0], **change}]}
    assert_gap(body, detail(), expected=False)


def test_legacy_report_input_has_no_gap():
    body = {key: value for key, value in BODY.items() if key not in {"question", "criteria"}}
    assert_gap(body, detail(), expected=False)


def test_multiple_parent_questions_are_dropped_without_shortening_analysis():
    assert_gap(
        BODY,
        detail(next_steps="‘어떻게 할까?’라고 묻고 ‘무엇부터 해 볼까?’라고 물어보세요."),
        expected=False,
    )


def test_rejected_parent_question_keeps_analysis():
    assert_gap(
        BODY,
        detail(next_steps="‘통계 자료를 찾아볼까?’라고 물어보세요."),
        expected=False,
    )


def assert_gap(body, output, *, expected):
    target = select_target(ExplanationRequest.model_validate(body))
    if target is None:
        llm = FakeLlm(output)
    else:
        main = PlainTextOutput(text=f"상세 분석\n{output.analysis}")
        extra = PlainTextOutput(
            text=(f"보완할 지점\n{output.improvement_points}\n\n개선 방안\n{output.next_steps}")
        )
        llm = FakeLlm(main, extra, PlainTextOutput(text="아니오") if expected else extra)
    versions = active(f"explanation/grade-{body['grade']}/{body['inputType'].lower()}")
    result = explain(llm, body, versions)
    assert llm.requests[0].max_tokens == 1536
    assert result.explanation.text.split("\n\n")[0] == f"상세 분석\n{output.analysis}"
    assert ("보완할 지점" in result.explanation.text) is expected
    assert ("개선 방안" in result.explanation.text) is expected
