"""POST /internal/theme-drafts 요청·응답 (api-spec 4.2, #437, 에픽 #436). JSON 필드는 camelCase.

learning 테마 초안 생성 작업이 호출 1번에 그래프를 한 번 끝까지 실행하도록 요청한다
(다시 부르기는 learning).
요청에는 학년·적용 주·주제·유형별 성취기준·요소 code·입력 방식·이전 실패만 있고 학생 정보는 없다.
응답에는 정답 논리 검사용 내부 칸(특징 표·단서 조건·증거·찾는 대상)을 넣지 않는다(계약 그대로).
"""

from datetime import date
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from app.followup.models import LlmVersions, ThinkingType
from app.judgment.models import ApiModel
from app.mission_draft.models import ESSAY_MIN_GRADE, Draft, ElementCode, InputType, Standard

Day = Literal["MON", "TUE", "WED", "THU", "FRI"]
Scene = Literal["INTRO", "MON", "TUE", "WED", "THU", "FRI", "OUTRO"]
# failure.stage와 previousFailures[].stage는 같은 네 값(사용자 결정 2026-11-10, #438과 맞춤)
FailureStage = Literal["THEME", "MISSION", "REVIEW", "IMAGE"]
# warnings는 끝내 실패해도 그 항목만 빼고 성공으로 돌려주는 단계까지 포함
WarningStage = Literal["THEME", "MISSION", "DIALOGUE", "REVIEW", "IMAGE", "VIDEO", "MOTION"]

THINKING_TYPES: tuple[ThinkingType, ...] = ("ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT")


class ThemeMissionInput(ApiModel):
    """유형 하나의 미션 입력.

    성취기준·요소 code·입력 방식은 learning이 채움(코드 목록은 learning 소유).
    """

    thinking_type: ThinkingType
    input_type: InputType
    standards: list[Standard] = Field(min_length=1)
    element_codes: list[ElementCode] = Field(min_length=1)


class ThemeFailure(ApiModel):
    """이전 시도의 실패.

    learning 검사 실패는 배치·정답 논리면 THEME, 미션 규칙이면 MISSION으로 바꿔 넣고
    AI 호출 실패는 넣지 않는다. MISSION 사유는 "<요일> <검사 코드> <자세히>"로 시작.
    """

    stage: FailureStage
    reasons: list[str] = Field(min_length=1)


class ThemeDraftRequest(ApiModel):
    grade_min: int = Field(ge=3, le=6)
    grade_max: int = Field(ge=3, le=6)
    week_start: date
    topic: str | None = None
    missions: list[ThemeMissionInput] = Field(min_length=5, max_length=5)
    previous_failures: list[ThemeFailure] = Field(default_factory=list)

    @model_validator(mode="after")
    def shape_fits(self) -> Self:
        if self.grade_min != self.grade_max:
            raise ValueError("학년별 테마라 gradeMin과 gradeMax가 같아야 함")
        if sorted(m.thinking_type for m in self.missions) != sorted(THINKING_TYPES):
            raise ValueError("missions는 생각 유형 5개에 1개씩")
        if self.grade_min < ESSAY_MIN_GRADE and any(m.input_type == "ESSAY" for m in self.missions):
            raise ValueError("논술은 초5~6")
        return self

    @property
    def grade(self) -> int:
        return self.grade_min

    def mission_for(self, thinking_type: ThinkingType) -> ThemeMissionInput:
        return next(m for m in self.missions if m.thinking_type == thinking_type)


class Character(ApiModel):
    name: str
    look: str


class ThemeDay(ApiModel):
    day: Day
    thinking_type: ThinkingType
    place: str
    scene_note: str
    clue: str
    rules_out: list[str]


class Theme(ApiModel):
    title: str
    world: str
    characters: list[Character]
    style_note: str
    outfit: str
    intro: str
    outro: str
    big_question: str
    candidates: list[str]
    answer: str
    days: list[ThemeDay]


class ThemeMission(ApiModel):
    day: Day
    thinking_type: ThinkingType
    draft: Draft


class DialogueLine(ApiModel):
    speaker: str
    text: str


class ThemeDialogue(ApiModel):
    day: Day
    lines: list[DialogueLine]


class ThemeWarning(ApiModel):
    stage: WarningStage
    item: str
    reason: str


class ThemeFailureResult(ApiModel):
    stage: FailureStage
    reasons: list[str]


class ThemeDraftResponse(ApiModel):
    """끝내 실패하면 failure를 담아 200(learning CHECK_FAILED).

    대화·영상·움직임은 끝내 실패해도 그 항목만 빼고 warnings에 남긴다.
    """

    theme: Theme | None
    missions: list[ThemeMission]
    dialogues: list[ThemeDialogue]
    images: dict[Scene, str]
    videos: dict[Scene, str]
    # 움직임 JSON 형식은 움직임 단계에서 확정(#437 확인 필요 "움직임 JSON 형식과 상한 값")
    motions: dict[Scene, dict[str, Any]]
    warnings: list[ThemeWarning]
    failure: ThemeFailureResult | None
    versions: LlmVersions
