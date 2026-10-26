"""근거 구절 추출 프롬프트. 문구를 바꾸면 PROMPT_VERSION을 올림 (NFR-DAT-02).

LLM에는 답변 원문·학년·기준표만 전달, 학생 이름·ID는 넣지 않음 (NFR-SEC-03).
"""

from app.judgment.models import RubricElement

PROMPT_VERSION = "judge@1"

SYSTEM = """\
너는 초등·중학생 답변에서 평가 요소별 근거 구절을 찾는 도우미다.
충족 여부를 판정하거나 점수를 매기지 않는다. 근거가 되는 구절을 찾는 일만 한다.

요소마다 status를 하나 고른다.
- FOUND: 답변에 그 요소를 보여 주는 구절이 있다. quote에 그 구절을 답변에서 그대로 복사한다.
- NOT_FOUND: 답변에 그 요소가 없다. quote는 null.
- UNCLEAR: 답변이 모호해서 있는지 없는지 판단할 수 없다. quote는 null.

규칙
- quote는 답변 안의 이어진 한 구간을 글자 그대로 복사한다.
  고쳐 쓰거나, 줄이거나, 맞춤법을 바로잡거나, 여러 곳을 이어 붙이지 않는다.
- 맞춤법·띄어쓰기 실수는 판단에 반영하지 않는다.
- 학생 학년 수준에 맞게 너그럽게 보되, 답변에 없는 내용을 추측해서 FOUND로 하지 않는다.
- 모든 요소에 대해 elementId를 그대로 써서 정확히 한 번씩 답한다.
"""


def build_user(answer_text: str, grade: int, elements: list[RubricElement]) -> str:
    lines = [f"학년: {grade}", "", "평가 요소:"]
    for element in elements:
        lines.append(f"- elementId: {element.element_id}")
        lines.append(f"  이름: {element.label}")
        if element.description:
            lines.append(f"  설명: {element.description}")
        if element.common_errors:
            lines.append(f"  자주 하는 실수: {'; '.join(element.common_errors)}")
    lines += ["", "학생 답변:", "<answer>", answer_text, "</answer>"]
    return "\n".join(lines)
