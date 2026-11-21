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
# 표정 그림 두 장 컷의 끝 그림 이름 꼬리(INTRO5END 등, #779 A안). 그림·재료·영상이 같은 이름을 씀
END_FACE = "END"
# 달리기 합성 컷의 자세 그림 이름 꼬리(#779 사용자 결정 2026-11-20 ②안): 초록 배경 기본 자세(POSE)와
# 그것을 고친 왼발·오른발 자세(RUNA·RUNB). 컷 그림(INTRO4)은 뭉치 없는 길 배경
RUN_BASE, RUN_STEPS = "POSE", ("RUNA", "RUNB")
EXTRA_TAILS = (END_FACE, RUN_BASE, *RUN_STEPS)


def end_key(key: str) -> str:
    """컷 그림 이름 → 그 컷 끝 표정 그림 이름(INTRO5 → INTRO5END)."""
    return f"{key}{END_FACE}"


def run_keys(key: str) -> tuple[str, str, str]:
    """달리기 합성 컷 그림 이름 → (기본 자세, 왼발 자세, 오른발 자세) 그림 이름."""
    return f"{key}{RUN_BASE}", f"{key}{RUN_STEPS[0]}", f"{key}{RUN_STEPS[1]}"


def extra_keys(key: str) -> tuple[str, ...]:
    """컷 그림 이름 → 그 컷에 딸린 그림 이름이 될 수 있는 것 모두(끝 표정·달리기 자세)."""
    return tuple(f"{key}{t}" for t in EXTRA_TAILS)


def cut_key_of(key: str) -> str:
    """딸린 그림 이름 → 그 컷 그림 이름(INTRO5END·INTRO4RUNA → INTRO5·INTRO4). 그 밖은 그대로."""
    for tail in EXTRA_TAILS:
        if key.startswith(("INTRO", "OUTRO")) and key.endswith(tail) and key != tail:
            return key.removesuffix(tail)
    return key


def is_extra(key: str) -> bool:
    """컷에 딸린 그림(끝 표정·달리기 자세)인지. 실패해도 장면 영상을 빼지 않고 그 컷만 대신함."""
    return cut_key_of(key) != key


def scene_of(key: str) -> str:
    """그림 이름 → 장면(INTRO5·INTRO5END → INTRO, 요일은 그대로)."""
    return key[:5] if key.startswith(("INTRO", "OUTRO")) else key


@dataclass(frozen=True)
class CutSpec:
    who: Who  # 누가 나오는지: 사람만·사건 물건 클로즈업(사람 손)·뭉치 혼자·뭉치 혼자 달림·함께
    role: int  # 줄거리 종류 콘티 틀의 역할 번호(1~4)
    caption: bool  # 자막을 띄우는 컷인지
    beat: str = ""  # 컷 할 일(줄거리 콘티 규칙·영상 지시 "Story beat")
    motion: str = ""  # 뭉치 컷 영상 지시(표정 변화 등, 영어)
    speaker: str = ""  # 자막 말하는 사람과 할 말(줄거리 콘티 규칙)
    narrator: bool = False  # 자막이 이름 없는 장면 소개(시작 1컷)
    # 첫 그림 표정(영어). 그림 지시에는 장면(scene)만 들어가 리액션 컷이 웃는 얼굴로 그려졌음
    # (경찰관 떡집 콘티 2026-11-19)
    look: str = ""
    # 이 컷이 잇는 앞 컷 번호(0이면 없음). 컷 그림을 따로 그려 같은 뒤뜰인데 탁자·담이 바뀌고 앞
    # 컷에서 덮은 떡이 다음 컷에서 벗겨졌음(경찰관 떡집 콘티 2026-11-19, 사용자 결정 B안): 그 앞
    # 컷 그림을 참고 그림으로 받아 장소·가구·물건 상태를 잇는다
    follows: int = 0  # 같은 장소(place)의 앞 사람 컷만
    place: Place = ""
    # 내용이 이 할 일 그대로인 컷(줄거리 종류 역할 내용을 붙이지 않음). 종료 6컷(뭉치에게 고마워함)
    # 은 모든 종류가 같은 엔딩(#779 사용자 결정 2026-11-19)
    own: bool = False
    # 사람이 나오는 컷의 4초 움직임(영어, 영상 지시). 예전에는 모든 사람 컷에 공통 "걷기·펄쩍·손
    # 흔들기 같은 큰 동작"이 붙어 컷마다 정한 동작(배웅은 바라보기 등)과 부딪혔음(#779 설계 C표,
    # 2종류 × 12컷 대조 2026-11-19). 공중 손짓(흔들기·손뼉)은 쓰지 않음(사용자 결정 2026-11-19)
    act: str = ""
    # 구도 틀 이름(frames.FRAMES, #779 설계 H). 장면 크기·구도·얼굴 규칙·카메라·수수께끼 조명·검토
    # 핵심은 틀이 정함. 종료 5컷은 줄거리 종류가 바꿀 수 있음(StoryType.outro5_frame). 예전 4컷은 ""
    frame: str = ""
    # 뭉치 컷 첫 그림의 입 모양(prompts.MOOD_MOUTH 키). 콘티 mungchiMood는 '컷 끝 표정'인데 첫
    # 그림에 그려, 종료 1컷("알았다!")·4컷이 처음부터 웃고 있어 놀람 → 웃음 변화가 없었음(대표
    # 5종 2차 5/5 테마, 경고 3건 "이미 활짝 웃는 입"). 6컷은 첫 표정을 컷 표가 정하고 변화는
    # motion이 말함
    # (재검토 2026-11-20). 종료 1·4컷 말고는 그동안 그려진 표정 그대로
    mouth: str = ""
    # 끝 입 모양(prompts.MOOD_MOUTH 키). 있으면 그 컷은 Veo를 쓰지 않고 표정 그림 두 장(첫 그림 +
    # 입만 바꾼 끝 그림, 그림 단계가 그림·검토)을 녹아드는 전환과 천천히 확대로 잇는다(#779 사용자
    # 결정 2026-11-20 A안). 뭉치 혼자 클로즈업은 Veo가 구도와 상관없이 팔을 만들어(장난꾸러기 "정리"
    # 영상 확인: 가슴 위 클로즈업 0/3, 가운데·전신·카메라 고정 0/3 — 9번 시도 모두 "몸 밖으로 뻗은
    # 팔"), 같은 3컷을 그림 두 장으로 만든 비교는 3/3 첫 시도 통과
    end_mouth: str = ""

    @property
    def two_faces(self) -> bool:
        """Veo 대신 표정 그림 두 장으로 만드는 컷(end_mouth)."""
        return bool(self.end_mouth)

    @property
    def run_comp(self) -> bool:
        """Veo 대신 코드가 합성하는 달리기 컷(6컷 RUN 틀, #779 사용자 결정 2026-11-20 ②안).

        뭉치 혼자 달리기는 Veo가 팔을 만들거나 몸을 틀어(장난꾸러기 "정리" 영상 확인: 시작 4컷
        3번 모두 실패, 종료 2컷 1번 통과) 길 배경 + 초록 배경 자세 그림 두 장을 번갈아 겹친다
        (media.run_clip). 예전 4컷 출동 컷은 예전처럼 Veo."""
        return self.who == "RUN" and bool(self.frame)

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
            "장소 소개: 장소가 한눈에 보이는 넓은 장면에서 인물들의 평소 모습(뭉치 없음)",
            # 자막 예시에 장소·이름·정답을 박지 않음(#779 대표 5종 콘티: 예시의 이름을 그대로 쓰고,
            # 떡집 테마 정답이 매번 예시의 동물이었음)
            speaker="이름 없이 이 테마 장소의 평소 모습을 소개하는 짧은 말(말줄임표로 끝냄)",
            narrator=True,
            look="Everyone looks relaxed and calm, busy with their usual tasks.",
            place="INCIDENT",
            act="The people keep doing their usual tasks with small, natural movements.",
            frame="WIDE_INTRO",
        ),
        CutSpec(
            "OBJECT",
            2,
            True,
            # 소리 탐정(소리를 듣고 귀 기울임)·탈것(온 사람과 인사함)처럼 물건이 없는 종류도 있어
            # '역할 2의 사건을 알 수 있는 것'으로 씀(#779 종류 11 × 컷 12 대조 2026-11-19)
            "사건 클로즈업: 역할 2의 사건을 알 수 있는 물건이나 자리(빈 접시·빈손·파헤친 자리·"
            "소리가 난 쪽·온 사람의 짐 등)를 크게, 인물은 어깨 위쪽과 몸에 맞는 크기의 손만(뭉치 "
            "없음)",
            speaker="그 컷에 보이는 인물(characters의 이름)이 사건을 알아채는 감탄('어라?'·'앗!' "
            "같은 말로 시작)",
            look="The person just noticed something: eyes a little wide, mouth in a small 'oh'.",
            follows=1,
            place="INCIDENT",
            act="The person's hand stops and they lean in a little, surprised.",
            frame="OBJECT_CLOSE",
        ),
        CutSpec(
            "PEOPLE",
            2,
            False,
            "인물 리액션: 사건을 본 인물들이 펄쩍 놀라는 얼굴(어깨 위, 뭉치 없음)",
            look="Everyone shows a big surprised face: wide eyes, raised eyebrows and open "
            "mouths, not smiling.",
            follows=1,
            place="INCIDENT",
            act="The people jump back a little in surprise and keep looking at the same spot.",
            frame="REACTION",
        ),
        CutSpec(
            "RUN",
            3,
            True,
            # 합성 컷(run_comp): 달리는 방향은 코드가 정함(배경이 뒤로 물러남, media.run_clip)이라
            # 글에는 방향을 쓰지 않음. "옆으로"는 합성과 어긋나고 "화면 쪽으로"는 글 규칙 "누구도
            # 화면 쪽으로 다가오지 않는다"와 부딪힘(2026-11-21)
            "뭉치 출동: 뭉치 혼자 정면을 본 채 짧은 갈색 발로 힘차게 달림",
            speaker="뭉치의 역할 구호(예: '뭉치: 경찰관 뭉치, 출동!')",
            place="ROAD",
            frame="RUN",
            mouth="determined",
        ),
        CutSpec(
            "MUNGCHI",
            3,
            False,
            # 장소는 사건 장소 안(5차 콘티: 장면 글 "떡집 앞"이 장소 칸 "떡집 안"과 부딪혔음).
            # 표정 그림 두 장(end_mouth): 놀란 입 → 다문 입(결심)
            "뭉치 결심: 사건 장소 안에 선 뭉치 혼자 가슴 위 클로즈업, 놀란 입에서 다문 입으로 "
            "결심한 얼굴",
            "Mungchi's small surprised o mouth turns into a firm closed mouth (determined).",
            place="INCIDENT",
            frame="MUNGCHI_CLOSE",
            mouth="surprised",
            end_mouth="determined",
        ),
        CutSpec(
            "GROUP",
            4,
            True,
            # 뭉치는 늘 정면을 보게 그려짐(대표 5종 콘티 경고 "뭉치는 상자보다 정면") — 뭉치에게
            # 다른 곳을 보라고 하지 않음
            "모두 모여 큰 질문: 인물들은 사건 자리를 보고, 뭉치는 사람들과 조금 떨어져 정면에서 "
            "갸웃함",
            "Mungchi stays apart from the people, tilts its head and sways slightly.",
            speaker="뭉치가 이번 주 큰 질문을 묻는 말(예: '뭉치: 장난꾸러기는 누구일까?')",
            look="The people look puzzled and curious, looking at the spot, not smiling widely.",
            follows=1,
            place="INCIDENT",
            act="The people tilt their heads, puzzled, still looking at the spot.",
            frame="GROUP_QUESTION",
            mouth="surprised",
        ),
    ),
    "OUTRO": (
        CutSpec(
            "MUNGCHI",
            1,
            True,
            # 표정 그림 두 장(end_mouth): 생각하는 다문 입 → '알았다!' 웃는 입
            "뭉치 깨달음: 뒤쪽 판·벽에 단서 그림들이 붙어 있고 그 앞에서 뭉치 혼자 정면을 보는 "
            "가슴 위 클로즈업(단서 물건을 뭉치 앞 바닥·탁자에 두지 않음), 생각하는 다문 입에서 "
            "알아챈 웃는 입으로",
            "Mungchi's closed thinking mouth turns into a smiling mouth as it realizes the answer.",
            speaker="뭉치가 '알았다!' 뒤에 이번 정답을 말함",
            place="INCIDENT",
            frame="MUNGCHI_CLOSE",
            mouth="determined",
            end_mouth="smile",
        ),
        CutSpec(
            "RUN",
            2,
            False,
            "뭉치 혼자 정답 장소로 가는 길을 정면을 본 채 짧은 갈색 발로 달려감(대상은 아직 보이지 "
            "않음)",
            place="ROAD",
            frame="RUN",
            mouth="determined",
        ),
        CutSpec(
            "PEOPLE",
            3,
            True,
            "정답 공개: 정답 장소에서 사람들과 대상(뭉치 없음)",
            speaker="그 컷에 보이는 인물(characters의 이름)이 공개에 놀라는 말('짜잔!'·'와!' 같은 "
            "말로 시작)",
            place="ANSWER",
            act="The people react as the story beat says with clear, natural movements (pointing "
            "or picking something up is fine).",
            frame="REVEAL",
        ),
        CutSpec(
            "MUNGCHI",
            3,
            False,
            # 표정 그림 두 장(end_mouth): 놀란 입 → 웃는 입
            "뭉치 리액션: 정답 장소 앞 뭉치 혼자 가슴 위 클로즈업, 놀란 입에서 활짝 웃음",
            "Mungchi's small surprised o mouth turns into a big smile.",
            place="ANSWER",
            frame="MUNGCHI_CLOSE",
            mouth="surprised",
            end_mouth="smile",
        ),
        CutSpec(
            "PEOPLE",
            4,
            False,
            # 내용은 종류 역할 4(동물 종류는 덮어 두기 + 배웅). 예전 "사람들과 대상이 함께 기뻐함
            # (손뼉)"은 종류마다 다른 마무리와 어긋났음
            "마무리: 역할 4 내용을 사람들만으로(뭉치 없음, 대상은 줄거리 종류 규칙에서 대상이 "
            "나오는 컷일 때만)",
            follows=3,
            place="ANSWER",
            # "calmly with small"은 종류 역할 "폴짝 뛰거나 웃음"과 부딪혔음(재검토 2026-11-20)
            act="The people act out the story beat with gentle, natural movements.",
            frame="JOY",
        ),
        CutSpec(
            "GROUP",
            4,
            True,
            # #779(사용자 결정 2026-11-19): 사건을 푼 뭉치에게 고마워하는 엔딩(모든 종류). 사람은
            # 뭉치를 만지지 않고 떨어져서(사람 팔이 뭉치에게 옮겨 붙지 않게)
            # 손뼉은 공중 손짓이라 뺌(사용자 결정 2026-11-19). 든 물건은 그대로 듦
            "엔딩 — 뭉치에게 고마워함: 넓은 장면에서 사람들이 뭉치 쪽으로 몸을 돌려 고마워하며 "
            "웃고(종료 5컷에서 든 물건은 그대로 듦), 뭉치는 사람들과 떨어져 쑥스럽게 웃으며 몸을 "
            "흔듦(아무도 뭉치를 만지지 않음)",
            "Mungchi stays apart from the people, smiles shyly and sways happily.",
            speaker="그 컷에 보이는 인물(characters의 이름)이 뭉치에게 '고마워, 뭉치!'처럼 "
            "고마워하는 말",
            own=True,
            look="The people smile warmly and thankfully at Mungchi.",
            # 종료 5컷이 아니라 3컷을 이음: 3 → 5 → 6으로 줄 서면 다시 그리기가 쌓여 그림 단계가
            # 300~460초가 됐음(대표 5종 2차 2026-11-19). 3 → (5, 6) 두 단으로. 5 → 6 물건 상태는
            # 할 일 글("종료 5컷에서 든 물건은 그대로 듦")로 이음
            follows=3,
            place="ANSWER",
            act="The people turn toward Mungchi and smile warmly from a little distance.",
            frame="FACING_MUNGCHI",
            mouth="smile",
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
