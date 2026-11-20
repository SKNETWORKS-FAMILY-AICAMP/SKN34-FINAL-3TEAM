"""컷 구도 틀(#779 설계 H, 사용자 결정 2026-11-19).

컷 표(cuts.CutSpec.frame)는 틀 이름만 가리키고, 틀마다 꼭 지킬 구도·얼굴 규칙 예외·카메라·조명
(수수께끼 여부)·그림 검토 핵심·변형을 한 곳에 둔다. 구도를 고칠 때는 틀 하나만 고친다.

틀을 둔 까닭: 구도 문장이 컷 표·종류 문구·공통 규칙에 흩어져 서로 부딪혔음. 공통 "모든 얼굴이 잘
보이게"가 엔딩 "인물들이 옆모습으로 뭉치를 봄"과 부딪혀 그림 모델이 인물을 카메라 쪽으로 돌렸음
(문제 컷 다시 그리기 2026-11-19, 엔딩 3장 중 2장). 그래서 얼굴 규칙도 틀이 정한다(faces).

변형은 테마마다 코드가 하나를 고른다(같은 테마·컷은 늘 같은 변형, 다시 만들어도 같음). 매주 구도가
조금씩 달라지게 하려는 것이고, 꼭 지킬 관계(image)는 변형과 상관없이 같다.

수수께끼 모험물 컷신 느낌(사용자 결정 2026-11-19): 사건 컷 수수께끼 조명(mystery)과 얼굴
클로즈업만 천천히 다가감(camera PUSH_SLOW)은 틀이 정한다. 뭉치 혼자 클로즈업(MUNGCHI_CLOSE)은 Veo를
쓰지 않고 표정 그림 두 장을 코드가 천천히 확대하며 잇는다(cuts.CutSpec.end_mouth, #779 A안).

멈춤 규칙(설계 H 5): 틀이나 변형을 두 번 고쳐도 그림 모델이 따르지 않으면 문장을 더 손보지 않고
이미 잘 나온 더 단순한 틀로 바꾼다.

검토 핵심(core) 쓰는 법(재검토 2026-11-20): '그림에 무엇이 보이는지'로만 쓴다. '누가 어디를 봄'은
구도가 방향을 정해 주는 틀(배웅·엔딩의 앞쪽 뒷모습)에만 쓴다. 핵심은 틀마다 한 문장인데 종류별
역할은 제각각이라(어느 길: 나른 사람에게 인사, 보물 쪽지: 함께 들여다봄) '대상을 봄'·'서로를 봄'을
핵심에 두면 틀대로 그려도 FRAME이 떨어진다(대표 5종 2차 경고 "서로 보는지 분명하지 않다" 2건). 한
줄 서기는 WARN(rules NO_ROW, 사용자 결정 2026-11-19)이라 핵심에 넣지 않는다.
"""

import zlib
from dataclasses import dataclass
from typing import Literal

Faces = Literal["front", "angle", "side", "back"]

# 얼굴 규칙(틀마다). 예전 공통 "Every face is clearly visible."은 front만
FACE_TEXT: dict[str, str] = {
    "front": "Every face is clearly visible.",
    "angle": "Every face is clearly visible, in front or three-quarter view.",
    "side": "Every face is clearly visible, in profile or three-quarter view as the composition "
    "says; the people do not need to face the viewer.",
    "back": "People may be seen from the side or from behind as the composition says; their "
    "faces do not need to face the viewer.",
}

# #779(3테마 실행 2026-11-18): 시작 1컷이 가까운 장면이면 장소가 안 보임. 넓은 장면으로 고정
WIDE_SHOT = (
    "Wide establishing shot: the whole place is visible and the people are seen full body, "
    "smaller in the scene."
)
# 가까운 장면은 어깨 위·손은 몸에 맞게(시제품에서 주먹이 얼굴보다 크게 그려짐)
CLOSE_SHOT = (
    "Close shot: the people are seen from the shoulders up with hands in natural size; anything "
    "held is at chest height and does not cover their faces."
)
# #779(사용자 결정 2026-11-19): 뭉치 혼자 나오는 가까운 장면. 위쪽은 자막 자리로 비움
MUNGCHI_CLOSE_SHOT = (
    "Close shot of Mungchi alone from the chest up, its face large and clearly visible, with "
    "empty space above its head for a caption; the place shows softly behind it."
)
# #779(사용자 결정 2026-11-19, 수수께끼 모험물 컷신 느낌): 사건 컷만 살짝 신비롭게, 무섭지 않게
# 시간대는 박지 않음: "bright afternoon daylight"가 밤 이야기(소리 탐정)의 시작 2·3컷을 낮으로
# 바꿨음(재검토 2026-11-20, 시작 1컷은 밤)
MYSTERY_LIGHT = (
    "A touch of mystery: soft long shadows and slightly cooler tones, in the scene's own time of "
    "day; the picture stays bright and gentle, never dark or scary."
)


@dataclass(frozen=True)
class Frame:
    id: str
    image: str  # 꼭 지킬 구도(영어, 그림 지시)
    variants: tuple[str, ...]  # 테마마다 하나(영어)
    faces: Faces
    camera: str  # 영상 카메라(models.CameraMove)
    core: str  # 그림 검토 핵심(한국어, 빠지면 FRAME FAIL — 그림에 보이는 것으로만, 머리말)
    mystery: bool = False  # 사건 컷 수수께끼 조명


FRAMES: dict[str, Frame] = {
    f.id: f
    for f in (
        Frame(
            "WIDE_INTRO",
            f"{WIDE_SHOT} The people are at different distances, busy with their usual tasks.",
            (
                "The camera looks across the place from the left side.",
                "The camera looks across the place from the right side.",
                "A slightly high viewpoint looks down over the place.",
            ),
            "angle",
            "PAN_SIDE",
            "장소가 한눈에 보이는 넓은 장면",
        ),
        Frame(
            "OBJECT_CLOSE",
            # 실제 그림은 인물 어깨 위(옆얼굴)와 손으로 그려짐(대표 5종 4/4). 예전 글 "어깨와
            # 손만"이 얼굴 규칙·컷 표 표정(눈·입)과 부딪혀 그려지는 대로 맞춤(재검토 2026-11-20)
            "Close shot of the incident object or spot, large in the picture; one person is at one "
            "side, seen from the shoulders up, with a natural-size hand.",
            (
                "The object is on the left side and the person's hand on the right.",
                "The object is on the right side and the person's hand on the left.",
                "The object is seen slightly from above.",
            ),
            "side",
            "PUSH_SLOW",
            "사건 대상(물건·동물·자리)이 크게 보임",
            mystery=True,
        ),
        Frame(
            "REACTION",
            f"{CLOSE_SHOT} They look toward the incident spot just outside the picture.",
            (
                "They stand side by side, turned at an angle.",
                "One stands slightly in front of the other, overlapping.",
            ),
            "angle",
            "HOLD_CLOSE",
            "인물들의 놀란 얼굴이 크게 보임",
            mystery=True,
        ),
        Frame(
            "RUN",
            "Mungchi alone runs sideways along the way, facing the viewer.",
            ("Mungchi runs from left to right.", "Mungchi runs from right to left."),
            "front",
            "TRACK_SIDE",
            "뭉치가 정면을 본 채 옆으로 달림",
        ),
        Frame(
            "MUNGCHI_CLOSE",
            MUNGCHI_CLOSE_SHOT,
            (
                "Mungchi is on the left third of the picture.",
                "Mungchi is in the center of the picture.",
                "Mungchi is on the right third of the picture.",
            ),
            "front",
            "PUSH_SLOW",
            "뭉치가 정면으로 크게 보임",
        ),
        Frame(
            "GROUP_QUESTION",
            f"{WIDE_SHOT} The people stand together on one side looking at the incident spot; "
            "Mungchi stands apart on the other side, facing the viewer.",
            (
                "The people are on the left and Mungchi on the right.",
                "The people are on the right and Mungchi on the left.",
            ),
            "side",
            "PAN_SIDE",
            "뭉치와 인물들이 서로 떨어져 한 그림에 있음",
        ),
        Frame(
            "REVEAL",
            # 드러나는 것이 사람(어느 길: 나른 사람, 시간 탐정: 그 일을 한 사람)인 종류도 있어
            # "대상을 봄"만으로 쓰지 않음(재검토 2026-11-20)
            f"{CLOSE_SHOT} What this cut reveals (the found target or answer, or the person the "
            "story beat names) is in the same picture, and the people turn toward it.",
            (
                "The revealed answer is in the center between the people.",
                "The revealed answer is at one side and the people turn toward it.",
            ),
            "side",
            "HOLD_CLOSE",
            "이 컷에서 드러나는 것(찾은 대상·정답, 또는 장면 글이 말한 사람·물건)이 그림에 보임",
        ),
        # 배웅(동물 종류 종료 5컷). '등·옆모습'을 직접 시킨 배웅은 문제 컷 다시 그리기에서 나아졌음
        Frame(
            "FAREWELL",
            "The people are in the foreground, seen from the side or from behind, all looking "
            # 가는 곳을 덤불로 박지 않음(오리는 물가 — 종류 역할 "제가 사는 쪽", 재검토 2026-11-20)
            "toward the animal; the animal is in the background, walking away toward where it "
            "lives (bushes, woods or water, as the scene says) and glancing back.",
            (
                "The animal is on the left in the background.",
                "The animal is on the right in the background.",
            ),
            "back",
            "PAN_SIDE",
            "인물들이 뒤쪽의 동물 쪽을 봄",
        ),
        Frame(
            "JOY",
            # 예방(재검토 2026-11-20): "서로 마주 보고"만 쓰면 '함께 들여다봄'(보물 쪽지·작은 생물)
            # 컷에서 무엇을 우선할지 흐려질 수 있어 하는 일은 할 일 글대로
            "The people are together close to each other, sharing the moment as the story beat "
            "says (celebrating, or looking at something together).",
            (
                "Two people are on one side and the others on the other side.",
                "The people stand close together in a small circle.",
            ),
            "side",
            "PAN_SIDE",
            "인물들이 기쁘거나 안도한 얼굴로 함께 있음",
        ),
        # 엔딩(종료 6컷). 옆모습으로 마주보게 한 두 번(대표 5종 콘티 3/3, 틀 확인 1/4) 모두
        # 인물들이 카메라 쪽이나 서로를 봐서, 멈춤 규칙대로 배웅(FAREWELL)에서 잘 나온 앞쪽 뒷모습
        # 방식으로 바꿈 — 얼굴 방향을 구도 자체로 정함(2026-11-19)
        Frame(
            "FACING_MUNGCHI",
            f"{WIDE_SHOT} The people are in the foreground, seen from behind or at a "
            "three-quarter back angle, all looking at Mungchi; Mungchi stands a little further "
            "back, apart from them, facing the viewer.",
            (
                "Mungchi is on the left side, a little further back.",
                "Mungchi is on the right side, a little further back.",
                "Mungchi is in the middle, a little further back, with the people on both sides "
                "in the foreground.",
            ),
            "back",
            "PAN_SIDE",
            "인물들이 뭉치 쪽을 봄",
        ),
    )
}


def variant(frame: Frame, key: str) -> str:
    """테마·컷마다 같은 변형(key = 테마 제목·컷). 다시 만들어도 같은 구도."""
    return frame.variants[zlib.crc32(key.encode("utf-8")) % len(frame.variants)]
