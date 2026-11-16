"""줄거리 종류·가족 등록표 (#634, 설계 ai.md 17.8·17.8.13).

종류마다 if문을 흩뿌리지 않고 이 표 하나에서 줄거리 규칙 묶음·콘티 틀·대상이 나와도 되는 컷·
흔적 특징·사실표를 꺼내 쓴다. 종류 이름(label)과 넷째 칸 이름(target_label)은 learning
`ThemeTopicSeeds.StoryType`과 같은 표다(learning이 주제 씨앗 `topic` 첫 칸에 넣음).

가족: ① 숨은 것(HIDDEN, 후보는 장소) — LOST·TREASURE, ③ 동물 주인공(ANIMAL) — PRANK·FOOTPRINT,
② 손에 든 것의 출처·정체(IN_HAND) — ORIGIN·GIFT·SECRET_INGREDIENT. ④⑤는 ② 실측을 통과한 뒤 켠다.
성질별 칸: 사실표(facts, 있으면 후보 이름을 엔딩 전에 감춤), 대상이 처음부터 손에 있음
(target_in_hand), 정답 후보가 그림에 나와도 되는 컷(answer_cuts), 종류별 흔적 특징(trace).
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

StoryTypeCode = Literal[
    "LOST", "TREASURE", "PRANK", "FOOTPRINT", "ORIGIN", "GIFT", "SECRET_INGREDIENT"
]
FamilyCode = Literal["HIDDEN", "ANIMAL", "IN_HAND"]

# 종료 콘티 1컷(단서 정리)은 모든 종류가 같다
OUTRO_THINK = "뭉치가 바닥·탁자에 놓인 단서들 앞에서 생각을 정리함"
INTRO_GO = "뭉치 출동(테마 차림의 뭉치가 혼자 화면 안에서 옆으로 통통 튀어 감)"
INTRO_ARRIVE = "현장 도착(뭉치와 인물들이 모여 큰 질문을 마주함)"
ALL_CUTS = frozenset((s, i) for s in ("INTRO", "OUTRO") for i in range(1, 5))


KIND_ORDER = ("TRACE", "SIGHTING", "RECORD")
KIND_KO = {"TRACE": "흔적", "SIGHTING": "목격", "RECORD": "기록"}
ALL_KINDS = frozenset(KIND_ORDER)


@dataclass(frozen=True)
class FactTable:
    """후보 특징 사실표(동물·선물·재료).

    모델이 지은 특징이 틀려 글 검토가 줄거리를 되풀이하던 것을 막으려고 코드가 값을 정한다
    (#634 1차 작은 실측, checks.apply_facts). 기준안 — 초등학생이 상식으로 받아들이는 값만, 같은
    특징의 값끼리는 한쪽이 다른 쪽에 들어가지 않게('털'은 '깃털'에 들어 있어 '부드러운 털').
    """

    name: str  # 동물·선물·재료
    features: tuple[str, ...]
    rows: dict[str, tuple[str, ...]]
    # 특징마다 알 수 있는 증거 종류(TRACE·SIGHTING·RECORD). 줄거리 직후 코드가 요일 증거 배정을 이에
    # 맞춘다(checks.fit_evidence_plan). ② 작은 실측 2차: 소리를 목격으로, 맛을 목격으로 써서 글 검토
    # CLUE_LOGIC("소리 단서의 증거 종류가 목격", "맛은 눈으로 확인할 수 없음")
    kinds: dict[str, frozenset[str]] | None = None

    def kinds_of(self, feature: str) -> frozenset[str] | None:
        return (self.kinds or {}).get(feature)

    def fact(self, candidate: str, feature: str) -> str | None:
        row = self.rows.get(candidate.strip())
        if row is None or feature not in self.features:
            return None
        return row[self.features.index(feature)]

    def text(self) -> str:
        head = " | ".join([self.name, *self.features])
        return "\n".join([f"  {head}", *(f"  {' | '.join([k, *v])}" for k, v in self.rows.items())])

    def rule(self) -> str:
        """줄거리 규칙: 후보·특징은 표 안에서, 값은 표 값 그대로(코드가 맞춤)."""
        kinds = " / ".join(
            f"{f}: {'·'.join(KIND_KO[k] for k in KIND_ORDER if k in ks)}"
            for f, ks in (self.kinds or {}).items()
        )
        return (
            f"- candidates는 아래 {self.name} 사실표에서 그 장소·이야기에 어울리는 4개를 표 이름 "
            "그대로 "
            f"쓴다(표 밖 {self.name}·색 낱말·'옆집' 같은 주인 표시 없이, 코드 검사 FACT_TABLE). "
            f"features는 표의 특징 이름 가운데 2~{len(self.features)}개를 그대로 쓰고 후보마다 "
            "값은 표 "
            "값 그대로 쓴다(코드가 표 값으로 맞춤. 표에 없는 특징·값을 지어내지 않는다).\n"
            f"- {self.name} 사실표:\n{self.text()}\n"
            + (
                "- 특징마다 알 수 있는 증거(그날 증거 종류에 맞는 특징을 고르고, 안 맞으면 코드가 "
                f"배정을 바꿈): {kinds}\n"
                if kinds
                else ""
            )
            + ""
            "- 엔딩 전 글(title·world·intro·시작 "
            "콘티·place·sceneNote·discovery·missionHook·incident·"
            f"인물 모습)에는 후보 {self.name} 이름과 정답 {self.name}만의 표 값을 쓰지 않는다(코드 "
            "검사 "
            "CANDIDATE_NAME·ANSWER_FACT). target에도 쓰지 않는다(TARGET_NAMES).\n"
        )


@dataclass(frozen=True)
class StoryType:
    code: StoryTypeCode
    label: str  # learning 씨앗 첫 칸(`줄거리: <label>`)
    target_label: str  # learning 씨앗 넷째 칸 이름(찾는 대상 / 밝힐 것 / 손에 든 것)
    family: FamilyCode
    candidate_kind: str  # 후보 범주(장소·동물·물건·재료)
    intro_cuts: tuple[str, str, str, str]
    outro_cuts: tuple[str, str, str, str]
    target_cuts: frozenset[tuple[str, int]]  # 대상(target)이 그림·영상에 나와도 되는 컷
    outro_rule: str  # 종료 이야기 마무리 장면(outroStory)
    rules: str  # 줄거리 프롬프트에 붙이는 종류 규칙(plan_user)
    facts: FactTable | None = None
    target_in_hand: bool = False  # ②: 대상이 처음부터 손에 있음(못 찾았다는 전제 13곳을 뒤집음)
    answer_cuts: frozenset[tuple[str, int]] = frozenset()  # 사실표 종류: 정답 후보가 나와도 되는 컷
    trace: re.Pattern[str] | None = None  # 종류별 흔적 특징(있으면 checks.traceable이 더해 봄)
    trace_only: bool = (
        False  # True면 일반 흔적 표 대신 이 표만(동물: '꼬리 모양'의 '모양'을 빼려고)
    )

    @property
    def animal(self) -> bool:
        return self.family == "ANIMAL"

    @property
    def hide_candidates(self) -> bool:
        """후보 이름을 엔딩 전 글·미션·대화·그림에 감추는 종류(사실표가 있는 종류)."""
        return self.facts is not None


HIDDEN_COMMON = (
    "- 큰 질문은 대상이 있었던 곳(장소)을 묻는다. candidates는 그 장소 안이나 둘레의 서로 다른 "
    "장소 이름이다(때·길·탈것·사람은 후보로 두지 않음).\n"
    "- 시작 이야기·콘티에서 대상이 후보가 아닌 곳에 있었다거나 그곳에서 사라졌다고 쓰지 않는다. "
    "그날 장소(place)를 정답 장소로 두지 않는다(흔적·목격 날에도 장면은 정답 장소가 아닌 곳에서 "
    "벌어짐).\n"
)

LOST = StoryType(
    code="LOST",
    label="잃어버린 것 찾기",
    target_label="찾는 대상",
    family="HIDDEN",
    candidate_kind="장소",
    intro_cuts=(
        "사건 장소의 평소 모습과 주인 인물(대상을 지니거나 쓰는 모습은 되지만 어디에 두는지는 "
        "보여 주지 않음, 뭉치 안 나옴)",
        "사건(주인이 대상이 사라진 걸 알아채고 당황함, 뭉치 안 나옴)",
        INTRO_GO,
        INTRO_ARRIVE,
    ),
    outro_cuts=(
        OUTRO_THINK,
        "정답 장소 앞에 도착해 바라봄",
        "정답 장소에서 찾은 대상을 주인이 받아 듦(뭉치는 곁에서 지켜봄)",
        "함께 기뻐함",
    ),
    target_cuts=frozenset({("INTRO", 1), ("OUTRO", 3), ("OUTRO", 4)}),
    outro_rule="뭉치가 정답 장소에서 찾는 대상을 찾아 주인에게 돌려주는 장면만 쓴다.",
    rules=(
        "- 사건: 주인 아이가 아끼는 물건·동물(target)을 잃어버렸다. 찾는 대상의 주인은 학생 또래 "
        "아이로 등장인물 중 한 명이다.\n"
        "- 큰 질문 예: 마지막으로 머문 곳·쉬어 간 곳·두고 온 곳·떨어뜨린 곳(테마에 맞게 고르고 "
        "'마지막으로 둔 곳'만 되풀이하지 않는다).\n"
        + HIDDEN_COMMON
        + "- intro: 주인 인물이 대상을 잃은 사건부터 테마 역할의 뭉치가 현장으로 출동해 큰 질문을 "
        "맡는 데까지.\n"
    ),
)

TREASURE = StoryType(
    code="TREASURE",
    label="보물 쪽지 따라가기",
    target_label="찾는 대상",
    family="HIDDEN",
    candidate_kind="장소",
    intro_cuts=(
        "사건 장소의 평소 모습과 쪽지를 받을 아이(보물은 보이지 않음, 뭉치 안 나옴)",
        "아이가 숨긴 사람이 남긴 쪽지를 받아 들고 놀람(쪽지에 글자는 보이지 않음, 뭉치 안 나옴)",
        INTRO_GO,
        INTRO_ARRIVE,
    ),
    outro_cuts=(
        OUTRO_THINK,
        "정답 장소 앞에 도착해 바라봄",
        "정답 장소에서 찾은 보물을 아이가 열어 봄(뭉치는 곁에서 지켜봄)",
        "보물 속 편지를 함께 읽으며 기뻐함(편지 글자는 보이지 않음)",
    ),
    target_cuts=frozenset({("OUTRO", 3), ("OUTRO", 4)}),
    outro_rule=(
        "뭉치와 아이가 정답 장소에서 숨긴 보물을 찾아 열고, 안에 든 편지를 함께 읽으며 기뻐하는 "
        "장면만 쓴다."
    ),
    rules=(
        "- 사건: 어른(target 글에 나온 숨긴 사람)이 아이를 위해 target을 숨기고 '보물을 숨겼으니 "
        "찾아보렴' 하는 쪽지를 남겼다. 쪽지를 받은 아이(학생 또래)가 등장인물 중 한 명이다. 숨긴 "
        "사람은 쪽지·편지로만 나오고 characters·장면·콘티에 나오지 않는다(나오면 답을 아는 사람이 "
        "됨). 쪽지에는 숨긴 곳을 알려 주는 글이 없고, 숨긴 곳은 다섯 증거로 밝힌다.\n"
        "- 큰 질문은 숨긴 곳을 묻는다(예: '할아버지가 타임캡슐을 숨긴 곳은 어디였을까?').\n"
        + HIDDEN_COMMON
        + "- 증거는 숨긴 사람이 보물을 숨기러 가며 남긴 것이다: 보물을 들고 지나간 길·잠시 "
        "내려놓은 자리의 흔적, 그때 보물을 든 숨긴 사람을 본 목격, 그때 찍힌 사진·적힌 기록. 숨긴 "
        "곳은 끝까지 모르는 답이라 증거가 나온 곳은 숨긴 곳이 아니고, 엔딩 전 글(장면 메모·증거 "
        "발견 줄·단서·수사 연결 문장)에 '숨긴 자리·숨긴 곳'을 쓰지 않는다(코드 검사 "
        "HIDE_SPOT). 흔적·기록 단서에는 보물 이름(target 낱말)을 넣어 그 보물의 증거임을 밝힌다. "
        "evidence.when은 숨긴 때다.\n"
        "- intro: 아이가 쪽지를 받는 데서 시작해 테마 역할의 뭉치가 현장으로 출동해 큰 질문을 "
        "맡는 데까지.\n"
    ),
)

# 동물 사실표(#634 1차 작은 실측: 너구리 고리무늬 꼬리·고양이 앞발가락 4개·까치 발가락 3개처럼
# 모델이 지은 특징이 틀려 글 검토 CLUE_LOGIC 7번 중 6번). 고양이는 걸을 때 발톱을 숨겨 발바닥
# 자국만.
# 꼬리 값은 짧게(1차 판정 1회: 값 셋이면 한 줄 단서 47자를 넘어 쪽지 꼴로 줄임)
ANIMALS = FactTable(
    name="동물",
    features=("몸을 덮은 것", "발자국 발 수", "발자국의 발톱", "꼬리 모양"),
    rows={
        "고양이": ("부드러운 털", "네 발", "발바닥 자국", "가는 꼬리"),
        "너구리": ("부드러운 털", "네 발", "발톱 자국", "굵은 꼬리"),
        "다람쥐": ("부드러운 털", "네 발", "발톱 자국", "복슬 꼬리"),
        "고슴도치": ("뾰족한 가시", "네 발", "발톱 자국", "짧은 꼬리"),
        "생쥐": ("부드러운 털", "네 발", "발톱 자국", "맨 꼬리"),
        "까치": ("깃털", "두 발", "발톱 자국", "긴 꽁지"),
        "비둘기": ("깃털", "두 발", "발톱 자국", "넓은 꽁지"),
        "참새": ("깃털", "두 발", "발톱 자국", "짧은 꽁지"),
        "오리": ("깃털", "두 발", "물갈퀴 자국", "뭉툭한 꽁지"),
    },
    kinds={
        "몸을 덮은 것": ALL_KINDS,
        "발자국 발 수": ALL_KINDS,
        "발자국의 발톱": frozenset({"TRACE", "RECORD"}),
        "꼬리 모양": frozenset({"SIGHTING", "RECORD"}),
    },
)
# 지난 이름(시험·문서 호환)
ANIMAL_FEATURES = ANIMALS.features
ANIMAL_FACTS = ANIMALS.rows

# 선물 사실표(#634 ②, 기준안): 상자를 열기 전에 알 수 있는 것만. '상자 모양'은 첫 그림부터 상자가
# 보여 단서가 공짜로 풀리므로 쓰지 않는다(설계 17.8.13 보강). '눌러 본 느낌'도 뺐다: 닫힌 상자를
# 눌러 안의 촉감을 알 수 없다고 글 검토 CLUE_LOGIC(② 작은 실측 선물 2건 모두) — 특징은 증거로
# 실제 알 수 있는 것만: 무게·소리(상자를 직접 들고 흔든 흔적·기록), 산 가게(목격·기록)
GIFTS = FactTable(
    name="선물",
    features=("상자 무게", "흔들면 나는 소리", "산 가게"),
    rows={
        "목도리": ("가벼운 상자", "소리 없음", "옷 가게"),
        "고무공": ("가벼운 상자", "통통 소리", "장난감 가게"),
        "색연필": ("가벼운 상자", "달각 소리", "문구점"),
        "그림책": ("묵직한 상자", "스르륵 소리", "서점"),
        "머그컵": ("묵직한 상자", "달그락 소리", "그릇 가게"),
        "화분": ("묵직한 상자", "흙 소리", "꽃집"),
    },
    # 상자 무게·소리는 상자를 직접 들고 흔든 흔적이나 택배 무게 메모·녹음 기록, 산 가게는 계산대에서
    # 사는 걸 본 목격이나 영수증·가게 스티커 기록(가게에서 나오는 걸 본 것만으로는 근거가 안 됨)
    kinds={
        "상자 무게": frozenset({"TRACE", "RECORD"}),
        "흔들면 나는 소리": frozenset({"TRACE", "RECORD"}),
        "산 가게": frozenset({"SIGHTING", "RECORD"}),
    },
)

# 재료 사실표(#634 ②, 기준안): 음식에 물드는 색은 그림에 보이면 답이 되므로 엔딩 전 그림에 음식을
# 그리지 않고(target_cuts), 엔딩 전 글의 정답 재료 값은 ANSWER_FACT로 막음. '자라는 곳'은 재료를
# 넣는 걸 봐도 알 수 없다고 글 검토 CLUE_LOGIC(② 작은 실측) — 산 가게(목격·장보기 기록)로 바꿈
INGREDIENTS = FactTable(
    name="재료",
    features=("물드는 색", "맛", "산 가게"),
    rows={
        "딸기": ("분홍빛", "새콤한 맛", "과일 가게"),
        "당근": ("주황빛", "달큰한 맛", "채소 가게"),
        "단호박": ("노란빛", "달큰한 맛", "채소 가게"),
        "쑥가루": ("초록빛", "쌉쌀한 맛", "방앗간"),
        "시금치": ("초록빛", "순한 맛", "채소 가게"),
        "자색고구마": ("보랏빛", "달큰한 맛", "채소 가게"),
        "블루베리": ("보랏빛", "새콤한 맛", "과일 가게"),
        "콩가루": ("누런빛", "고소한 맛", "방앗간"),
        "흑임자": ("잿빛", "고소한 맛", "방앗간"),
    },
    kinds={
        "물드는 색": ALL_KINDS,
        "맛": frozenset({"TRACE", "RECORD"}),
        "산 가게": frozenset({"SIGHTING", "RECORD"}),
    },
)


def animal_fact(animal: str, feature: str) -> str | None:
    """동물 사실표 값(지난 이름). 표 밖이면 None."""
    return ANIMALS.fact(animal, feature)


def animal_table_text() -> str:
    return ANIMALS.text()


ANIMAL_COMMON = (
    "- target은 주제의 '밝힐 것' 글을 그대로 쓴다(정답 동물 이름을 쓰지 않음, 코드 검사 "
    "TARGET_NAMES). 사건을 알아챈 아이(학생 또래)가 등장인물 중 한 명이다. 후보 동물의 주인은 "
    "등장하지 않는다.\n"
    "- incident: 사건 물건·일 한 줄(예: '떡 접시가 비어 있고 떡 부스러기가 흩어짐'). 엔딩 전에 "
    "보여도 되는 사실이고 그 주 문제의 소재가 된다. 동물 이름을 쓰지 않는다. 반드시 채운다(비우면 "
    "코드 검사 REQUIRED).\n"
    "- answerLook: 정답 동물의 겉모습 한 줄(예: '귀 끝이 까맣고 꼬리가 굵은 갈색 너구리'). 종료 "
    "그림·영상에서 이 모습 그대로 그린다. 표의 정답 동물 값과 맞게 쓰고 반드시 채운다.\n"
    "- 큰 질문은 그 일을 한 동물을 묻는다(예: '떡을 몰래 먹은 건 누구였을까?').\n"
    + ANIMALS.rule()
    + "- 엔딩 전 장면에 후보 동물을 등장시키지 않는다.\n"
    "- 단서는 관찰이다. TRACE는 그 동물이 남긴 흔적(발자국의 발 수·발톱 자국, 떨어진 털·깃털·"
    "가시), SIGHTING은 부분 목격(어두워 꼬리만 봄·뒷모습만 봄), RECORD는 부분 기록(사진에 발끝만·"
    "영상에 꼬리 그림자만)이다. TRACE 날 특징은 몸을 덮은 것·발자국 발 수·발자국의 발톱 가운데서, "
    "꼬리 모양은 목격·기록 날에 쓴다. 목격·기록이 동물 전체 모습이나 이름을 알려 주지 "
    "않는다. '고양이는 밤에 다닌다' 같은 동물 상식 문장은 단서가 아니다. TRACE 날 단서에는 '동물' "
    "낱말을 넣어 그 동물의 흔적임을 밝힌다.\n"
    "- 동물의 습성·장난이지 범죄가 아니다. 누구를 탓하거나 도둑·범인으로 부르지 않고 잡아 "
    "가두거나 벌주지 않는다. 경찰관·소방관은 해결사 차림일 뿐 체포·조사 장면을 쓰지 않는다.\n"
    "- 시작 이야기는 아이가 사건(incident)을 알아챈 데서 시작해 테마 역할의 뭉치가 현장으로 "
    "출동해 큰 질문을 맡는 데까지.\n"
)

ANIMAL_OUTRO = (
    "정답 동물을 찾아 중립 인물(사육사·관리인·사건을 알아챈 아이처럼 후보 동물의 주인이 아닌 "
    "사람)이 제자리에서 부드럽게 안아 올리고 모두 함께 웃는 장면만 쓴다. 혼내거나 가두거나 "
    "쫓아내지 않고, 동물이 걸어 나가는 장면을 쓰지 않는다. 뭉치는 곁에서 지켜본다."
)
ANIMAL_INTRO_CUTS = (
    "사건 장소의 평소 모습과 사건을 알아챌 아이(뭉치·동물 안 나옴)",
    "아이가 사건(incident)을 알아채고 놀람(뭉치·동물 안 나옴)",
    INTRO_GO,
    INTRO_ARRIVE,
)
ANIMAL_OUTRO_CUTS = (
    OUTRO_THINK,
    "정답 동물이 있는 곳에 도착해 그 동물(answerLook 모습)을 바라봄",
    "중립 인물이 정답 동물을 제자리에서 부드럽게 안아 올림(뭉치는 곁에서 지켜봄)",
    "함께 웃으며 기뻐함",
)
ANIMAL_TARGET_CUTS = frozenset({("OUTRO", 2), ("OUTRO", 3), ("OUTRO", 4)})
# 동물 흔적 특징: 동물 몸이 남기는 것(몸을 덮은 것·발자국 발 수·발자국의 발톱). 꼬리 모양은 흔적에
# 남지 않아 목격·기록 날로(일반 흔적 표의 '모양'에 걸리지 않게 이 표만 봄)
ANIMAL_TRACE = re.compile(r"발자국|발가락|발톱|덮은|털|깃털|가시")

PRANK = StoryType(
    code="PRANK",
    label="동물 장난꾸러기 찾기",
    target_label="밝힐 것",
    family="ANIMAL",
    candidate_kind="동물",
    intro_cuts=ANIMAL_INTRO_CUTS,
    outro_cuts=ANIMAL_OUTRO_CUTS,
    target_cuts=ANIMAL_TARGET_CUTS,
    outro_rule=ANIMAL_OUTRO,
    rules=(
        "- 사건: 동물 한 마리가 몰래 장난을 쳤다(target, 예: 떡을 몰래 먹은 동물). 장난의 흔적이 "
        "incident다.\n" + ANIMAL_COMMON
    ),
    facts=ANIMALS,
    answer_cuts=ANIMAL_TARGET_CUTS,
    trace=ANIMAL_TRACE,
    trace_only=True,
)

FOOTPRINT = StoryType(
    code="FOOTPRINT",
    label="발자국 주인 찾기",
    target_label="밝힐 것",
    family="ANIMAL",
    candidate_kind="동물",
    intro_cuts=ANIMAL_INTRO_CUTS,
    outro_cuts=ANIMAL_OUTRO_CUTS,
    target_cuts=ANIMAL_TARGET_CUTS,
    outro_rule=ANIMAL_OUTRO,
    rules=(
        "- 사건: 어떤 동물이 발자국을 남기고 갔다(target, 예: 모래밭에 발자국을 남긴 동물). "
        "발자국이 처음 발견된 일이 incident다.\n" + ANIMAL_COMMON
    ),
    facts=ANIMALS,
    answer_cuts=ANIMAL_TARGET_CUTS,
    trace=ANIMAL_TRACE,
    trace_only=True,
)

# ② 손에 든 것(설계 17.8.13): 대상이 처음부터 손에 있어 공통 규칙의 '대상은 종료 전까지 못 찾음'·
# '대상 몸·겉의 자국은 쓰지 않음'을 이 종류에서는 뒤집는다(대상 자체도 증거)
IN_HAND_COMMON = (
    "- 대상(target)은 처음부터 등장인물이 가지고 있다. 이 종류에서는 공통 규칙의 '대상은 종료 "
    "이야기 전까지 찾지 못한 상태'·'대상 몸이나 겉에 남은 자국은 쓰지 않는다'를 쓰지 않는다: "
    "대상은 장면·대화에 나와도 되고, 대상 자체(묻은 것·밴 냄새·무게·소리·만진 느낌·맛)도 흔적 "
    "증거다. 대상이 지금 어디 있는지 묻지 않고, 대상이 온 곳·대상의 정체(지나간 일)를 묻는다.\n"
)
# ②의 흔적 특징: 대상에 묻거나 밴 것, 대상 자체를 살펴 알 수 있는 것(일반 흔적 표에 더함)
IN_HAND_TRACE = re.compile(r"묻은|가루|꽃가루|흙|밴|냄새|향|무게|소리|느낌|맛|물드는|색|빛")
IN_HAND_INTRO_GO = (INTRO_GO, INTRO_ARRIVE)

ORIGIN = StoryType(
    code="ORIGIN",
    label="출처 찾기",
    target_label="손에 든 것",
    family="IN_HAND",
    candidate_kind="장소",
    intro_cuts=(
        "사건 장소의 평소 모습과 아이(뭉치 안 나옴)",
        "아이가 온 곳을 모르는 대상(target)을 만나거나 받아 들고 고개를 갸웃함(뭉치 안 나옴)",
        *IN_HAND_INTRO_GO,
    ),
    outro_cuts=(
        OUTRO_THINK,
        "정답 장소 앞에 도착해 바라봄",
        "정답 장소의 사람이 대상을 반갑게 맞음(뭉치는 곁에서 지켜봄)",
        "함께 기뻐함",
    ),
    target_cuts=ALL_CUTS,
    outro_rule=(
        "뭉치와 아이가 정답 장소를 찾아가 대상을 돌려주거나 고마움을 전하는 장면만 쓴다(정답 "
        "장소의 "
        "사람은 결말에서 처음 나와도 된다)."
    ),
    rules=(
        IN_HAND_COMMON
        + "- 사건: 학생 또래 아이가 온 곳을 모르는 것(target, 예: 놀이터에서 만난 길 잃은 강아지·"
        "주소가 지워진 택배 상자)을 만나거나 받았다. 잃은 사람·보낸 사람을 탓하지 않는다.\n"
        "- 큰 질문은 그것이 온 곳을 묻는다(예: '이 강아지는 어느 집에서 왔을까?'). candidates는 그 "
        "장소 둘레의 서로 다른 집·가게·공방 이름이다.\n"
        "- 증거: 대상에 묻거나 밴 것(꽃가루·흙·밀가루·냄새)은 흔적, 대상을 데려오거나 들고 온 "
        "사람을 "
        "본 부분 목격, 그때의 기록. 정답 장소 이름이 적힌 것(주소·영수증·가게 도장)은 쓰지 않는다"
        "(답이 바로 보임). 흔적·기록 단서에는 대상 낱말(target)을 넣는다. 그날 장소(place)를 정답 "
        "장소로 두지 않는다.\n"
        "- intro: 아이가 대상을 만나거나 받은 데서 시작해 테마 역할의 뭉치가 현장으로 출동해 큰 "
        "질문을 맡는 데까지.\n"
    ),
    target_in_hand=True,
    trace=IN_HAND_TRACE,
)

GIFT = StoryType(
    code="GIFT",
    label="선물 상자 수수께끼",
    target_label="손에 든 것",
    family="IN_HAND",
    candidate_kind="물건",
    intro_cuts=(
        "사건 장소의 평소 모습과 아이(뭉치 안 나옴)",
        "아이가 리본 달린 선물 상자를 받아 들고 궁금해함(상자는 닫혀 있음, 뭉치 안 나옴)",
        *IN_HAND_INTRO_GO,
    ),
    outro_cuts=(
        OUTRO_THINK,
        "닫힌 선물 상자 앞에 모두 모여 바라봄",
        "아이가 상자를 열어 선물을 꺼냄(뭉치는 곁에서 지켜봄)",
        "함께 기뻐함",
    ),
    target_cuts=ALL_CUTS,  # 상자는 늘 보이고, 상자 안 선물은 answer_cuts에서만
    outro_rule="아이가 선물 상자를 열어 선물(정답)이 나오고 모두 함께 기뻐하는 장면만 쓴다.",
    rules=(
        IN_HAND_COMMON
        + "- 사건: 아이가 리본 달린 선물 상자(target)를 받았다. 상자는 토요일 종료 이야기에서 "
        "연다. "
        "보낸 사람은 등장해도 되지만 선물 이름을 말하지 않는다.\n"
        "- 큰 질문은 상자에 넣은 선물을 묻는다(예: '상자에 넣은 선물은 무엇이었을까?').\n"
        + GIFTS.rule()
        + "- 엔딩 전 장면·콘티에서 상자를 열거나 안을 보여 주지 않는다. 상자는 늘 같은 모습(리본 "
        "달린 네모 상자)이라 상자 모양은 증거가 아니다.\n"
        "- 증거: 상자 무게·흔들면 나는 소리는 아이가 상자를 직접 들어 보거나 흔들어 본 흔적(흔적 "
        "단서에는 '상자' 낱말, 소리 단서에는 '흔들' 낱말)이나 택배 무게 메모·녹음 같은 기록, 산 "
        "가게는 보낸 사람이 그 가게 계산대에서 선물을 사는 걸 본 목격이나 영수증·가게 스티커 같은 "
        "기록(선물 이름은 적혀 있지 않음)으로 쓴다. 가게에서 나오는 걸 본 것만으로는 산 가게의 "
        "근거가 "
        "아니다. 목격·영상으로 무게·소리를 알았다고 쓰지 않는다.\n"
        "- intro: 아이가 상자를 받는 데서 시작해 테마 역할의 뭉치가 현장으로 출동해 큰 질문을 맡는 "
        "데까지.\n"
    ),
    facts=GIFTS,
    target_in_hand=True,
    answer_cuts=frozenset({("OUTRO", 3), ("OUTRO", 4)}),
    trace=IN_HAND_TRACE,
)

SECRET_INGREDIENT = StoryType(
    code="SECRET_INGREDIENT",
    label="비밀 재료 찾기",
    target_label="손에 든 것",
    family="IN_HAND",
    candidate_kind="재료",
    intro_cuts=(
        "사건 장소의 평소 모습과 아이(뭉치 안 나옴)",
        "아이가 음식(target)을 맛보고 무엇이 들었는지 궁금해함(음식은 접시 덮개나 도시락 안이라 "
        "색은 보이지 않음, 뭉치 안 나옴)",
        *IN_HAND_INTRO_GO,
    ),
    outro_cuts=(
        OUTRO_THINK,
        "만든 사람과 함께 덮인 음식 앞에 모임",
        "만든 사람이 비밀 재료를 꺼내 보여 줌(뭉치는 곁에서 지켜봄)",
        "모두 함께 음식을 나눠 먹으며 기뻐함(뭉치는 곁에서 통통 튐)",
    ),
    # 음식에 물든 색이 그림에 보이면 답이 되어, 음식은 비밀 재료를 밝힌 뒤 컷에서만 그림
    target_cuts=frozenset({("OUTRO", 3), ("OUTRO", 4)}),
    outro_rule=(
        "만든 사람이 비밀 재료(정답)를 밝히고 모두 함께 그 음식을 나눠 먹으며 기뻐하는 장면만 쓴다."
    ),
    rules=(
        IN_HAND_COMMON
        + "- 사건: 누군가 만든 음식(target, 예: 대회에 낸 할머니의 떡)에 비밀 재료가 들어갔다. "
        "만든 "
        "사람은 등장해도 되지만 재료 이름은 토요일까지 말하지 않는다.\n"
        "- 큰 질문은 넣은 비밀 재료를 묻는다(예: '할머니가 떡에 넣은 비밀 재료는 무엇이었을까?').\n"
        + INGREDIENTS.rule()
        + "- 증거: 물든 색·맛은 음식·그릇·도마에 남은 흔적(흔적 단서에는 음식 낱말 target)이나 "
        "맛 평가 메모 같은 기록, 산 가게는 만든 사람이 그 가게 계산대에서 재료를 사는 걸 본 "
        "목격이나 장보기 메모·영수증 같은 기록(재료 이름은 적혀 있지 않음)으로 쓴다. 맛은 직접 "
        "맛본 "
        "흔적 날이나 기록 날에만 쓴다(목격으로 맛을 알 수 없음). 엔딩 전 장면·콘티에서 음식의 색을 "
        "보여 주지 않는다"
        "(덮개·도시락 안).\n"
        "- intro: 아이가 음식을 맛보는 데서 시작해 테마 역할의 뭉치가 현장으로 출동해 큰 질문을 "
        "맡는 데까지.\n"
    ),
    facts=INGREDIENTS,
    target_in_hand=True,
    answer_cuts=frozenset({("OUTRO", 3), ("OUTRO", 4)}),
    trace=IN_HAND_TRACE,
)

STORY_TYPES: dict[str, StoryType] = {
    t.code: t for t in (LOST, TREASURE, PRANK, FOOTPRINT, ORIGIN, GIFT, SECRET_INGREDIENT)
}
BY_LABEL = {t.label: t for t in STORY_TYPES.values()}

_NEW = re.compile(
    r"^줄거리: (.+?) / 뭉치 역할: (.+?) / 장소: (.+?) / (찾는 대상|밝힐 것|손에 든 것): (.+)$"
)
_OLD = re.compile(r"^뭉치 역할: (.+?) / 장소: (.+?) / 찾는 대상: (.+)$")


def parse_topic(topic: str | None) -> StoryType | None:
    """learning 주제 씨앗의 종류. 새 형식은 첫 칸, 옛 형식(종류 없음)은 잃어버린 것 찾기.

    관리자가 쓴 자유 글·모르는 종류 이름·라벨이 종류와 안 맞는 글은 None(모델이 종류를 고름).
    learning `ThemeTopicSeeds.parse`와 같은 규칙.
    """
    text = (topic or "").strip()
    if m := _NEW.match(text):
        found = BY_LABEL.get(m.group(1))
        return found if found and found.target_label == m.group(4) else None
    if _OLD.match(text):
        return LOST
    return None


def story_type(theme: dict[str, Any]) -> StoryType:
    """줄거리의 종류(내부 칸 storyType). 없거나 모르는 값이면 잃어버린 것 찾기(#634 전 테마)."""
    return STORY_TYPES.get(str(theme.get("storyType") or ""), LOST)


def is_animal(theme: dict[str, Any]) -> bool:
    return story_type(theme).animal


def type_rules(t: StoryType) -> str:
    """줄거리 프롬프트에 붙이는 그 종류 규칙 묶음(콘티 틀·결말 포함)."""
    intro = ", ".join(f"{i} {role}" for i, role in enumerate(t.intro_cuts, 1))
    outro = ", ".join(f"{i} {role}" for i, role in enumerate(t.outro_cuts, 1))
    return (
        f"줄거리 종류: {t.label}(storyType {t.code}, 후보는 {t.candidate_kind})\n"
        + t.rules
        + f"- outro(마무리 장면): {t.outro_rule}\n"
        f"- introCuts 순서: {intro}.\n"
        f"- outroCuts 순서: {outro}.\n"
    )
