"""근거 구절 추출 프롬프트 출력 형식."""

import re

from app.judgment.models import RubricElement
from app.judgment.prompts import PROMPT_VERSION, SYSTEM, build_user


def element(element_id: str, **extra) -> RubricElement:
    return RubricElement(
        element_id=element_id, label=f"요소 {element_id}", points=1, judge_verified=True, **extra
    )


def test_build_user_lists_elements_and_wraps_answer() -> None:
    elements = [
        element("e1", description="주장을 밝힘", common_errors=["이유 없음", "주장 반복"]),
        element("e2"),  # 설명·자주 하는 실수가 없으면 그 줄을 쓰지 않음
    ]
    assert build_user("나는 찬성해.\n왜냐하면 재밌어.", 3, elements) == "\n".join(
        [
            "학년: 3",
            "",
            "평가 요소:",
            "- elementId: e1",
            "  이름: 요소 e1",
            "  설명: 주장을 밝힘",
            "  자주 하는 실수: 이유 없음; 주장 반복",
            "- elementId: e2",
            "  이름: 요소 e2",
            "",
            "학생 답변:",
            "<answer>",
            "나는 찬성해.",
            "왜냐하면 재밌어.",
            "</answer>",
        ]
    )


def test_system_asks_status_and_verbatim_quote_only() -> None:
    assert all(status in SYSTEM for status in ("FOUND", "NOT_FOUND", "UNCLEAR"))
    assert "elementId" in SYSTEM
    assert re.fullmatch(r"judge@\d+", PROMPT_VERSION)
