"""테마 초안 글 단계 시험 자료: 검사를 모두 통과하는 초3 줄거리·미션·대화.

줄거리(후보 4개, 정답 텃밭):
- 특징 표: 땅(놀이터 모래·텃밭 흙·창고 시멘트·정자 흙),
  지붕(놀이터·텃밭 없음, 창고·정자 있음), 물기(모두 젖음)
- 월·화 HINT(물기), 수 RULE(지붕 없음 → 창고·정자), 목 RULE(땅 흙 → 놀이터·창고),
  금 HINT(물기) → 수요일까지 놀이터·텃밭 2개 남고, 마지막 틀린 후보(놀이터)는 목요일에 빠짐
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
    rules_out: list[str],
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
        "rulesOut": rules_out,
    }


def valid_theme() -> dict[str, Any]:
    """check_theme(grade=3)을 통과하는 줄거리(GeneratedTheme.model_dump() 모양)."""
    return {
        "title": "보리를 찾아라",
        "world": "작은 마을의 비 온 뒤 오후",
        "characters": [{"name": "지호", "look": "노란 우비를 입은 아이"}],
        "styleNote": "밝은 수채화",
        "outfit": "주황 조끼",
        "intro": "비가 그친 오후, 강아지 보리가 사라졌어요. 뭉치와 지호가 단서를 모아요.",
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
            day("MON", "보리 발자국이 젖어 있었어.", "발자국", "HINT", "물기", ["젖음"], []),
            day(
                "TUE",
                "보리 털이 비에 젖어 반짝였대.",
                "물기",
                "HINT",
                "물기",
                ["젖음"],
                [],
                "SIGHTING",
            ),
            day(
                "WED",
                "보리는 지붕이 없는 곳으로 갔대.",
                "목격",
                "RULE",
                "지붕",
                ["없음"],
                ["정자", "창고"],
                "SIGHTING",
            ),
            day(
                "THU",
                "보리 발바닥에 흙이 묻어 있었어.",
                "재질",
                "RULE",
                "땅",
                ["흙"],
                ["놀이터", "창고"],
            ),
            day(
                "FRI",
                "보리가 지나간 길에 젖은 자국이 남았어.",
                "냄새",
                "HINT",
                "물기",
                ["젖음"],
                [],
                "RECORD",
            ),
        ],
    }


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
    """초3 미션 초안(생각 열기 3개). SOLVE는 풀이(최종 답), 나머지는 서술."""
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


def dialogue(d: str, speaker: str = "지호", **overrides: Any) -> GeneratedDialogue:
    """초3 대화(단서 줄 포함 2~3줄). 월요일은 recap 없음."""
    body: dict[str, Any] = {
        "recap": None if d == "MON" else "앞에서 모은 단서를 다시 볼까?",
        "lines": [GeneratedLine(speaker="뭉치", text="여기 뭔가 있어!")],
        "clueSpeaker": speaker,
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
