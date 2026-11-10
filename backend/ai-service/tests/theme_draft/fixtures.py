"""테마 초안 글 단계 시험 자료: 검사를 모두 통과하는 초3 줄거리·미션·대화.

줄거리(후보 4개, 정답 텃밭):
- 특징 표: 땅(놀이터 모래·텃밭 흙·창고 시멘트·정자 흙),
  지붕(놀이터·텃밭 없음, 창고·정자 있음), 물기(모두 젖음)
- 월·화 HINT(물기), 수 RULE(지붕 없음 → 창고·정자), 목 RULE(땅 흙 → 놀이터·창고),
  금 HINT(물기) → 수요일까지 놀이터·텃밭 2개 남고, 마지막 틀린 후보(놀이터)는 목요일에 빠짐
- 뭉치는 구조대로 출동한 해결사, 보리의 주인은 지호. 요일마다 증거 발견 줄(discovery)과
  수사 연결 문장(missionHook)은 단서 결론(허용 값)·후보·정답을 말하지 않음
"""

import copy
from typing import Any

from app.mission_draft.prompts import GeneratedAnswerKey, GeneratedDraft, GeneratedElement
from app.theme_draft.models import (
    GeneratedDialogue,
    GeneratedLine,
    GeneratedMissionReview,
    GeneratedStoryReview,
    GeneratedTheme,
    MissionReviewItem,
    StoryReviewItem,
)
from tests.theme_draft.helpers import DAY_TYPES, STANDARDS

CANDIDATES = ["놀이터", "텃밭", "창고", "정자"]
ANSWER = "텃밭"
# 요일별 (증거 발견 줄, 수사 연결 문장). 둘 다 미션 전 대화 끝 두 줄로 나감
DISCOVERY = {
    "MON": "길에 보리 발자국이 찍혀 있어! 어디로 갔는지 알 수 있을지도 몰라.",
    "TUE": "빵집 아저씨가 보리를 봤대! 그때 모습을 물어보자.",
    "WED": "지호 친구가 보리가 가는 걸 봤대! 들어 보자.",
    "THU": "골목에 보리 발자국이 또 있어! 무엇이 묻었는지 살펴보자.",
    "FRI": "가게 앞 사진에 보리가 찍혔대! 자세히 보자.",
}
HOOK = {  # 증거 발견 줄 다음 뭉치의 수사 연결(대화 마지막 줄, 40자 이내)
    "MON": "발자국을 풀려면 동물이 사는 환경을 알아야 해. 도와줄래?",
    "TUE": "아저씨 말을 따지려면 사실과 의견을 나눠야 해. 도와줄래?",
    "WED": "본 것을 기억하려면 동물의 특징을 알아야 해. 도와줄래?",
    "THU": "발자국 수를 세려면 계산이 필요해. 같이 해 볼래?",
    "FRI": "사진을 보기 전에 이번 주를 돌아보자. 도와줄래?",
}
TYPE_DAY = {t: d for d, t in DAY_TYPES.items()}


def feature(name: str, values: dict[str, str], code: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "standardCode": code,
        "values": [{"candidate": c, "value": v} for c, v in values.items()],
    }


def day(
    d: str,
    clue: str,
    clue_type: str,
    kind: str,
    feat: str,
    allowed: list[str],
    ev: str = "TRACE",
) -> dict[str, Any]:
    return {
        "day": d,
        "thinkingType": DAY_TYPES[d],
        "place": f"마을 {d.lower()} 길",
        "sceneNote": "뭉치와 지호가 강아지 보리의 흔적을 살펴보는 장면",
        "clue": clue,
        "clueType": clue_type,
        "condition": {"kind": kind, "feature": feat, "allowed": allowed},
        "evidence": {"kind": ev, "when": "보리가 사라진 날 오후"},
        "discovery": DISCOVERY[d],
        "missionHook": HOOK[d],
    }


def valid_theme() -> dict[str, Any]:
    """check_theme(grade=3)을 통과하는 줄거리(GeneratedTheme.model_dump() 모양, rulesOut 없음:
    코드가 fill_rules_out으로 채움)."""
    return {
        "title": "보리를 찾아라",
        "world": "작은 마을의 비 온 뒤 오후",
        "characters": [{"name": "지호", "look": "노란 우비를 입은 아이"}],
        "styleNote": "밝은 수채화",
        "outfit": "구조대 주황 조끼",
        "intro": "비가 그친 오후, 지호의 강아지 보리가 사라졌어요. 구조대 뭉치가 출동해요.",
        "outro": "보리는 텃밭 고랑에서 흙투성이로 낮잠을 자고 있었어요.",
        "bigQuestion": "보리는 어디에 숨어 있을까?",
        "target": "강아지 보리",
        "candidates": list(CANDIDATES),
        "answer": ANSWER,
        "features": [
            feature("땅", {"놀이터": "모래", "텃밭": "흙", "창고": "시멘트", "정자": "흙"}),
            feature("지붕", {"놀이터": "없음", "텃밭": "없음", "창고": "있음", "정자": "있음"}),
            feature("물기", {c: "젖음" for c in CANDIDATES}, code=STANDARDS["ANALYZE"][0]),
        ],
        "days": [
            day("MON", "보리 발자국이 젖어 있었어.", "발자국", "HINT", "물기", ["젖음"]),
            day(
                "TUE",
                "보리 털이 비에 젖어 반짝였대.",
                "물기",
                "HINT",
                "물기",
                ["젖음"],
                "SIGHTING",
            ),
            day(
                "WED",
                "보리는 지붕이 없는 곳으로 갔대.",
                "목격",
                "RULE",
                "지붕",
                ["없음"],
                "SIGHTING",
            ),
            day(
                "THU",
                "보리 발바닥에 흙이 묻어 있었어.",
                "재질",
                "RULE",
                "땅",
                ["흙"],
            ),
            day(
                "FRI",
                "보리가 지나간 길에 젖은 자국이 남았어.",
                "냄새",
                "HINT",
                "물기",
                ["젖음"],
                "RECORD",
            ),
        ],
        "introCuts": copy.deepcopy(INTRO_CUTS),
        "outroCuts": copy.deepcopy(OUTRO_CUTS),
    }


def cut(scene: str, action: str, caption: str, mood: str) -> dict[str, str]:
    return {"scene": scene, "action": action, "caption": caption, "mungchiMood": mood}


# 시작: 1 평소 모습과 주인·2 사건(뭉치 없음, none) → 3 뭉치 혼자 출동·4 현장 도착(none 아님)
INTRO_CUTS = [
    cut(
        "비 그친 마을 길에서 지호가 보리와 공놀이를 한다",
        "보리가 공을 물고 꼬리를 흔든다",
        "비가 그친 오후.",
        "none",
    ),
    cut(
        "빈 목줄만 남은 길모퉁이에서 지호가 두리번거린다",
        "지호가 깜짝 놀라 주위를 둘러본다",
        "보리가 사라졌다!",
        "none",
    ),
    cut(
        "주황 조끼를 입은 뭉치가 마을 길을 달려간다",
        "뭉치가 힘차게 달린다",
        "구조대 뭉치 출동!",
        "determined",
    ),
    cut(
        "뭉치와 지호가 길모퉁이에서 마주 본다",
        "둘이 함께 고개를 끄덕인다",
        "보리는 어디에 숨어 있을까?",
        "determined",
    ),
]
# 종료: 1 단서 정리 → 2 정답 장소로 → 3 찾아 주인에게 돌려줌 → 4 함께 기뻐함
OUTRO_CUTS = [
    cut(
        "뭉치가 단서 쪽지를 펼쳐 놓는다",
        "쪽지를 하나씩 짚는다",
        "모은 단서를 정리해 볼까?",
        "determined",
    ),
    cut(
        "뭉치와 지호가 텃밭으로 달려간다", "고랑 사이를 달린다", "지붕 없는 흙밭으로!", "determined"
    ),
    cut(
        "텃밭 고랑에서 찾은 보리를 뭉치가 지호에게 건넨다",
        "지호가 보리를 안아 올린다",
        "찾았다, 텃밭이었어!",
        "surprised",
    ),
    cut("뭉치와 지호와 보리가 함께 웃는다", "모두 폴짝 뛴다", "단서가 길을 알려 줬어.", "smile"),
]


def theme_with(**changes: Any) -> dict[str, Any]:
    theme = valid_theme()
    theme.update(copy.deepcopy(changes))
    return theme


def day_with(theme: dict[str, Any], d: str, **changes: Any) -> dict[str, Any]:
    theme = copy.deepcopy(theme)
    target = next(x for x in theme["days"] if x["day"] == d)
    target.update(changes)
    return theme


def generated_theme(theme: dict[str, Any] | None = None) -> GeneratedTheme:
    return GeneratedTheme.model_validate(theme or valid_theme())


def mission_draft(thinking_type: str, hints: int = 3, **overrides: Any) -> GeneratedDraft:
    """초3 미션 초안(생각 열기 3개). SOLVE는 풀이(최종 답), 나머지는 서술.

    수사 연결 문장은 대화 마지막 줄로 나가므로 질문에 넣지 않는다."""
    code = STANDARDS[thinking_type][0]
    solve = thinking_type == "SOLVE"
    body: dict[str, Any] = {
        "title": "뭉치의 탐정 수첩",
        "question": "뭉치와 지호가 마을 길에서 본 것을 떠올려 보고 까닭과 함께 써 보자.",
        "guide": None,
        "sceneNote": None,
        "choices": None,
        "categories": None,
        "answerKey": GeneratedAnswerKey(choiceIds=None, assignments=None, finalAnswer="579")
        if solve
        else None,
        "exampleAnswer": None if solve else "길이 미끄러웠으니 천천히 걸어야 한다고 생각해.",
        "forbiddenTerms": [],
        "hints": ["무엇을 보았는지 떠올려 볼까?", "왜 그렇게 생각했을까?", "다른 생각도 있을까?"][
            :hints
        ],
        "elements": [
            GeneratedElement(
                code=f"{thinking_type}_X",
                label="요소",
                description="설명",
                goodThought=False,
                standardCode=code,
            )
        ],
    }
    body.update(overrides)
    return GeneratedDraft(**body)


def dialogue(speaker: str = "뭉치", **overrides: Any) -> GeneratedDialogue:
    """초3 대화(증거 발견 줄 포함 2~3줄): LLM 줄 1줄 + 코드가 넣는 증거 발견 줄."""
    body: dict[str, Any] = {
        "lines": [GeneratedLine(speaker="지호", text="여기 뭔가 있는 것 같아!")],
        "discoverySpeaker": speaker,
    }
    body.update(overrides)
    return GeneratedDialogue(**body)


def story_review(
    verdicts: dict[str, str] | None = None, days: dict[str, list[str]] | None = None
) -> GeneratedStoryReview:
    ids = ("CLUE_LOGIC", "ANSWER_HINT", "GRADE_VOCAB", "STANDARD_FIT", "SAFETY")
    verdicts, days = verdicts or {}, days or {}
    return GeneratedStoryReview(
        items=[
            StoryReviewItem(
                id=i,
                verdict=verdicts.get(i, "PASS"),
                days=days.get(i, []),  # type: ignore[arg-type]
                reason=f"{i} 사유",
            )
            for i in ids
        ]
    )


def mission_review(verdicts: dict[str, str] | None = None) -> GeneratedMissionReview:
    verdicts = verdicts or {}
    items = [
        # type: ignore[arg-type]
        MissionReviewItem(id=i, verdict=verdicts.get(i, "PASS"), reason=f"{i} 사유")
        for i in ("EXAMPLE_COMPLETE", "STANDARD_FIT", "MATERIAL")
    ]
    overall = "FAIL" if "FAIL" in verdicts.values() else "PASS"
    return GeneratedMissionReview(verdict=overall, items=items)  # type: ignore[arg-type]
