"""테마 초안 시험 자료. 성취기준 문장은 교육부 고시 별책(저작권법 제7조 제2호) 원문."""

from app.followup.models import LlmVersions
from app.mission_draft.models import Draft
from app.theme_draft.models import (
    Character,
    DialogueLine,
    Theme,
    ThemeDay,
    ThemeDialogue,
    ThemeDraftResponse,
    ThemeMission,
)

STANDARDS = {
    "ANALYZE": (
        "4과02-02",
        "다양한 환경에 서식하는 동물을 조사하여 동물의 생김새와 생활 방식이 "
        "환경과 관련되어 있음을 설명할 수 있다.",
        "NARRATIVE",
    ),
    "EVALUATE": (
        "4국02-04",
        "글에 나타난 사실과 의견을 구분하고 필자와 자신의 의견을 비교한다.",
        "NARRATIVE",
    ),
    "CREATE": (
        "4과02-03",
        "동물의 특징을 이용하여 일상생활에서 활용할 수 있는 생활용품을 설계하여 "
        "협력적으로 소통할 수 있다.",
        "NARRATIVE",
    ),
    "SOLVE": (
        "4수01-03",
        "세 자리 수의 덧셈과 뺄셈의 계산 원리를 이해하고 그 계산을 할 수 있다.",
        "SOLUTION_STEPS",
    ),
    "REFLECT": (
        "4도01-03",
        "성실한 생활의 모범 사례를 탐색하고 시간 관리를 위한 생활을 계획하여 "
        "지속적인 자기 성장을 모색한다.",
        "NARRATIVE",
    ),
}
DAYS = ("MON", "TUE", "WED", "THU", "FRI")
DAY_TYPES = dict(zip(DAYS, STANDARDS, strict=True))


def mission_body(thinking_type: str) -> dict:
    code, statement, input_type = STANDARDS[thinking_type]
    return {
        "thinkingType": thinking_type,
        "inputType": input_type,
        "standards": [{"code": code, "statement": statement}],
        "elementCodes": [{"code": f"{thinking_type}_X", "label": "요소", "description": ""}],
    }


def request_body(grade: int = 3, **overrides) -> dict:
    body = {
        "gradeMin": grade,
        "gradeMax": grade,
        "weekStart": "2026-11-16",
        "topic": "구조대: 길 잃은 강아지 찾기",
        "missions": [mission_body(t) for t in STANDARDS],
        "previousFailures": [],
    }
    return {**body, **overrides}


def sample_response() -> ThemeDraftResponse:
    """그래프가 돌려줄 응답 모양(계약 칸만)."""
    draft = Draft(title="제목", question="질문", hints=["생각 열기"])
    candidates = ["놀이터", "텃밭", "창고", "정자"]
    return ThemeDraftResponse(
        theme=Theme(
            title="보리를 찾아라",
            world="작은 마을",
            characters=[Character(name="지호", look="노란 우비")],
            style_note="밝은 오후",
            outfit="주황 조끼",
            intro="보리가 사라졌어요.",
            outro="정답은 텃밭이에요.",
            big_question="보리를 마지막으로 본 곳은?",
            candidates=candidates,
            answer="텃밭",
            days=[
                ThemeDay(
                    day=d,
                    thinking_type=DAY_TYPES[d],
                    place="마을",
                    scene_note="장면",
                    clue="단서",
                    rules_out=[],
                )
                for d in DAYS
            ],
        ),
        missions=[ThemeMission(day=d, thinking_type=DAY_TYPES[d], draft=draft) for d in DAYS],
        dialogues=[
            ThemeDialogue(day=d, lines=[DialogueLine(speaker="뭉치", text="가 보자")]) for d in DAYS
        ],
        images={},
        videos={},
        motions={},
        warnings=[],
        failure=None,
        versions=LlmVersions(model="fake-model", prompt="theme-draft@1"),
    )
