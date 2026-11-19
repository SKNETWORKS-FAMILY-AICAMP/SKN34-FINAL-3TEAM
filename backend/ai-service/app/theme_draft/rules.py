"""공통 규칙 목록(#779 설계 C·H, 사용자 결정 2026-11-19).

규칙 하나 = 항목 하나. 항목 안에 어느 컷에 붙는지(적용 조건)와 그림 지시·영상 지시·영상 금지 목록
낱말·검토 문장·등급을 함께 두고, 지시와 검토는 이 목록에서 만든다. 규칙을 고칠 때는 항목 하나만
고친다.

목록을 둔 까닭: 규칙이 문장 상수로 흩어져 그림 지시·영상 지시·금지 목록·검토 지시에 손으로 하나씩
붙어 있어, 하나를 바꾸면 네다섯 곳을 고쳐야 했고 빠뜨리면 부딪혔음(예: "뭉치는 물건을 들지 않음"이
대상을 감추는 줄에 얹혀 동물 장난꾸러기 컷에는 아예 없었음, 2종류 × 12컷 대조 2026-11-19).

적용 조건(when): mungchi = 뭉치가 나오는 컷, people = 사람이 나오는 컷, people6 = 사람이 나오는 6컷
컷(예전 4컷 초안 영상은 예전 동작 그대로), wild = 야생 동물이 정답인 종류(동물 장난꾸러기·발자국
주인·소리의 동물), all = 모든 컷. 시험(test_design_walkthrough)이 항목마다 그 조건의 컷에 들어갔는지
본다.

아직 이 목록 밖(각자 한 곳에서 쓰는 규칙): 뭉치 모습(MUNGCHI_LOOK·MUNGCHI_KEEP), 글자 없음
(IMAGE_RULES·TEXT 검토), 화면 밖·길로만 움직임(영상 지시 고정 줄), 2D 그림체. 얼굴 규칙은 구도 틀
(frames.FACE_TEXT)이 정한다.
"""

from dataclasses import dataclass
from typing import Literal

When = Literal["all", "mungchi", "people", "people6", "wild", ""]


@dataclass(frozen=True)
class Rule:
    id: str
    image: str = ""  # 그림 지시(영어)
    image_when: When = ""
    video: str = ""  # 영상 지시(영어)
    video_when: When = ""
    negative: str = ""  # 영상 금지 목록 낱말(영어)
    negative_when: When = ""
    review_item: str = ""  # 그림 검토 항목(MUNGCHI·SAFETY·SCENE_FIT)
    review: str = ""  # 그 항목에 붙는 판정 문장(한국어)
    fail: str = ""  # 등급 기준(문서·시험용 설명)
    warn: str = ""


RULES: tuple[Rule, ...] = (
    # #779: 뭉치가 사람 곁에 붙으면 영상 모델이 사람 팔·손을 뭉치에게 옮겨 붙임(3테마 실행 실패 5컷)
    Rule(
        "MUNGCHI_SEPARATE",
        image="Mungchi is its own small separate figure: it does not touch, overlap or merge with "
        "anyone and never takes on a person's arms, hands, legs, hair or clothes.",
        image_when="mungchi",
        video="Mungchi is its own small separate figure: it does not touch, overlap or merge with "
        "anyone and never takes on a person's arms, hands, legs, hair or clothes.",
        video_when="mungchi",
        review_item="MUNGCHI",
        review="뭉치가 사람과 겹치거나 맞닿아 한 몸처럼 보이면 결함.",
        fail="겹쳐 한 몸",
    ),
    # #779 설계 C표: 영상에서만 막던 것을 첫 그림에서도(첫 그림에 들고 있으면 영상도 따라감)
    Rule(
        "MUNGCHI_HOLDS_NOTHING",
        image="Mungchi holds nothing in its hands except outfit items it already wears; it never "
        "holds a story object.",
        image_when="mungchi",
        review_item="MUNGCHI",
        review="뭉치가 차림 소품(목에 걸거나 머리에 쓴 것)이 아닌 물건, 특히 사건 물건이나 찾는 "
        "대상을 들고 있으면 결함.",
        fail="사건 물건·대상을 듦",
    ),
    # #779(3테마 실행 2026-11-18): 뭉치와 동물이 붙어 있으면 영상에서 뭉치가 그 동물(너구리)로 바뀜
    Rule(
        "APART_FROM_ANIMALS",
        image="If an animal appears, it stays apart from Mungchi with clear space between them "
        "and keeps its own look; Mungchi never takes on any animal's features (no tail, no "
        "striped fur, no animal ears or muzzle).",
        image_when="mungchi",
        video="If an animal appears, it stays apart from Mungchi with clear space between them "
        "and keeps its own look; Mungchi never takes on any animal's features (no tail, no "
        "striped fur, no animal ears or muzzle).",
        video_when="mungchi",
        fail="뭉치가 동물 모습이 됨",
    ),
    # 만지기 예외: 그 동물을 돌보거나 데리고 있는 사람(주인·돌보던 아이·길 잃은 동물을 데려가는
    # 아이). 씨앗 "체험 농장 / 아이가 돌보던 아기 염소", "아파트 놀이터 / 길 잃은 강아지"
    Rule(
        "NO_TOUCH",
        image="Nobody touches Mungchi, and nobody touches, lifts or holds an animal, except that "
        "the person who looks after that animal (its owner or carer) may hold it gently.",
        image_when="people",
        video="Nobody touches Mungchi, and nobody touches, lifts or holds an animal, except that "
        "the person who looks after that animal (its owner or carer) may hold it gently.",
        video_when="people6",
        negative="people touching the animal, holding the animal",
        negative_when="wild",
        review_item="SAFETY",
        review="그 동물을 돌보거나 데리고 있는 사람(주인·돌보던 아이·길 잃은 동물을 데려가는 "
        "아이)이 안거나 목줄을 잡거나 쓰다듬는 것은 위험이 아니다. 그 밖의 사람·뭉치가 동물을 "
        "만지거나 안거나 붙잡으면 결함이다.",
        fail="예외 밖에서 만지거나 안거나 붙잡음",
    ),
    # 사람 손(사용자 결정 2026-11-19): 공중 손짓 없음. 물건을 다루는 손은 컷 할 일에 적힌 것만
    Rule(
        "HAND",
        video="No waving and no clapping: the people's hands only hold, open or point at things "
        "as the story beat says.",
        video_when="people6",
        negative="waving, clapping",
        negative_when="all",
        warn="다른 동작",
    ),
    # 한 줄 서기는 WARN(사용자 결정 2026-11-19), 그 컷 핵심이 빠지면 SCENE_FIT FAIL
    Rule(
        "NO_ROW",
        video="The people never line up in a row facing the camera; they keep facing each other "
        "or what they are doing.",
        video_when="people6",
        negative="people standing in a row facing the camera",
        negative_when="all",
        review_item="SCENE_FIT",
        review="인물들이 한 줄로 서서 카메라를 보는 것은 WARN이다.",
        warn="한 줄로 섬",
    ),
)
BY_ID = {r.id: r for r in RULES}


def lines(kind: Literal["image", "video", "negative"], flags: set[str]) -> list[str]:
    """그 컷의 적용 조건(flags)에 맞는 규칙 줄(목록 순서). flags에는 늘 'all'이 들어간다."""
    out = []
    for r in RULES:
        text, when = {
            "image": (r.image, r.image_when),
            "video": (r.video, r.video_when),
            "negative": (r.negative, r.negative_when),
        }[kind]
        if text and when and when in flags | {"all"}:
            out.append(text)
    return out


def review(item: str) -> str:
    """그림 검토 항목에 붙는 판정 문장들(목록 순서)."""
    return " ".join(r.review for r in RULES if r.review_item == item and r.review)
