"""미션 초안 생성 프롬프트 (기획서 6.2 ②, FN-ADM-20, #354).

문구를 바꾸면 PROMPT_VERSION을 올림 (NFR-DAT-02). LLM에는 성취기준·(있으면) 성취수준 문장·
생각 유형·쓸 수 있는 요소 code·학년·입력 방식·이전 실패 사유만 전달한다.
학생 정보·학생 답·AI Hub 데이터는 넣지 않는다.
"""

from pydantic import BaseModel

from app.followup.prompts import grade_style
from app.mission_draft.models import InputType, MissionDraftRequest

PROMPT_VERSION = "mission-draft@1"

THINKING_LABEL = {
    "ANALYZE": "분석하기(원인·특징·관계를 찾고 까닭으로 잇기)",
    "EVALUATE": "따져 보기(주장·근거를 세우고 다른 관점을 따지기)",
    "CREATE": "새로 만들기(새로운 생각을 내고 왜 더 나은지 말하기)",
    "SOLVE": "문제 해결하기(구할 것을 정하고 방법을 세워 결과를 확인하기)",
    "REFLECT": "돌아보기(바뀐 생각과 그 까닭을 자기 경험과 잇기)",
}

INPUT_GUIDE: dict[InputType, str] = {
    "CHOICE": (
        "고르기: choices에 선택지 3~4개(id는 c1, c2 …), answerKey.choiceIds에 정답 id 1개. "
        "요소는 ANSWER_KEY 하나만. exampleAnswer·categories는 null"
    ),
    "ORDERING": (
        "순서 정하기: choices에 항목 3~5개(id는 c1, c2 …), "
        "answerKey.choiceIds에 모든 id를 올바른 순서로. "
        "요소는 ANSWER_KEY 하나만. exampleAnswer·categories는 null"
    ),
    "CLASSIFICATION": (
        "분류하기: choices에 항목 4~6개(id는 c1, c2 …), categories에 그룹 2~3개(id는 g1, g2 …), "
        "answerKey.assignments에 모든 항목의 {choiceId, categoryId}. "
        "요소는 ANSWER_KEY 하나만. exampleAnswer는 null"
    ),
    "NARRATIVE": (
        "서술: 학생이 자기 생각을 글로 씀. exampleAnswer에 학년에 맞는 예시 답. "
        "choices·categories·answerKey는 null. 요소는 아래 요소 규칙대로"
    ),
    "SOLUTION_STEPS": (
        "풀이 단계: 학생이 무엇을 구하나요·어떻게 구할까요·계산·확인해 보기를 씀. "
        "answerKey.finalAnswer에 단위 없이 최종 답만. "
        "요소는 아래 요소 규칙의 유형 요소와 FINAL_ANSWER 하나. "
        "choices·categories는 null"
    ),
    "ESSAY": (
        "논술: 학생이 주장·까닭 1·까닭 2·반대 의견에 답하기를 씀. "
        "exampleAnswer에 학년에 맞는 예시 답. "
        "choices·categories·answerKey는 null. 따져 보기 논술이면 EVALUATE_CLAIM·EVALUATE_EVIDENCE·"
        "EVALUATE_PERSPECTIVE 세 요소를 모두 둠"
    ),
}

# 생각 미션(서술·풀이·논술)의 필수·들어가면 좋은 생각 기본값. 데모 시드 20문항의 유형별
# 지정을 따른다(ai.md 9.1). 관리자가 검토에서 바꿀 수 있다.
ELEMENT_RULE = {
    "ANALYZE": "ANALYZE_RELATION은 필수, ANALYZE_REASON은 들어가면 좋은 생각",
    "EVALUATE": (
        "EVALUATE_CLAIM·EVALUATE_EVIDENCE는 필수, EVALUATE_PERSPECTIVE는 들어가면 좋은 생각"
    ),
    "CREATE": "CREATE_NEW·CREATE_WHY는 필수, CREATE_CONNECT는 들어가면 좋은 생각",
    "SOLVE": "SOLVE_DEFINE·SOLVE_PLAN은 필수, SOLVE_CHECK는 들어가면 좋은 생각",
    "REFLECT": "REFLECT_CHANGE·REFLECT_REASON은 필수, REFLECT_CONNECT는 들어가면 좋은 생각",
}
EVALUATE_ESSAY_RULE = (
    "EVALUATE_CLAIM·EVALUATE_EVIDENCE·EVALUATE_PERSPECTIVE 모두 필수, "
    "들어가면 좋은 생각은 두지 않음"
)
CLOSED_INPUTS = {"CHOICE", "ORDERING", "CLASSIFICATION"}

# 이전 시도 실패 사유 → 고칠 점 (learning이 previousFailures로 돌려줌)
FAILURE_FIX = {
    ("REQUIRED", "TITLE"): "제목을 채운다",
    ("REQUIRED", "QUESTION"): "질문을 채운다",
    ("REQUIRED", "ELEMENTS"): "평가 요소를 채운다",
    ("REQUIRED", "CHOICES"): "선택지를 2개 이상 채운다",
    ("REQUIRED", "CATEGORIES"): "분류 그룹을 2개 이상 채운다",
    ("REQUIRED", "ANSWER_KEY"): "입력 방식에 맞는 정답 키를 채운다",
    ("REQUIRED", "EXAMPLE_ANSWER"): "예시 답을 채운다",
    ("REQUIRED", "HINTS"): "생각 열기 질문을 1개 이상 채운다",
    ("QUESTION_LENGTH", "TOO_LONG"): "질문을 글자 수 상한 안으로 줄인다",
    ("LEAK", "ANSWER_KEY"): "질문·안내·생각 열기 질문에 정답을 쓰지 않는다",
    ("LEAK", "FORBIDDEN_TERM"): "질문·안내·생각 열기 질문에 금지어를 쓰지 않는다",
    ("LEAK", "EXAMPLE_ANSWER"): "질문·안내·생각 열기 질문에 예시 답 내용을 쓰지 않는다",
}
CHECK_FIX = {
    "STANDARD_CODE": "요소의 standardCode는 주어진 성취기준 코드만 쓴다",
    "ELEMENT_CODE": "요소 code는 주어진 목록과 입력 방식 규칙을 지킨다",
    "SHAPE": "선택지·그룹·정답 키가 서로 맞게(정답 id가 선택지에 있게) 만든다",
    "AI_CALL": "형식에 맞게 다시 만든다",
}

# 줄 길이 제한 때문에 문자열을 이어 붙였을 뿐 한 규칙은 한 줄이다
SYSTEM = (
    "너는 초등학생 사고력 학습 서비스의 미션 초안을 만든다. "
    "만든 초안은 사람이 검수한 뒤에만 학생에게 공개된다.\n"
    "\n"
    "규칙\n"
    "- 미션은 주어진 성취기준을 공부하는 활동이다. "
    "질문은 성취기준 문장의 행동(동사)을 학생이 직접 하게 만든다.\n"
    "- 질문은 학생이 실제로 생각해서 답하는 열린 상황으로, "
    "정답이나 답의 핵심 내용을 질문에 쓰지 않는다.\n"
    '- "학년에 맞는 말투"와 글자 수 상한을 지킨다. 어려운 한자어는 풀어 쓴다.\n'
    '- 평가 요소 code는 "쓸 수 있는 요소 code" 목록에 있는 것만 쓰고 '
    "이름·설명을 이 미션에 맞게 구체화한다.\n"
    "- 정답 요소(ANSWER_KEY·FINAL_ANSWER)가 아닌 요소의 standardCode는 "
    "주어진 성취기준 코드 중 하나, 정답 요소는 null.\n"
    "- goodThought=true(들어가면 좋은 생각)는 판정에서 필수가 아닌 요소다. "
    '"요소 규칙"이 있으면 그 요소들을 모두 두고 규칙대로 정한다. 정답 요소는 항상 false.\n'
    "- forbiddenTerms에는 질문·안내·생각 열기 질문에 나오면 "
    "답을 알려 주게 되는 낱말을 적는다.\n"
    "- hints(생각 열기 질문)는 1~3개, 답을 알려 주지 않고 생각의 출발점만 준다.\n"
    "- sceneNote는 장면 그림을 그릴 사람에게 주는 짧은 메모다. 학생에게 보이지 않는다.\n"
    "- 실존 인물·상표·학생 개인정보를 쓰지 않는다. 등장인물은 흔한 이름의 또래로 한다.\n"
)


class GeneratedChoice(BaseModel):
    id: str
    label: str


class GeneratedAssignment(BaseModel):
    choiceId: str  # noqa: N815 (응답 JSON 키를 그대로 받음)
    categoryId: str  # noqa: N815


class GeneratedAnswerKey(BaseModel):
    choiceIds: list[str] | None  # noqa: N815
    assignments: list[GeneratedAssignment] | None
    finalAnswer: str | None  # noqa: N815


class GeneratedElement(BaseModel):
    code: str
    label: str
    description: str
    goodThought: bool  # noqa: N815
    standardCode: str | None  # noqa: N815


class GeneratedDraft(BaseModel):
    """구조화 출력 형식. 필드 이름은 api-spec 4.2 `draft`와 같음."""

    title: str
    question: str
    guide: str | None
    sceneNote: str | None  # noqa: N815
    choices: list[GeneratedChoice] | None
    categories: list[GeneratedChoice] | None
    answerKey: GeneratedAnswerKey | None  # noqa: N815
    exampleAnswer: str | None  # noqa: N815
    forbiddenTerms: list[str]  # noqa: N815
    hints: list[str]
    elements: list[GeneratedElement]


def build_user(request: MissionDraftRequest, max_question_chars: int) -> str:
    lines = ["성취기준:"]
    for standard in request.standards:
        lines.append(f"- {standard.code}: {standard.statement}")
        if standard.level is not None:
            lines.append(f"  성취수준 {standard.level.grade}: {standard.level.text}")
    grade = (
        f"초{request.grade_min}"
        if request.grade_min == request.grade_max
        else f"초{request.grade_min}~{request.grade_max}"
    )
    lines += [
        "",
        f"생각 유형: {THINKING_LABEL[request.thinking_type]}",
        f"학년: {grade}",
        f"학년에 맞는 말투: {grade_style(request.grade_min)}",
        f"질문 글자 수 상한: {max_question_chars}자",
        f"입력 방식: {INPUT_GUIDE[request.input_type]}",
    ]
    rule = element_rule(request)
    if rule:
        lines.append(f"요소 규칙: {rule}")
    lines += [
        "",
        "쓸 수 있는 요소 code:",
    ]
    for element in request.element_codes:
        detail = f" - {element.description}" if element.description else ""
        lines.append(f"- {element.code}: {element.label}{detail}")
    fixes = list(dict.fromkeys(_fix(f.check, f.reason) for f in request.previous_failures))
    if fixes:
        lines += ["", "이전 초안이 검사를 통과하지 못했다. 아래를 고쳐서 새로 만든다:"]
        lines += [f"- {fix}" for fix in fixes]
    return "\n".join(lines)


def element_rule(request: MissionDraftRequest) -> str | None:
    """정답형은 ANSWER_KEY 하나뿐이라 규칙 없음. 따져 보기 논술은 세 논증 요소가 모두 필수."""
    if request.input_type in CLOSED_INPUTS:
        return None
    if request.input_type == "ESSAY" and request.thinking_type == "EVALUATE":
        return EVALUATE_ESSAY_RULE
    return ELEMENT_RULE[request.thinking_type]


def _fix(check: str, reason: str) -> str:
    fallback = "검사를 통과하도록 다시 만든다"
    return FAILURE_FIX.get((check, reason)) or CHECK_FIX.get(check) or fallback
