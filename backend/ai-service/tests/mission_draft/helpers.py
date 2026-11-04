"""미션 초안 테스트 공통 입력. 성취기준 문장은 데모 시드와 같은 합성·공개 문장, 학생 정보 없음."""

from typing import Any

from app.mission_draft.models import MissionDraftRequest
from app.mission_draft.prompts import (
    GeneratedAnswerKey,
    GeneratedAssignment,
    GeneratedChoice,
    GeneratedDraft,
    GeneratedElement,
)

EVALUATE_CODES = [
    {"code": "EVALUATE_CLAIM", "label": "주장", "description": "자기 주장(입장)을 밝힘"},
    {"code": "EVALUATE_EVIDENCE", "label": "근거", "description": "주장을 뒷받침하는 근거를 말함"},
    {
        "code": "EVALUATE_PERSPECTIVE",
        "label": "다른 관점·반론",
        "description": "다른 관점·반대 의견을 생각하고 답함",
    },
]


def make_request(**overrides: Any) -> MissionDraftRequest:
    body: dict[str, Any] = {
        "standards": [{"code": "6국01-02", "statement": "의견을 제시하고 함께 조정하며 토의한다."}],
        "thinkingType": "EVALUATE",
        "elementCodes": EVALUATE_CODES,
        "gradeMin": 5,
        "gradeMax": 5,
        "inputType": "NARRATIVE",
        "previousFailures": [],
    }
    body.update(overrides)
    return MissionDraftRequest.model_validate(body)


def element(
    code: str, *, good: bool = False, standard: str | None = "6국01-02"
) -> GeneratedElement:
    return GeneratedElement(
        code=code, label=code, description=f"{code} 설명", goodThought=good, standardCode=standard
    )


def narrative_draft(**overrides: Any) -> GeneratedDraft:
    body: dict[str, Any] = {
        "title": "쉬는 시간을 늘릴까?",
        "question": (
            "쉬는 시간을 20분으로 늘리자는 의견이 있어요. "
            "너는 어떻게 생각하는지 까닭과 함께 써 보자."
        ),
        "guide": "찬성인지 반대인지 먼저 정해 보자.",
        "sceneNote": "교실에서 친구들이 시계를 보는 장면",
        "choices": None,
        "categories": None,
        "answerKey": None,
        "exampleAnswer": (
            "나는 찬성이야. 쉬는 시간이 길면 친구와 더 오래 놀고 다음 수업에 더 집중할 수 있어."
        ),
        "forbiddenTerms": ["집중력 향상"],
        "hints": ["쉬는 시간에 주로 무엇을 하는지 떠올려 볼까?"],
        "elements": [
            element("EVALUATE_CLAIM"),
            element("EVALUATE_EVIDENCE"),
            element("EVALUATE_PERSPECTIVE", good=True),
        ],
    }
    body.update(overrides)
    return GeneratedDraft(**body)


def choice_draft(**overrides: Any) -> GeneratedDraft:
    body: dict[str, Any] = {
        "title": "시든 화분",
        "question": "두 화분 중 하나만 시들었어요. 무엇 때문일까?",
        "guide": None,
        "sceneNote": None,
        "choices": [
            GeneratedChoice(id="c1", label="햇빛"),
            GeneratedChoice(id="c2", label="물"),
            GeneratedChoice(id="c3", label="흙"),
        ],
        "categories": None,
        "answerKey": GeneratedAnswerKey(choiceIds=["c2"], assignments=None, finalAnswer=None),
        "exampleAnswer": None,
        "forbiddenTerms": [],
        "hints": ["두 화분이 서로 어떻게 달랐는지 살펴볼까?"],
        "elements": [element("ANSWER_KEY", standard=None)],
    }
    body.update(overrides)
    return GeneratedDraft(**body)


def classification_draft() -> GeneratedDraft:
    return choice_draft(
        categories=[GeneratedChoice(id="g1", label="동물"), GeneratedChoice(id="g2", label="식물")],
        answerKey=GeneratedAnswerKey(
            choiceIds=None,
            assignments=[GeneratedAssignment(choiceId="c1", categoryId="g1")],
            finalAnswer=None,
        ),
    )
