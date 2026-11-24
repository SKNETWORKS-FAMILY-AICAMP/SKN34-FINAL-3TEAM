"""POST /internal/theme-drafts 요청·응답 (api-spec 4.2, #437, 에픽 #436). JSON 필드는 camelCase.

learning 테마 초안 생성 작업이 호출 1번에 그래프를 한 번 끝까지 실행하도록 요청한다
(다시 부르기는 learning).
요청에는 학년·적용 주·주제·유형별 성취기준·요소 code·입력 방식·이전 실패만 있고 학생 정보는 없다.
응답에는 정답 논리 검사용 내부 칸(특징 표·단서 조건·증거·찾는 대상)을 넣지 않는다(계약 그대로).
"""

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.followup.models import LlmVersions, ThinkingType
from app.judgment.models import ApiModel
from app.mission_draft.models import ESSAY_MIN_GRADE, Draft, ElementCode, InputType, Standard
from app.theme_draft.families import StoryTypeCode

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


REGEN_VERSION = 1  # regen 묶음 모양 번호(ai 전용 칸이 바뀌면 올림)
# 부분 다시 생성 대상(#537, 사용자 결정 2026-11-17).
# 영상은 시작·종료만, 그림은 장면 7개, 미션은 요일 5개
RegenTarget = Literal[
    "VIDEO:INTRO",
    "VIDEO:OUTRO",
    "IMAGE:INTRO",
    "IMAGE:OUTRO",
    "IMAGE:MON",
    "IMAGE:TUE",
    "IMAGE:WED",
    "IMAGE:THU",
    "IMAGE:FRI",
    "MISSION:MON",
    "MISSION:TUE",
    "MISSION:WED",
    "MISSION:THU",
    "MISSION:FRI",
]


class ThemeRegenBase(ApiModel):
    """원래 초안 결과(learning이 저장한 output 그대로).

    공개 theme은 쓰지 않고 regen.theme을 쓴다.
    """

    missions: list["ThemeMission"] = Field(default_factory=list)
    dialogues: list["ThemeDialogue"] = Field(default_factory=list)
    images: dict[str, str] = Field(default_factory=dict)
    videos: dict[str, str] = Field(default_factory=dict)
    motions: dict[str, dict] = Field(default_factory=dict)
    warnings: list["ThemeWarning"] = Field(default_factory=list)
    regen: dict


class ThemeRegenerate(ApiModel):
    """부분 다시 생성 요청: 대상과 원래 초안 결과. 대상은 원래 결과 regen.targets 안이어야 한다."""

    targets: list[RegenTarget] = Field(min_length=1)
    base: ThemeRegenBase

    @model_validator(mode="after")
    def targets_available(self) -> Self:
        self.targets = list(dict.fromkeys(self.targets))
        regen = self.base.regen
        if regen.get("version") != REGEN_VERSION or not isinstance(regen.get("theme"), dict):
            raise ValueError("base.regen 형식이 아님")
        missing = [t for t in self.targets if t not in (regen.get("targets") or [])]
        if missing:
            raise ValueError(f"재료가 없어 다시 만들 수 없는 대상: {missing}")
        return self


class ThemeDraftRequest(ApiModel):
    grade_min: int = Field(ge=3, le=6)
    grade_max: int = Field(ge=3, le=6)
    week_start: date
    topic: str | None = None
    missions: list[ThemeMissionInput] = Field(min_length=5, max_length=5)
    previous_failures: list[ThemeFailure] = Field(default_factory=list)
    # 부분 다시 생성(#537). 없으면 지금처럼 전체 생성
    regenerate: ThemeRegenerate | None = None

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
    # 그날 단서가 쓰는 특징 이름(features의 name, #647 선택 칸). 학생에게 단서 근거를
    # 보여 주는 데 씀
    clue_feature: str | None = None


class ThemeFeatureValue(ApiModel):
    candidate: str
    value: str


class ThemeFeature(ApiModel):
    """후보 특징 표의 특징 하나(#647): 이름과 후보마다 값.

    고른 성취기준 코드는 내부 칸이라 넣지 않음.
    """

    name: str
    values: list[ThemeFeatureValue]


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
    # 후보 특징 표(#647 선택 칸). rulesOut을 계산한 근거라 learning이 저장하고 학생에게는
    # 얻은 요일 것만 보임
    features: list[ThemeFeature] | None = None


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


VideoScene = Literal["INTRO", "OUTRO"]  # 영상은 시작·종료만(사용자 결정 2026-11-11)
EffectShape = Literal["circle", "leaf", "petal", "drop", "star", "snow", "bubble", "confetti"]
TransitionKind = Literal["none", "fade", "slide-left", "slide-right", "zoom"]


class MotionPoint(BaseModel):
    """그림 너비·높이 % 좌표와 확대(생각 열기 위치와 같은 기준)."""

    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    zoom: float = Field(ge=1, le=1.4)


class MotionTransition(BaseModel):
    kind: TransitionKind
    seconds: float = Field(ge=0.3, le=1.2)


class MotionCamera(BaseModel):
    from_: MotionPoint = Field(alias="from")
    to: MotionPoint
    seconds: float = Field(ge=8, le=20)

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class MotionEffect(BaseModel):
    shape: EffectShape
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    count: int = Field(ge=1, le=20)
    size: float = Field(ge=1, le=6)
    direction: int = Field(ge=0, le=359)
    speed: float = Field(ge=2, le=20)
    opacity: float = Field(ge=0.2, le=0.8)


class MotionCaption(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(max_length=30)


class MotionSpot(BaseModel):
    """살펴보기에서 학생이 누르는 그림 속 물건(요일 장면). 좌표는 그림 %."""

    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    label: str = Field(min_length=1, max_length=10)
    line: str = Field(min_length=1, max_length=30)
    evidence: bool  # 그날 찾은 증거 물건이면 true(장면마다 정확히 1개)


class ThemeMotion(BaseModel):
    """장면 움직임 형식 v1(api-spec 4.2·ai-service.yaml ThemeMotion). learning은 그대로 저장.

    spots는 2026-11-11 더한 선택 칸(요일 장면 살펴보기, 시작·종료는 빈 배열)이라 version은 1.
    """

    version: Literal[1] = 1
    transition: MotionTransition
    camera: MotionCamera | None
    speakers: dict[str, MotionPoint]
    effects: list[MotionEffect] = Field(max_length=2)
    captions: list[MotionCaption] = Field(max_length=8)
    spots: list[MotionSpot] = Field(default_factory=list, max_length=3)


class ThemeDraftResponse(ApiModel):
    """끝내 실패하면 failure를 담아 200(learning CHECK_FAILED).

    대화·영상·움직임은 끝내 실패해도 그 항목만 빼고 warnings에 남긴다.
    """

    theme: Theme | None
    missions: list[ThemeMission]
    dialogues: list[ThemeDialogue]
    images: dict[Scene, str]
    videos: dict[VideoScene, str]
    motions: dict[Scene, ThemeMotion]
    warnings: list[ThemeWarning]
    failure: ThemeFailureResult | None
    versions: LlmVersions
    # 부분 다시 생성 재료(#537). learning은 targets만 읽고 나머지는 열어 보지 않고 저장·전달.
    # 글 단계까지 못 가면 null
    regen: dict | None = None


ThemeRegenBase.model_rebuild()
ThemeRegenerate.model_rebuild()
ThemeDraftRequest.model_rebuild()


# ---------------------------------------------------------------------------
# LLM 구조화 출력 형식(테마 틀 스키마). 응답 JSON 키를 그대로 받으려고 camelCase 필드.
# 정답 논리 검사용 내부 칸(features·target·clueType·condition·evidence)은 응답 Theme에 넣지 않는다.
# ---------------------------------------------------------------------------
ClueType = Literal[
    "목격",
    "기록",
    "시각",
    "잠김",
    "소리",
    "색",
    "냄새",
    "재질",
    "무게",
    "습성",
    "발자국",
    "온도",
    "물기",
    "크기",
]
ReviewVerdict = Literal["PASS", "WARN", "FAIL"]
# #971: NEXT_FIT(이어 가기 날 지문이 사건 이야기·답이 다음 행동을 정함·단서가 그곳에서 나옴, 측정
# 판정과 같은 말). #782 v13 HELPER_FIT(부탁 날 돕는 사람의 일) 자리
StoryReviewId = Literal[
    "CLUE_LOGIC", "ANSWER_HINT", "GRADE_VOCAB", "STANDARD_FIT", "NEXT_FIT", "SAFETY"
]
MissionReviewId = Literal["EXAMPLE_COMPLETE", "STANDARD_FIT", "MATERIAL", "STORY_LINK"]


class GeneratedCharacter(BaseModel):
    name: str
    look: str


class GeneratedFeatureValue(BaseModel):
    candidate: str
    value: str


class GeneratedFeature(BaseModel):
    """후보 특징 표의 특징 하나. standardCode는 고른 그날 성취기준(장면에서 골랐으면 null, RAG "
    "#470 근거 자리)."""

    name: str
    standardCode: str | None
    values: list[GeneratedFeatureValue]


class GeneratedCondition(BaseModel):
    """단서가 말하는 조건. RULE은 그때 남은 후보를 새로 빼고, HINT는 남은 후보를 빼지 않으며 새
    특징 값을 알려 준다. STORY(사건 단서, #782 테마 짜임 사용자 결정 2026-11-19)는 후보 특징 대신
    사건이 어떻게 벌어졌는지 새 사실을 주고 아무 후보도 빼지 않는다(feature ''·allowed [])."""

    kind: Literal["RULE", "HINT", "STORY"]
    feature: str
    allowed: list[str]


class GeneratedEvidence(BaseModel):
    """단서의 증거 종류와 때. 못 찾은 대상 몸의 자국 같은 종류는 고를 수 없게 목록으로 둔다."""

    kind: Literal["TRACE", "SIGHTING", "RECORD"]
    when: str


class GeneratedDay(BaseModel):
    """rulesOut은 LLM이 쓰지 않는다. 특징 표와 condition으로 정해지는 값이라 코드가 채운다
    (checks.fill_rules_out).

    dayStep(오늘 온 까닭)·discovery(그날 찾은 증거 한 줄)·missionHook(증거의 어느 부분으로 그날
    활동을 할지 한 줄)은 대화 모델이 미션 전 대화를 쓰는 재료인 내부 칸이라 응답 theme에는 넣지
    않는다(#782 테마 짜임, 사용자 결정 2026-11-19: 전에는 discovery·missionHook을 대화 끝 두 줄로
    그대로 넣어 대화가 틀에 박혔음). discovery는 그림·살펴보기의 증거로도 쓴다. 단서는 학생이 그날
    미션을 마친 뒤 보여 주므로 셋 다 후보·정답을 말하지 않고 단서 결론도 말하지 않는다.
    """

    day: Day
    thinkingType: ThinkingType
    place: str
    sceneNote: str
    clue: str
    clueType: ClueType
    condition: GeneratedCondition
    evidence: GeneratedEvidence
    discovery: str
    missionHook: str
    # 오늘 온 까닭(내부 칸, #782 테마 짜임 기준안 — 확인 전): 어제 한 일에서 이어지는 한 줄(단서
    # 결과는 말하지 않음, 사용자 결정 2026-11-19 "어제 한 일만 잇기"). 기본값은 예전 저장본(부분
    # 다시 생성 재료)용이고 LLM 스키마는 필수, 새 줄거리는 check_theme이 REQUIRED로 봄
    dayStep: str = ""
    # 그날 장소 사람 호칭(내부 칸, #782 테마 짜임, 기준안). 이어 가기 날은 그날 지문 글을 가진·
    # 건네는 사람(#971). 미션 방식(missionWay)·다음 행동 종류(nextKind)는 코드가 정해
    # 넣음(LLM 스키마 밖). 기본값은 예전 저장본용
    helper: str = ""
    # #782 v10 부탁 날 아이 답의 쓰임 자리(내부 칸). #971 아침 재설계부터 쓰지 않음(쓴 글은 지문 속
    # 다음 행동에게 감) — 예전 저장본용으로 칸만 둠
    helperUse: str = ""
    # #971: 이어 가기 날 지문 속 사건에 나오는 다음 행동 — 갈 곳(그날 장소 안·곁의 자리)·만날 사람
    # (그때 그 자리에 있던 사람)·쓴 글을 받을 사람(내부 칸, 12자 기준안). 단서는 거기서 나오고 학생
    # 응답 단서 앞에 이름표로 붙음(checks.labeled_clue). 수사 날은 빈 값, 기본값은 예전 저장본용
    nextTarget: str = ""
    # 그날 미션 지문이 될 증거 내용(내부 칸, #782): 수사 연결 문장이 가리킨 증거의 그 부분을 줄거리
    # 단계에서 그때 사건에 관한 내용으로 써 두고 미션이 그대로 씀(미션 단계가 지어내면 사건과 무관한
    # 글로 빠졌음)
    missionMaterial: str

    @model_validator(mode="after")
    def _no_empty_texts(self) -> "GeneratedDay":
        """글 칸이 비면 형식 밖 응답으로 본다(LLM_INVALID_OUTPUT → 한 번 더 부름).

        #535 8차: 줄거리 한 번이 다섯 요일의 증거 발견 줄·수사 연결 문장 10칸을 비워
        REQUIRED로 다시 생성. JSON 스키마는 바꾸지 않는다(검증만).
        """
        empty = [
            k
            for k in ("place", "sceneNote", "clue", "discovery", "missionHook", "missionMaterial")
            if not getattr(self, k).strip()
        ]
        if empty:
            raise ValueError(f"{self.day} 빈 칸 {empty}")
        return self


# 그 컷 끝 뭉치 표정(입 모양으로만: smile 웃는 입, surprised 작은 o 입, determined 다문 일자 입).
# 뭉치가 나오지 않는 컷은 none
MungchiMood = Literal["none", "smile", "surprised", "determined"]
# #779(기준안 2026-11-18): 컷 카메라. 실측에서 문제없던 것만(다가가기 push-in은 발이 잘려 뺌).
# FOLLOW_BEHIND 앞으로 걸어가는 인물을 뒤에서 따라감, TRACK_SIDE 옆으로 이동하는 인물을 옆에서
# 따라감, PAN_SIDE 넓은 장면·모인 장면을 천천히 옆으로 훑음, HOLD_CLOSE 가까운 장면을 그대로 유지
# #779(2026-11-19): PUSH_SLOW 얼굴 클로즈업에서만 천천히 조금 다가감(6컷 틀은 카메라를 코드가 정함)
CameraMove = Literal["FOLLOW_BEHIND", "TRACK_SIDE", "PAN_SIDE", "HOLD_CLOSE", "PUSH_SLOW"]


class GeneratedCut(BaseModel):
    """시작·종료 영상 콘티의 한 컷(#779 새 테마 6컷 × 4초, 예전 초안 4컷 4·6·8·6초).

    caption은 자막 있는 컷만(그 밖은 코드가 빈 글로, cuts.LAYOUTS).

    내부 칸이라 응답 theme에는 넣지 않는다. camera는 #779 칸이라 그 전에 저장된 테마(부분 다시
    생성)·시험 자료에는 없을 수 있어 기본값을 둔다(LLM 스키마는 strict라 필수).
    """

    scene: str
    action: str
    caption: str
    mungchiMood: MungchiMood
    camera: CameraMove = "PAN_SIDE"


class GeneratedTheme(BaseModel):
    """줄거리 출력. storyType·incident·answerLook은 #634, branch는 #782 내부 칸(응답 theme에 넣지
    않음).

    기본값은 #634 전 테마·시험 고정 자료용이고, LLM 스키마는 strict라 모두 필수(기본값 제거).
    storyType은 주제가 learning 씨앗이면 코드가 주제에서 읽은 값으로 덮어쓴다(plan_theme).
    """

    storyType: StoryTypeCode = "LOST"
    # 갈래(#782 기준안 — 확인 전, 내부 칸): 종류마다 정한 목록 안 값(families.STORY_BRANCHES),
    # 갈래가 없는 종류는 null. 주제 글에 갈래가 있으면 plan_theme이 덮어쓰고, 목록 밖 값은 None으로
    branch: str | None = None
    title: str
    world: str
    characters: list[GeneratedCharacter]
    styleNote: str
    outfit: str
    intro: str
    outro: str
    bigQuestion: str
    target: str
    # 동물 주인공 가족(③)만: 사건 물건·일 한 줄(미션 소재), 정답 동물 겉모습 한 줄(종료
    # 그림). 그 밖 종류는 null
    incident: str | None = None
    candidates: list[str]
    answer: str
    answerLook: str | None = None
    # #779 컷 장소(cuts.PLACE_KEY): 사건 장소(시작 콘티·종료 1컷)와 정답 장소(종료 3~6컷)의 모습 한
    # 줄씩. 컷 그림 지시에 코드가 넣음. 6컷 테마는 필수(REQUIRED), 예전 테마는 없음
    introPlace: str | None = None
    outroPlace: str | None = None
    features: list[GeneratedFeature]
    days: list[GeneratedDay]
    introCuts: list[GeneratedCut]
    outroCuts: list[GeneratedCut]


class GeneratedLine(BaseModel):
    speaker: str
    text: str


class GeneratedDialogue(BaseModel):
    """미션 전 대화 전체(#782 테마 짜임, 사용자 결정 2026-11-19: 모델이 처음부터 끝까지 씀. 전에는
    증거 발견 줄·수사 연결 문장을 코드가 끝 두 줄로 넣었음)."""

    lines: list[GeneratedLine]


class GeneratedFix(BaseModel):
    path: str  # 받은 칸 경로 그대로(예: TUE.clue, title, introCuts2.caption)
    text: str


class GeneratedFixes(BaseModel):
    """줄거리 검사가 칸 하나만 고치면 되는 사유(길이·증거 발견 줄 단서 값·후보 이름)로만 실패했을
    때 그 칸만 고쳐 쓴 결과(fix_theme). 다른 칸은 그대로 둔다."""

    fixes: list[GeneratedFix]


class GeneratedHookFixes(GeneratedFixes):
    """미션이 통과한 뒤 그 요일 수사 연결 문장을 문제 소재에 맞게 고쳐 쓴 결과(fix_hook, #535).
    모양은 GeneratedFixes와 같고 path는 `<요일>.missionHook`."""


class GeneratedExampleFix(BaseModel):
    """미션 검토가 예시 답 미완성(EXAMPLE_COMPLETE)으로만 실패했을 때 질문은 그대로 두고 예시 답만
    고쳐 쓴 결과. finalAnswer는 풀이(SOLUTION_STEPS)만, 아니면 null."""

    exampleAnswer: str
    finalAnswer: str | None


class StoryReviewItem(BaseModel):
    id: StoryReviewId
    verdict: ReviewVerdict
    days: list[Day]
    reason: str


class GeneratedStoryReview(BaseModel):
    items: list[StoryReviewItem]


class FollowVerdict(BaseModel):
    """이어 가기 판정(#971): 이어 가기 날 하나의 자연/억지와 근거 한 문장. 그래프 밖 측정
    판정(저장소 밖 judge_follow.py)이 씀 — 그래프 안에서는 글 검토 NEXT_FIT이 같은 기준으로 봄."""

    day: Day
    flow: Literal["NATURAL", "FORCED"]
    reason: str


class GeneratedFollowJudge(BaseModel):
    items: list[FollowVerdict]


class MissionReviewItem(BaseModel):
    id: MissionReviewId
    verdict: ReviewVerdict
    reason: str


class GeneratedMissionReview(BaseModel):
    verdict: ReviewVerdict
    items: list[MissionReviewItem]


# MISSION_FIT(미션 그림만: 질문·생각 열기가 가리키는 것이 다 보이는지)·SCENE_FIT(장면 일치)
# FLOW: 잇는 컷이 앞 컷 그림과 장소·물건 상태가 이어지는지(#779 B안)
# PEOPLE: 등장인물 기준 그림과 같은 사람인지(#779 설계 C표). FRAME: 구도 틀의 검토 핵심(설계 H)
ImageReviewId = Literal[
    "MUNGCHI",
    "ANSWER_HINT",
    "TEXT",
    "SAFETY",
    "MISSION_FIT",
    "SCENE_FIT",
    "FLOW",
    "PEOPLE",
    "FRAME",
]
VideoReviewId = Literal["MORPH", "ANSWER_HINT", "TEXT", "SAFETY", "CONTINUITY"]


class ImageReviewItem(BaseModel):
    id: ImageReviewId
    verdict: ReviewVerdict
    reason: str


class GeneratedImageReview(BaseModel):
    """그림 1장 검토(검토 모델이 그림을 봄)."""

    items: list[ImageReviewItem]


class VideoReviewItem(BaseModel):
    id: VideoReviewId
    verdict: ReviewVerdict
    reason: str


class GeneratedVideoReview(BaseModel):
    """영상 컷 1개 검토(2초마다 뽑은 장면을 봄)."""

    items: list[VideoReviewItem]


class GeneratedPoint(BaseModel):
    x: float
    y: float
    zoom: float


class GeneratedSpeaker(BaseModel):
    name: str
    x: float
    y: float


class GeneratedEffect(BaseModel):
    shape: EffectShape
    color: str
    count: int
    size: float
    direction: int
    speed: float
    opacity: float


class GeneratedSpot(BaseModel):
    label: str
    line: str
    evidence: bool
    x: float
    y: float


class GeneratedMotion(BaseModel):
    """생성 모델이 그림을 보고 정하는 움직임 값. 상한은 코드가 맞춘다(checks.motion·checks.spots).

    spots는 요일 장면에서 살펴보기로 누를 그림 속 물건(시작·종료는 빈 목록).
    """

    transition: TransitionKind
    transitionSeconds: float
    cameraFrom: GeneratedPoint
    cameraTo: GeneratedPoint
    cameraSeconds: float
    speakers: list[GeneratedSpeaker]
    effects: list[GeneratedEffect]
    spots: list[GeneratedSpot]
