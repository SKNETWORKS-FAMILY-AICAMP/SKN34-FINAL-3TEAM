"""POST /internal/mission-drafts 요청·응답 (API 명세서 4.2, #354). JSON 필드는 camelCase.

learning 미션 초안 생성 작업이 호출 1번에 생성 1회를 요청한다(반복·상한은 learning).
요청에는 성취기준·생각 유형·표준 요소·학년·입력 방식만 있고 학생 정보는 없다.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from app.followup.models import LlmVersions, ThinkingType
from app.judgment.models import ApiModel

InputType = Literal["CHOICE", "ORDERING", "CLASSIFICATION", "NARRATIVE", "SOLUTION_STEPS", "ESSAY"]
# ai 검사. 요청의 previousFailures에는 learning 검사(STANDARD_CODE·ELEMENT_CODE·SHAPE)와
# AI_CALL도 옴
AiCheck = Literal["REQUIRED", "QUESTION_LENGTH", "LEAK"]

ESSAY_MIN_GRADE = 5  # 논술은 초5~6 (P03)


class StandardLevel(ApiModel):
    """성취수준 문장. 평가원 자료 이용 조건 확인 전에는 learning이 보내지 않음 (FN 1.5)."""

    grade: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Standard(ApiModel):
    code: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    level: StandardLevel | None = None


class ElementCode(ApiModel):
    """초안 요소에 쓸 수 있는 code.

    learning이 FN 1.5 표에서 유형 코드와 입력 방식의 정답 코드를 채움.
    """

    code: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str = ""


class Failure(ApiModel):
    check: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class MissionDraftRequest(ApiModel):
    standards: list[Standard] = Field(min_length=1)
    thinking_type: ThinkingType
    element_codes: list[ElementCode] = Field(min_length=1)
    grade_min: int = Field(ge=3, le=6)
    grade_max: int = Field(ge=3, le=6)
    input_type: InputType
    previous_failures: list[Failure] = Field(default_factory=list)

    @model_validator(mode="after")
    def grades_fit(self) -> Self:
        if self.grade_min > self.grade_max:
            raise ValueError("gradeMin은 gradeMax보다 클 수 없음")
        if self.input_type == "ESSAY" and self.grade_min < ESSAY_MIN_GRADE:
            raise ValueError("논술은 초5~6")
        return self


class Choice(ApiModel):
    id: str
    label: str


class Assignment(ApiModel):
    choice_id: str
    category_id: str


class AnswerKey(ApiModel):
    """learning 관리자 기준표 정답 키와 같은 모양.

    고르기·순서 choiceIds, 분류 assignments, 풀이 finalAnswer.
    """

    choice_ids: list[str] | None = None
    assignments: list[Assignment] | None = None
    final_answer: str | None = None


class DraftElement(ApiModel):
    code: str
    label: str
    description: str
    good_thought: bool
    standard_code: str | None = None


class Draft(ApiModel):
    title: str
    question: str
    guide: str | None = None
    scene_note: str | None = None
    choices: list[Choice] | None = None
    categories: list[Choice] | None = None
    answer_key: AnswerKey | None = None
    example_answer: str | None = None
    forbidden_terms: list[str] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    elements: list[DraftElement] = Field(default_factory=list)


class Checks(ApiModel):
    passed: bool
    failures: list[Failure]


class MissionDraftResponse(ApiModel):
    draft: Draft
    checks: Checks
    versions: LlmVersions
