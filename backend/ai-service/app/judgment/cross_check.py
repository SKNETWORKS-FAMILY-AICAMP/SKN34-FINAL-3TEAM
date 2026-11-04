"""M2·M1 교차 확인 입력과 불일치 판단 (api-spec 4.2.2, #69).

불일치 경계는 M2 담당 확인 전 임시값이라 설정으로 둠. PARTIAL은 불일치로 보지 않음.
"""

from typing import Any

from app.config import Settings
from app.judgment.models import JudgmentRequest, JudgmentResult


def m2_body(request: JudgmentRequest) -> dict[str, Any] | None:
    """M2를 부를 입력이 갖춰졌으면 scoring 요청 본문. 학년·승인 범위는 scoring이 판단."""
    if request.input_type == "SOLUTION_STEPS" or not request.question:
        return None
    body: dict[str, Any] = {
        "prompt": request.question,
        "text": request.answer_text,
        "grade": request.grade,
        "inputType": request.input_type,
    }
    if request.input_type == "NARRATIVE":
        keywords = [keyword for keyword in request.keywords if keyword.strip()]
        if not keywords:
            return None
        return body | {"keywords": keywords}
    if request.essay_type is None:
        return None
    return body | {"essayType": request.essay_type}


def m1_body(request: JudgmentRequest) -> dict[str, Any] | None:
    if (
        request.input_type != "SOLUTION_STEPS"
        or not request.question
        or not request.answer_key
        or request.solution is None
    ):
        return None
    return {
        "problem": request.question,
        "answerKey": request.answer_key,
        "solution": {
            "steps": request.solution.steps,
            "finalAnswer": request.solution.final_answer,
        },
    }


def mean(scores: dict[str, int]) -> float:
    return sum(scores.values()) / len(scores)


def disagrees(result: JudgmentResult, input_type: str, average: float, settings: Settings) -> bool:
    if input_type == "NARRATIVE":
        low, high = settings.m2_narrative_low, settings.m2_narrative_high
    else:
        low, high = settings.m2_essay_low, settings.m2_essay_high
    return (result == "CORRECT" and average <= low) or (result == "RETHINK" and average >= high)
