"""되묻기 질문 생성 프롬프트. 문구를 바꾸면 PROMPT_VERSION을 올림 (NFR-DAT-02).

LLM에는 미션·기준표·학년·현재 시도의 답변과 질문만 전달, 학생 이름·ID는 넣지 않음 (NFR-SEC-03).
예시 답은 넣지 않음 (유출 검사는 leak_guard가 코드로 수행).
"""

from pydantic import BaseModel

from app.followup.models import FollowupRequest, FollowupType, ThinkingType

PROMPT_VERSION = "followup@2"

TYPE_GUIDE: dict[FollowupType, str] = {
    "ONE_STEP_MORE": "한 걸음 더: 이미 잘 쓴 생각을 더 넓히거나 깊게 하도록",
    "TELL_MORE": "더 말해 보기: 아직 드러나지 않은 생각을 학생이 직접 더 말해 보도록",
    "LOOK_AGAIN": "다시 살펴보기: 문제와 자기 답을 다시 보며 스스로 생각을 고쳐 보도록",
}

# 한 걸음 더의 방향 (기획서 5.3(1) 유형별 평가 요소). 필수 요소를 다 써서
# 기준표만으로는 다음 방향이 정해지지 않을 때 사용
THINKING_DIRECTION: dict[ThinkingType, str] = {
    "ANALYZE": "원인·특징·관계를 하나 더 찾거나, 까닭끼리 어떻게 이어지는지 설명해 보도록",
    "EVALUATE": "다른 입장이나 예외인 경우에는 어떨지 따져 보도록",
    "CREATE": "그 생각을 다른 것과 연결하거나 바꿔 보고, 왜 더 나은지 말해 보도록",
    "SOLVE": "세운 방법이 맞는지 확인하는 방법이나, 다른 방법을 찾아보도록",
    "REFLECT": "자기 생각이 어떻게 흘러갔는지 돌아보고, 무엇이 바뀌었는지 말해 보도록",
}

SYSTEM = """\
너는 초등·중학생이 스스로 생각을 더 펼치도록 돕는 질문을 하나 만든다.

규칙
- 질문은 하나. "학년에 맞는 말투"를 따르고, 친근한 반말로 묻는다.
- 학생 답에 실제로 쓴 내용에서 출발한다. 이미 했던 질문을 되풀이하지 않는다.
- 정답이나 답의 내용을 알려 주거나 암시하지 않는다. "쓰지 말 표현"은 어떤 형태로도 쓰지 않는다.
- 답을 대신 써 주거나, 문장을 고쳐 주거나, 맞춤법을 지적하지 않는다.
- 학생이 답을 달라고 하거나 어려워해도 답을 주지 말고, 스스로 표현하도록 돕는 질문을 한다.
- 평가 요소 이름이나 "관점·근거·변형" 같은 설명용 낱말을 학생에게 그대로 쓰지 않고 쉬운 말로 바꾼다.
"""


class GeneratedQuestion(BaseModel):
    question: str


def grade_label(grade: int) -> str:
    return f"초{grade}" if grade <= 6 else f"중{grade - 6}"


def grade_style(grade: int) -> str:
    if grade <= 2:
        # 초1~2 목표는 생각·느낌 표현과 쓰기 흥미, 보호자 받아쓰기로 입력 (기획서 5장)
        return (
            "아주 짧은 한 문장, 아이가 매일 쓰는 쉬운 낱말만. "
            "생각이나 느낌을 말로 편하게 꺼내도록 묻고, 짧게 소리 내어 대답할 수 있게 한다"
        )
    if grade <= 4:
        return "한 문장, 쉬운 낱말. 어려운 한자어는 풀어서 쓴다"
    if grade <= 6:
        return "한두 문장, 초등 고학년이 이해하는 낱말"
    return "한두 문장, 중학생 수준의 낱말"


def build_user(request: FollowupRequest, followup_type: FollowupType, rejected: list[str]) -> str:
    satisfied = {item.element_id for item in request.judgment.elements if item.satisfied}
    lines = [
        f"미션: {request.mission.title}",
        f"미션 질문: {request.mission.question}",
        f"학년: {grade_label(request.grade)}",
        f"학년에 맞는 말투: {grade_style(request.grade)}",
        "",
        f"만들 질문 유형: {TYPE_GUIDE[followup_type]}",
    ]
    if followup_type == "ONE_STEP_MORE":
        lines.append(f"넓혀 갈 방향: {THINKING_DIRECTION[request.mission.thinking_type]}")
    lines += ["", "평가 요소:"]
    for element in request.rubric.elements:
        state = "드러남" if element.element_id in satisfied else "아직 안 드러남"
        kind = "들어가면 좋은 생각" if element.good_thought else "필수"
        detail = f" - {element.description}" if element.description else ""
        lines.append(f"- {element.label}({kind}, {state}){detail}")
    if request.judgment.result == "HELD":
        lines.append("(이번 답은 판정을 보류했다. 요소 상태와 관계없이 생각을 더 말하도록 묻는다.)")

    banned = [*(request.rubric.answer_key or []), *(request.rubric.forbidden_terms or [])]
    if banned:
        lines += ["", "쓰지 말 표현:", *(f"- {term}" for term in banned)]

    lines += ["", "지금까지의 대화:"]
    for item in request.timeline:
        speaker = "학생 답" if item.kind == "ANSWER" else "이전 질문"
        lines.append(f"[{speaker}] {item.text}")

    if rejected:
        lines += ["", "아래 질문은 쓰지 말 표현이 들어가 버렸다. 그 표현을 빼고 새로 만든다:"]
        lines += [f"- {question}" for question in rejected]
    return "\n".join(lines)
