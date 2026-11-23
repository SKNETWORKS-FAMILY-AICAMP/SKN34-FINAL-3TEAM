"""테마 초안 글 단계 시험 자료: 검사를 모두 통과하는 초3 줄거리·미션·대화.

줄거리(후보 4개, 정답 텃밭):
- 특징 표: 땅(놀이터 모래·텃밭 흙·창고 시멘트·정자 흙),
  지붕(놀이터·텃밭 없음, 창고·정자 있음), 물기(놀이터·텃밭 젖음, 창고·정자 마름)
- 월 RULE(물기 젖음 → 창고·정자), 화 STORY(사건 단서), 수 HINT(지붕 없음), 목 STORY,
  금 RULE(땅 흙 → 놀이터·창고) → 목요일까지 놀이터·텃밭 2개 남고, 마지막 틀린 후보(놀이터)는
  금요일에 빠짐(#782 테마 짜임: 후보를 빼지 않는 날은 사건 단서, 앞 요일 단서를 되풀이하지 않음)
- 증거 종류는 기본 요청(helpers.request_body)의 코드 배정과 같음: 월 흔적·화 목격·수 목격·목 흔적·
  금 기록(일지)
- 뭉치는 구조대로 출동한 해결사, 보리의 주인은 지호. 요일마다 증거 발견 줄(discovery)과
  수사 연결 문장(missionHook)은 단서 결론(허용 값)·후보·정답을 말하지 않음
"""

import copy
from typing import Any

from app.mission_draft.prompts import GeneratedAnswerKey, GeneratedDraft, GeneratedElement
from app.theme_draft.checks import REVIEW_IDS
from app.theme_draft.models import (
    GeneratedDialogue,
    GeneratedHelperJudge,
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
    "FRI": "가게 주인의 일지를 찾았어! 그때가 적혀 있을지 몰라.",
}
# 증거에서 오늘 할 일(수사 연결, 대화 재료, 40자 이내). #782: 증거의 한 부분과 활동을 말함
HOOK = {
    # #782 미션 방식: 부탁 날(기본 요청 배정 월·수·목·금)은 돕는 사람의 일만 말하고
    # 흔적·기록 낱말을 쓰지 않음(EVIDENCE_EARLY)
    "MON": "공원 안내문에 보리 산책 이야기가 있어. 같이 까닭을 살펴볼래?",
    "TUE": "할머니 말에 보리 모습이 더 있어. 사실과 의견을 나눠 볼래?",
    "WED": "그 아이 말에 보리가 한 일도 있어. 같이 새 생각을 더해 볼래?",
    "THU": "보리 산책 길 사이를 잰 값도 있어. 같이 늘어난 길이를 구해 볼래?",
    "FRI": "가게 안내판에 그날 시간도 적혀 있어. 같이 이번 주를 돌아볼래?",
}
# 그날 미션 지문이 될 증거 내용(내부 칸 missionMaterial, #782). 그날 단서 값(젖음·없음·흙)·후보
# 이름은 없음
MATERIAL = {
    "MON": "지호의 일지: 보리는 비가 그치자 공을 물고 마을 길로 달려 나갔다. 지호가 부르자 한 번 "
    "돌아보고 다시 달렸다.",
    "TUE": "이웃 할머니의 말: 보리가 꼬리를 흔들며 내 앞을 지나갔어. 조금 뒤에 지호가 보리를 "
    "부르며 따라왔지.",
    "WED": "본 아이의 말: 보리가 나비를 쫓아 길모퉁이를 돌았어. 나비가 날아가자 한참 냄새를 "
    "맡았어.",
    "THU": "발자국 사이를 잰 값: 첫째 30cm, 둘째 45cm, 셋째 60cm.",
    "FRI": "가게 주인의 일지: 4시 비 그침, 4시 10분 보리 산책 시작, 4시 30분 보리가 보이지 않음.",
}
# 오늘 온 까닭(내부 칸 dayStep, #782 테마 짜임). 앞 요일·그날 단서 값(젖음·없음·흙)·후보 이름은 없음
STEP = {
    "MON": "보리가 사라진 길부터 살펴보러 왔어.",  # 대화 첫 줄로 지호가 말함(SELF_NAME)
    # 화~금은 오늘 여기 온 까닭, 어제 일은 들은 것만(#782 설계 v7 DAY_STEP_MADE)
    "TUE": "공원 관리인 말을 듣고 빵집 앞까지 왔어.",
    "WED": "빵집 아저씨 이야기를 듣고 길모퉁이로 왔어.",
    "THU": "꽃집 할머니가 알려 준 골목 안쪽으로 왔어.",
    "FRI": "문구점 사장님 말을 따라 가게 앞까지 왔어.",
}
# 그날 장소 사람(내부 칸 helper, #782 테마 짜임 미션 방식). missionWay가 없으면 수사(예전
# 저장본과 같음)
HELPER = {
    "MON": "공원 관리인",
    "TUE": "빵집 아저씨",
    "WED": "꽃집 할머니",
    "THU": "골목 문구점 사장님",
    "FRI": "가게 주인",
}
TYPE_DAY = {t: d for d, t in DAY_TYPES.items()}
# 그날 돕는 사람의 약속 줄(#782 설계 v10: 요일마다 다른 말, 기록 날은 자기 기록)
PROMISE = {
    "MON": "도와주면 그때 본 걸 알려 줄게.",
    "TUE": "같이 봐 주면 내가 아는 것도 말해 줄게.",
    "WED": "도와주면 그날 내가 본 걸 말해 줄게.",
    "THU": "같이 해 주면 그때 본 것도 알려 줄게.",
    "FRI": "도와주면 내 일지를 보여 줄게.",
}


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
        # #782 미션 방식: 부탁 날 장면 메모에는 흔적을 쓰지 않음(EVIDENCE_EARLY)
        "sceneNote": "뭉치와 지호가 그곳 사람을 만나 하는 일을 살펴보는 장면",
        "clue": clue,
        "clueType": clue_type,
        "condition": {"kind": kind, "feature": feat, "allowed": allowed},
        "evidence": {"kind": ev, "when": "보리가 사라진 날 오후"},
        "discovery": DISCOVERY[d],
        "missionHook": HOOK[d],
        "missionMaterial": MATERIAL[d],
        "dayStep": STEP[d],
        "helper": HELPER[d],
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
        # #779 컷 장소(6컷 테마 필수): 사건 장소·정답 장소 모습
        "introPlace": "그네와 미끄럼틀이 있는 비 온 뒤 마을 놀이터",
        "outroPlace": "고랑마다 상추가 자라는 마을 텃밭",
        "features": [
            feature("땅", {"놀이터": "모래", "텃밭": "흙", "창고": "시멘트", "정자": "흙"}),
            feature("지붕", {"놀이터": "없음", "텃밭": "없음", "창고": "있음", "정자": "있음"}),
            # #782: 값이 하나뿐인 특징의 힌트는 아무것도 알려 주지 않아(CLUE_EMPTY) 창고·정자는 마름
            feature(
                "물기",
                {"놀이터": "젖음", "텃밭": "젖음", "창고": "마름", "정자": "마름"},
                code=STANDARDS["ANALYZE"][0],
            ),
        ],
        "days": [
            # 월요일 힌트는 아직 빠진 후보가 없어 늘 특징 값 전부라(#782 CLUE_EMPTY) RULE로
            # #782 설계 v3 CLUE_SOURCE: 부탁 날 흔적 단서는 돕는 사람이 본 흔적
            day("MON", "내가 본 보리 발자국은 젖어 있었어.", "발자국", "RULE", "물기", ["젖음"]),
            # #782 테마 짜임: 후보를 빼지 않는 날은 사건 단서(STORY), 앞 요일 단서를 되풀이하지 않음
            day(
                "TUE",
                "보리가 공을 물고 골목 쪽으로 달려갔대.",
                "목격",
                "STORY",
                "",
                [],
                "SIGHTING",
            ),
            day(
                "WED",
                "내가 봤는데 보리는 지붕이 없는 곳으로 갔어.",  # 전해 들은 말(~대) 아님
                "소리",
                "HINT",
                "지붕",
                ["없음"],
                "SIGHTING",
            ),
            day(
                "THU",
                "내가 보니 산책 길 사이로 보리 발자국이 골목 안쪽에 이어졌어.",
                "크기",
                "STORY",
                "",
                [],
            ),
            # 마지막 틀린 후보는 금요일에 빠짐(#782 테마 짜임)
            day(
                "FRI",
                "일지에 보리 발바닥에 흙이 묻어 있었다고 적혔어.",
                "기록",
                "RULE",
                "땅",
                ["흙"],
                "RECORD",
            ),
        ],
        "introCuts": copy.deepcopy(INTRO_CUTS),
        "outroCuts": copy.deepcopy(OUTRO_CUTS),
    }


def cut(scene: str, action: str, caption: str, mood: str) -> dict[str, str]:
    return {"scene": scene, "action": action, "caption": caption, "mungchiMood": mood}


# 시작: 1 평소 모습과 주인·2 사건(뭉치 없음, none) → 3 뭉치 혼자 출동·4 현장 도착(none 아님)
# #779(사용자 결정 2026-11-19) 6컷 틀(cuts.LAYOUTS): 시작 1 사람·2 사건 물건·3 사람 리액션·4 뭉치
# 달리기·5 뭉치·6 함께, 종료 1 뭉치·2 뭉치 달리기·3 사람·4 뭉치·5 사람·6 함께. 자막은 시작 1·2·4·6,
# 종료 1·3·6에만('이름: 대사', 시작 1은 장면 소개)
INTRO_CUTS = [
    cut(
        "비 그친 마을 길에서 지호가 보리와 공놀이를 한다",
        "보리가 공을 물고 꼬리를 흔든다",
        "비 그친 오후의 마을 길…",
        "none",
    ),
    cut(
        "길모퉁이에 빈 목줄만 놓여 있고 지호의 손이 목줄을 든다",
        "지호가 빈 목줄을 들어 올린다",
        "지호: 어라? 목줄만 있어!",
        "none",
    ),
    cut(
        "길모퉁이에서 지호가 깜짝 놀란 얼굴로 두리번거린다",
        "지호가 펄쩍 놀라 주위를 둘러본다",
        "",
        "none",
    ),
    cut(
        "주황 조끼를 입은 뭉치가 마을 길 위에 있다",
        "뭉치가 짧은 갈색 발로 옆으로 힘차게 달려간다",
        "뭉치: 구조대 뭉치, 출동!",
        "determined",
    ),
    cut(
        "길모퉁이 앞에 선 뭉치의 얼굴이 크게 보인다",
        "뭉치가 입을 꾹 다물고 몸을 살짝 흔든다",
        "",
        "determined",
    ),
    cut(
        "길모퉁이에 지호가 서 있고 조금 떨어진 곳에 뭉치가 있다",
        "지호가 고개를 끄덕이고 뭉치가 고개를 갸웃한다",
        "뭉치: 어디에 숨었을까?",
        "determined",
    ),
]
OUTRO_CUTS = [
    cut(
        "뒤쪽 나무판에 단서 그림들이 붙어 있고 그 앞에 뭉치의 얼굴이 크게 보인다",
        "뭉치가 고개를 갸웃하다 활짝 웃는다",
        "뭉치: 알았다! 텃밭이야!",
        "surprised",
    ),
    cut(
        "텃밭으로 가는 흙길에 뭉치가 있다",
        "뭉치가 짧은 갈색 발로 옆으로 힘차게 달려간다",
        "",
        "determined",
    ),
    cut(
        "텃밭 고랑에서 지호가 찾은 보리를 안아 올린다",
        "지호가 보리를 안아 올린다",
        "지호: 짜잔! 보리다!",
        "none",
    ),
    cut(
        "텃밭 앞에 선 뭉치의 얼굴이 크게 보인다",
        "뭉치가 놀란 입에서 활짝 웃는다",
        "",
        "surprised",
    ),
    cut(
        "텃밭 앞에서 지호와 보리가 함께 웃는다",
        "지호가 폴짝 뛰며 활짝 웃는다",
        "",
        "none",
    ),
    cut(  # #779 엔딩: 그 컷에 보이는 인물이 뭉치에게 고마워함
        "텃밭 앞에서 보리를 안은 지호가 뭉치 쪽으로 몸을 돌리고 조금 떨어진 곳에 뭉치가 있다",
        "지호가 뭉치를 보며 웃고 뭉치가 쑥스럽게 웃으며 몸을 살짝 흔든다",
        "지호: 고마워, 뭉치!",
        "smile",
    ),
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
        # #782: 줄거리가 정한 그날 지문을 문제 글에 그대로 넣음(MATERIAL_MISSING)
        "question": f"{MATERIAL[TYPE_DAY[thinking_type]]} 이 글을 읽고 까닭과 함께 써 보자.",
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


def dialogue(day: str | None = None, **overrides: Any) -> GeneratedDialogue:
    """미션 전 대화 4줄(모든 학년 4~5줄). 검사 시험은 이 4줄을 그대로 보고, 그래프에서는 코드가
    오늘 온 까닭을 주인공의 말로 앞에 붙여 5줄이 된다(#782 설계 v3). 요일을 주면 셋째 줄은 그날
    돕는 사람의 약속(#782 미션 방식, 부탁 날 ASK_PROMISE — 다른 날에도 그대로 둠). #782 설계 v10:
    요일마다 다른 말이고 금요일(기록 날)은 자기
    일지(ASK_PROMISE 감각)."""
    body: dict[str, Any] = {
        "lines": [
            # 첫날에도 쓰므로 '어제'를 쓰지 않음(#782 DAY1_TIME)
            GeneratedLine(speaker="지호", text="보리를 찾으러 여기까지 왔어."),
            GeneratedLine(speaker="뭉치", text="여기 뭔가 남아 있는 것 같아!"),
            GeneratedLine(
                speaker=HELPER[day] if day else "지호",
                text=PROMISE[day] if day else PROMISE["MON"],
            ),
            GeneratedLine(speaker="뭉치", text="여기 적힌 것을 같이 살펴볼래?"),
        ],
    }
    body.update(overrides)
    return GeneratedDialogue(**body)


def story_review(
    verdicts: dict[str, str] | None = None,
    days: dict[str, list[str]] | None = None,
    promise_days: list[str] | None = None,
) -> GeneratedStoryReview:
    """promise_days: CLUE_LOGIC 중 약속 줄만 틀린 요일(#782 설계 v12)."""
    ids = REVIEW_IDS  # #782 설계 v13: HELPER_FIT 포함
    verdicts, days = verdicts or {}, days or {}
    return GeneratedStoryReview(
        items=[
            StoryReviewItem(
                id=i,
                verdict=verdicts.get(i, "PASS"),
                days=days.get(i, []),  # type: ignore[arg-type]
                reason=f"{i} 사유",
                promiseDays=(promise_days or []) if i == "CLUE_LOGIC" else [],  # type: ignore[arg-type]
            )
            for i in ids
        ]
    )


def helper_judge(forced: dict[str, str] | None = None) -> GeneratedHelperJudge:
    """돕는 사람 판정(#782 설계 v13 가). forced: {요일: 근거}만 FORCED, 나머지 요일은 NATURAL."""
    forced = forced or {}
    return GeneratedHelperJudge.model_validate(
        {
            "items": [
                {
                    "day": d,
                    "flow": "FORCED" if d in forced else "NATURAL",
                    "reason": forced.get(d) or "자연스러움",
                }
                for d in ("MON", "TUE", "WED", "THU", "FRI")
            ]
        }
    )


def mission_review(verdicts: dict[str, str] | None = None) -> GeneratedMissionReview:
    verdicts = verdicts or {}
    items = [
        # type: ignore[arg-type]
        MissionReviewItem(id=i, verdict=verdicts.get(i, "PASS"), reason=f"{i} 사유")
        for i in ("EXAMPLE_COMPLETE", "STANDARD_FIT", "MATERIAL", "STORY_LINK")
    ]
    overall = "FAIL" if "FAIL" in verdicts.values() else "PASS"
    return GeneratedMissionReview(verdict=overall, items=items)  # type: ignore[arg-type]
