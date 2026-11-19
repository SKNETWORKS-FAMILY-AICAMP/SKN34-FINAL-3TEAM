"""시작·종료 영상 컷 틀(#779, 사용자 결정 2026-11-18·19).

새 테마는 시작·종료 각 6컷 × 4초("만화 예고편 컷 문법"): 사람이 손으로 하는 동작(안기·열기·손뼉)
곁에 뭉치가 있으면 영상 모델이 사람 팔을 뭉치에게 옮겨 붙여서(3테마 실행 실패 5컷 모두), 사람 컷과
뭉치 컷을 나누고 마지막 단체 컷만 함께(뭉치는 떨어져) 나온다. 자막은 중요한 순간 컷에만(B안,
"이름: 대사" 꼴), 카메라는 컷 역할마다 코드가 정한다.

예전에 저장된 4컷 초안(4·6·8·6초)은 부분 다시 생성(#537)·영상만 다시 만들기에서 예전 동작 그대로
돌도록 4컷 틀을 함께 둔다(카메라는 콘티 camera 칸, 자막은 모든 컷).

컷마다 `role`은 줄거리 종류 콘티 틀(families.StoryType.intro_cuts·outro_cuts, 4개)의 몇 번째 역할
내용을 쓰는지다. 대상·정답이 나와도 되는 컷(target_cuts·answer_cuts, 4컷 번호)도 이 번호로 옮긴다
(families.type_cuts).
"""

from dataclasses import dataclass
from typing import Literal

Who = Literal["PEOPLE", "OBJECT", "MUNGCHI", "RUN", "GROUP"]
Shot = Literal["", "WIDE", "CLOSE", "MUNGCHI_CLOSE"]
# 컷 장소(#779 사용자 결정 2026-11-19): 사건 장소(introPlace)·가는 길·정답 장소(outroPlace). 장소
# 모습은 글 모델이 테마에 한 번만 쓰고(PLACE_KEY 칸) 컷 그림 지시에 코드가 넣는다. 컷마다 글
# 모델이 장소를 정해 종료 3컷 숲 → 5컷 떡집 문가처럼 바뀌었음(경찰관 떡집 콘티 3차). 예전 4컷은 ""
Place = Literal["", "INCIDENT", "ROAD", "ANSWER"]
PLACE_KEY = {"INCIDENT": "introPlace", "ANSWER": "outroPlace"}

NEW_CUTS = 6  # 새 테마 컷 수(기준안)
LEGACY_SECONDS = (4, 6, 8, 6)  # 예전 4컷 초안 컷 길이(사용자 결정 2026-11-11)
NEW_SECONDS = (4, 4, 4, 4, 4, 4)  # 6컷 컷 길이(기준안, theme_video_cut_seconds 기본값)
CAPTION_MAX = {4: 30, 6: 20}  # 컷 자막 글자 상한(6컷은 "이름: " 포함, 기준안)
MUNGCHI_ALONE: tuple[Who, ...] = ("MUNGCHI", "RUN")


@dataclass(frozen=True)
class CutSpec:
    who: Who  # 누가 나오는지: 사람만·사건 물건 클로즈업(사람 손)·뭉치 혼자·뭉치 혼자 달림·함께
    role: int  # 줄거리 종류 콘티 틀의 역할 번호(1~4)
    caption: bool  # 자막을 띄우는 컷인지
    camera: str | None = None  # 카메라(None이면 콘티 camera 칸, 예전 4컷)
    shot: Shot = ""  # 그림 장면 크기
    beat: str = ""  # 컷 할 일(줄거리 콘티 규칙·영상 지시 "Story beat")
    motion: str = ""  # 뭉치 컷 영상 지시(표정 변화 등, 영어)
    speaker: str = ""  # 자막 말하는 사람과 할 말(줄거리 콘티 규칙)
    narrator: bool = False  # 자막이 이름 없는 장면 소개(시작 1컷)
    mystery: bool = False  # 사건 컷 색감(긴 그림자·조금 차가운 빛, 밝은 낮 그대로)
    # 첫 그림 표정(영어). 그림 지시에는 장면(scene)만 들어가 리액션 컷이 웃는 얼굴로 그려졌음
    # (경찰관 떡집 콘티 2026-11-19)
    look: str = ""
    # 이 컷이 잇는 앞 컷 번호(0이면 없음). 컷 그림을 따로 그려 같은 뒤뜰인데 탁자·담이 바뀌고 앞
    # 컷에서 덮은 떡이 다음 컷에서 벗겨졌음(경찰관 떡집 콘티 2026-11-19, 사용자 결정 B안): 그 앞
    # 컷 그림을 참고 그림으로 받아 장소·가구·물건 상태를 잇는다
    follows: int = 0  # 같은 장소(place)의 앞 사람 컷만
    # 내용이 이 할 일 그대로인 컷(줄거리 종류 역할 내용을 붙이지 않음). 종료 6컷(뭉치에게 고마워함)
    # 은 모든 종류가 같은 엔딩(#779 사용자 결정 2026-11-19)
    own: bool = False
    place: Place = ""
    # 사람이 나오는 컷의 4초 움직임(영어, 영상 지시). 예전에는 모든 사람 컷에 공통 "걷기·펄쩍·손
    # 흔들기 같은 큰 동작"이 붙어 컷마다 정한 동작(배웅은 바라보기 등)과 부딪혔음(#779 설계 C표,
    # 2종류 × 12컷 대조 2026-11-19). 공중 손짓(흔들기·손뼉)은 쓰지 않음(사용자 결정 2026-11-19)
    act: str = ""

    @property
    def has_mungchi(self) -> bool:
        return self.who in ("MUNGCHI", "RUN", "GROUP")

    @property
    def has_people(self) -> bool:
        return self.who in ("PEOPLE", "OBJECT", "GROUP")

    @property
    def mungchi_alone(self) -> bool:
        return self.who in MUNGCHI_ALONE


_LEGACY = {
    "INTRO": (
        CutSpec("PEOPLE", 1, True),
        CutSpec("PEOPLE", 2, True),
        CutSpec("RUN", 3, True),
        CutSpec("GROUP", 4, True),
    ),
    "OUTRO": tuple(CutSpec("GROUP", i, True) for i in range(1, 5)),
}

_NEW = {
    "INTRO": (
        CutSpec(
            "PEOPLE",
            1,
            True,
            "PAN_SIDE",
            "WIDE",
            "장소 소개: 장소가 한눈에 보이는 넓은 장면에서 인물들의 평소 모습(뭉치 없음)",
            speaker="이름 없이 장면을 소개하는 짧은 말(예: '평화로운 마을 떡집…')",
            narrator=True,
            look="Everyone looks relaxed and calm, busy with their usual tasks.",
            place="INCIDENT",
            act="The people keep doing their usual tasks with small, natural movements.",
        ),
        CutSpec(
            "OBJECT",
            2,
            True,
            "PUSH_SLOW",
            "CLOSE",
            # 소리 탐정(소리를 듣고 귀 기울임)·탈것(온 사람과 인사함)처럼 물건이 없는 종류도 있어
            # '역할 2의 사건을 알 수 있는 것'으로 씀(#779 종류 11 × 컷 12 대조 2026-11-19)
            "사건 클로즈업: 역할 2의 사건을 알 수 있는 물건이나 자리(빈 접시·빈손·파헤친 자리·"
            "소리가 난 쪽·온 사람의 짐 등)를 크게, 인물은 어깨 위쪽과 몸에 맞는 크기의 손만(뭉치 "
            "없음)",
            speaker="그 컷에 보이는 인물이 사건을 알아채는 감탄(예: '아린: 어라? 떡이 없어졌어!')",
            mystery=True,
            look="The person just noticed something: eyes a little wide, mouth in a small 'oh'.",
            follows=1,
            place="INCIDENT",
            act="The person's hand stops and they lean in a little, surprised.",
        ),
        CutSpec(
            "PEOPLE",
            2,
            False,
            "HOLD_CLOSE",
            "CLOSE",
            "인물 리액션: 사건을 본 인물들이 펄쩍 놀라는 얼굴(어깨 위, 뭉치 없음)",
            mystery=True,
            look="Everyone shows a big surprised face: wide eyes, raised eyebrows and open "
            "mouths, not smiling.",
            follows=1,
            place="INCIDENT",
            act="The people jump back a little in surprise and keep looking at the same spot.",
        ),
        CutSpec(
            "RUN",
            3,
            True,
            "TRACK_SIDE",
            "",
            "뭉치 출동: 뭉치 혼자 정면을 본 채 짧은 갈색 발로 옆으로 힘차게 달리고 배경이 흘러감",
            speaker="뭉치의 역할 구호(예: '뭉치: 경찰관 뭉치, 출동!')",
            place="ROAD",
        ),
        CutSpec(
            "MUNGCHI",
            3,
            False,
            "PUSH_SLOW",
            "MUNGCHI_CLOSE",
            # 장소는 사건 장소 안(5차 콘티: 장면 글 "떡집 앞"이 장소 칸 "떡집 안"과 부딪혔음)
            "뭉치 결심: 사건 장소 안에 선 뭉치 혼자 가슴 위 클로즈업, 다문 입으로 결심한 얼굴",
            "Mungchi's face turns determined (a firm closed mouth) and it sways slightly.",
            place="INCIDENT",
        ),
        CutSpec(
            "GROUP",
            4,
            True,
            "PAN_SIDE",
            "WIDE",
            "모두 모여 큰 질문: 인물들과 뭉치가 사건 현장에 모임(뭉치는 사람들과 조금 떨어져 섬)",
            "Mungchi stays apart from the people, tilts its head and sways slightly.",
            speaker="뭉치가 이번 주 큰 질문을 묻는 말(예: '뭉치: 장난꾸러기는 누구일까?')",
            look="The people look puzzled and curious, looking at the spot, not smiling widely.",
            follows=1,
            place="INCIDENT",
            act="The people tilt their heads, puzzled, still looking at the spot.",
        ),
    ),
    "OUTRO": (
        CutSpec(
            "MUNGCHI",
            1,
            True,
            "PUSH_SLOW",
            "MUNGCHI_CLOSE",
            "뭉치 깨달음: 뒤쪽 판·벽에 붙은 단서 그림들 앞에서 뭉치 혼자 가슴 위 클로즈업(단서 "
            "물건을 뭉치 앞 바닥·탁자에 두지 않음), 갸웃하다 놀란 입, 활짝 웃음",
            "Mungchi tilts its head, then its mouth opens in a small surprised o, then it breaks "
            "into a big smile.",
            speaker="뭉치가 정답을 말함(예: '뭉치: 알았다! 장난꾸러기는 너구리야!')",
            place="INCIDENT",
        ),
        CutSpec(
            "RUN",
            2,
            False,
            "TRACK_SIDE",
            "",
            "뭉치 혼자 정답 장소로 짧은 갈색 발로 옆으로 달려감(대상은 아직 보이지 않음)",
            place="ROAD",
        ),
        CutSpec(
            "PEOPLE",
            3,
            True,
            "HOLD_CLOSE",
            "CLOSE",
            "정답 공개: 정답 장소에서 사람들과 대상(뭉치 없음)",
            speaker="그 컷에 보이는 인물이 공개에 놀람(예: '새봄: 짜잔! 보물이다!')",
            place="ANSWER",
            act="The people react as the story beat says with clear, natural movements (pointing "
            "or picking something up is fine).",
        ),
        CutSpec(
            "MUNGCHI",
            3,
            False,
            "PUSH_SLOW",
            "MUNGCHI_CLOSE",
            "뭉치 리액션: 정답 장소 앞 뭉치 혼자 가슴 위 클로즈업, 놀란 입에서 활짝 웃음",
            "Mungchi's mouth opens in a small surprised o, then it breaks into a big smile and "
            "sways happily.",
            place="ANSWER",
        ),
        CutSpec(
            "PEOPLE",
            4,
            False,
            "PAN_SIDE",
            "",
            # 내용은 종류 역할 4(동물 종류는 덮어 두기 + 배웅). 예전 "사람들과 대상이 함께 기뻐함
            # (손뼉)"은 종류마다 다른 마무리와 어긋났음
            "마무리: 역할 4 내용을 사람들만으로(뭉치 없음, 대상은 줄거리 종류 규칙에서 대상이 "
            "나오는 컷일 때만)",
            follows=3,
            place="ANSWER",
            act="The people act out the story beat calmly with small, natural movements.",
        ),
        CutSpec(
            "GROUP",
            4,
            True,
            "PAN_SIDE",
            "WIDE",
            # #779(사용자 결정 2026-11-19): 사건을 푼 뭉치에게 고마워하는 엔딩(모든 종류). 사람은
            # 뭉치를 만지지 않고 떨어져서(사람 팔이 뭉치에게 옮겨 붙지 않게)
            # 손뼉은 공중 손짓이라 뺌(사용자 결정 2026-11-19). 든 물건은 그대로 듦
            "엔딩 — 뭉치에게 고마워함: 넓은 장면에서 사람들이 뭉치 쪽으로 몸을 돌려 고마워하며 "
            "웃고(종료 5컷에서 든 물건은 그대로 듦), 뭉치는 사람들과 떨어져 쑥스럽게 웃으며 몸을 "
            "흔듦(아무도 뭉치를 만지지 않음)",
            "Mungchi stays apart from the people, smiles shyly and sways happily.",
            speaker="그 컷에 보이는 인물이 뭉치에게 고마워하는 말(예: '아린: 고마워, 뭉치!')",
            own=True,
            look="The people smile warmly and thankfully at Mungchi.",
            follows=5,
            place="ANSWER",
            act="The people turn toward Mungchi and smile warmly from a little distance.",
        ),
    ),
}

LAYOUTS: dict[int, dict[str, tuple[CutSpec, ...]]] = {4: _LEGACY, NEW_CUTS: _NEW}


def layout(n: int) -> dict[str, tuple[CutSpec, ...]]:
    """컷 수의 틀. 모르는 컷 수는 새 틀(검사 CUTS가 새 테마의 컷 수를 막음)."""
    return LAYOUTS.get(n, _NEW)


def spec(scene: str, index: int, n: int) -> CutSpec:
    return layout(n)[scene][index - 1]


def role_cut(scene: str, index: int, n: int) -> tuple[str, int]:
    """n컷 틀의 컷 → 줄거리 종류 콘티 틀(4컷 번호)의 같은 역할 컷."""
    return scene, spec(scene, index, n).role


def all_cuts(n: int) -> frozenset[tuple[str, int]]:
    return frozenset((s, i) for s in ("INTRO", "OUTRO") for i in range(1, len(layout(n)[s]) + 1))


def mapped(cuts: frozenset[tuple[str, int]], n: int) -> frozenset[tuple[str, int]]:
    """4컷 번호 묶음(대상·정답이 나와도 되는 컷) → n컷 번호. 4컷이면 그대로. 뭉치 혼자 나오는 컷은
    대상·정답을 그리지 않아 뺀다(6컷)."""
    if n == 4:
        return cuts
    return frozenset(
        (s, i)
        for s, i in all_cuts(n)
        if role_cut(s, i, n) in cuts and not spec(s, i, n).mungchi_alone
    )


def seconds(n: int, configured: list[int] | tuple[int, ...]) -> list[float]:
    """n컷 컷 길이: 설정 길이가 컷 수와 같으면 설정, 4컷이면 예전 4·6·8·6초, 그 밖은 4초씩."""
    if len(configured) == n:
        return [float(x) for x in configured]
    if n == 4:
        return [float(x) for x in LEGACY_SECONDS]
    return [4.0] * n
