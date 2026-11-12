"""검사·본문 조립 규칙 (#565, api-spec 4.2.6)."""

import pytest

from app.memory_explanation import checks
from app.memory_explanation.models import MemoryEvidence
from app.memory_explanation.prompts import GeneratedSentence as S

EVIDENCE = [
    MemoryEvidence(
        no=1,
        theme_title="동물 친구들의 집",
        mission_question="고양이가 살기 좋은 집을 설계해 보세요.",
        answer_excerpt="고양이는 높은 곳을 좋아해서 계단을 만들었다.",
        week_label="10월 둘째 주",
    ),
    MemoryEvidence(
        no=3,
        theme_title="사라진 별자리",
        mission_question="별자리를 찾는 순서를 정해 보세요.",
        answer_excerpt="북두칠성부터 찾으면 다른 별도 찾기 쉽다.",
        week_label="10월 셋째 주",
    ),
]


def test_compose_puts_numbers_before_end_punctuation_and_collects_citations() -> None:
    composed = checks.compose(
        [
            S(text='고양이 집에 "계단을 만들었다"고 썼어요.', evidence=[1]),
            S(text="별자리 순서도 정했어요", evidence=[3, 1, 3]),
        ]
    )
    assert composed.text == (
        '고양이 집에 "계단을 만들었다"고 썼어요[1]. 별자리 순서도 정했어요[1][3].'
    )
    assert composed.citations == [1, 3]


def test_compose_removes_numbers_written_inside_sentence() -> None:
    composed = checks.compose([S(text="집을 설계했어요 [2].", evidence=[1])] * 2)
    assert composed.text == "집을 설계했어요[1]. 집을 설계했어요[1]."


def test_valid_output_passes() -> None:
    sentences = [
        S(text='"북두칠성부터 찾으면"이라고 답했어요.', evidence=[3]),
        S(text="「동물 친구들의 집」에서 고양이 집을 설계했어요.", evidence=[1]),
    ]
    assert checks.check(sentences, EVIDENCE) is None


@pytest.mark.parametrize(
    ("sentences", "kind", "reason"),
    [
        ([S(text="한 문장.", evidence=[1])], "FORMAT", "SENTENCE_COUNT"),
        ([S(text="가.", evidence=[1])] * 4, "FORMAT", "SENTENCE_COUNT"),
        ([S(text="가.", evidence=[1]), S(text=" [1] ", evidence=[1])], "FORMAT", "BLANK_SENTENCE"),
        ([S(text="가.", evidence=[1]), S(text="나.", evidence=[])], "REJECTED", "NO_CITATION"),
        (
            [S(text="가.", evidence=[1]), S(text="나.", evidence=[2])],
            "REJECTED",
            "CITATION_OUT_OF_RANGE",
        ),
        (
            [S(text="가.", evidence=[1]), S(text='"계단을 만들었다"고 했어요.', evidence=[3])],
            "REJECTED",
            "QUOTE_NOT_IN_EVIDENCE",
        ),
        (
            [S(text="가.", evidence=[1]), S(text="“계단을 만들었어요”라고 했어요.", evidence=[1])],
            "REJECTED",
            "QUOTE_NOT_IN_EVIDENCE",
        ),
    ],
)
def test_problems(sentences: list[S], kind: str, reason: str) -> None:
    assert checks.check(sentences, EVIDENCE) == checks.Problem(kind, reason)  # type: ignore[arg-type]
