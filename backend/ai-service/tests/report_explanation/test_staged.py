import pytest

from app.llm.report import PlainTextOutput
from tests.fakes import FakeLlm
from tests.report_explanation.test_service import explain

ANALYSIS = (
    '자녀는 "컵의 물 온도는 점점 올라가고 그릇의 물 온도는 점점 내려갔어요"라고 적었어요. '
    "두 물의 온도가 반대로 변한 까닭을 열의 이동으로 설명했어요."
)
STRENGTH = (
    "'그릇의 물은 열을 잃어 식고, 컵의 물은 열을 얻어 따뜻해졌어요'라는 문장은 "
    "온도 변화와 열의 이동을 잘 연결하여 설명하고 있습니다."
)
ADVICE = "열이 이동할 때의 관찰을 더 떠올려 볼 수 있도록 도와주세요."
QUESTION = "열이 이동하는 과정에서 어떤 변화를 더 관찰할 수 있었나요?"
CUP = {
    "grade": 5,
    "inputType": "NARRATIVE",
    "topic": "따뜻해진 컵의 비밀",
    "question": "관찰한 물의 온도 변화를 근거로 그 까닭을 설명해 보세요.",
    "text": (
        "컵의 물 온도는 점점 올라가고 그릇의 물 온도는 점점 내려갔어요. "
        "그릇의 물은 열을 잃어 식고, 컵의 물은 열을 얻어 따뜻해졌어요."
    ),
    "criteria": [
        {
            "label": "온도 변화",
            "requirement": "두 물의 온도 변화를 설명함",
            "required": True,
            "satisfied": True,
        },
        {
            "label": "까닭 잇기",
            "requirement": "관찰한 온도 변화와 열의 이동을 이어 설명함",
            "required": False,
            "satisfied": True,
            "quote": "그릇의 물은 열을 잃어 식고, 컵의 물은 열을 얻어 따뜻해졌어요",
        },
    ],
}


@pytest.mark.parametrize("verdict", ["아니오", "예", "판단하기 어려움"])
def test_completed_cup_answer_expands_a_strength_and_checks_the_question(verdict):
    llm = FakeLlm(
        PlainTextOutput(text=f"### 상세 분석\n{ANALYSIS} 더 구체적인 내용을 덧붙이면 좋겠습니다."),
        PlainTextOutput(text=f"보완할 지점\n{STRENGTH}\n\n개선 방안\n{ADVICE} '{QUESTION}'"),
        PlainTextOutput(text=verdict),
    )
    result = explain(llm, CUP).explanation.text
    assert result.startswith(f"상세 분석\n{ANALYSIS}\n\n보완할 지점\n{STRENGTH}")
    assert "덧붙이면 좋겠습니다." not in result
    assert f"개선 방안\n{ADVICE}" in result
    assert (QUESTION in result) is (verdict == "아니오")
    analysis, coaching, judge = llm.requests
    assert all(request.output is PlainTextOutput for request in (analysis, coaching, judge))
    assert analysis.max_tokens == coaching.max_tokens == 1536
    assert analysis.timeout > 0 and coaching.timeout > 0
    assert "관찰한 온도 변화와 열의 이동을 이어 설명함" in coaching.user
    assert "자녀는 이미 이 부분을 잘 썼습니다" in coaching.user
    assert QUESTION in judge.user


def test_supplement_format_failure_retries_then_keeps_the_valid_analysis():
    llm = FakeLlm(
        PlainTextOutput(text=f"상세 분석\n{ANALYSIS}"),
        PlainTextOutput(text="보완할 지점\n" + STRENGTH),
        PlainTextOutput(text="답변이 중간에 끊겼어요."),
    )
    assert explain(llm, CUP).explanation.text == f"상세 분석\n{ANALYSIS}"
    assert [req.repetition_penalty for req in llm.requests] == [None, None, 1.1]


def test_missing_question_is_generated_and_checked_separately():
    llm = FakeLlm(
        PlainTextOutput(text=f"상세 분석\n{ANALYSIS}"),
        PlainTextOutput(text=f"보완할 지점\n{STRENGTH}\n\n개선 방안\n{ADVICE}"),
        PlainTextOutput(text=QUESTION),
        PlainTextOutput(text="아니오"),
    )
    assert explain(llm, CUP).explanation.text.endswith(f"'{QUESTION}'")
    assert "[생각을 이어 갈 기준]" in llm.requests[2].user
    assert QUESTION in llm.requests[3].user
