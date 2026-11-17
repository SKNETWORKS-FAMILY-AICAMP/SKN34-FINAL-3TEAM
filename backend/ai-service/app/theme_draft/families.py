"""줄거리 종류·가족 등록표 (#634, 설계 ai.md 17.8·17.8.13).

종류마다 if문을 흩뿌리지 않고 이 표 하나에서 줄거리 규칙 묶음·콘티 틀·대상이 나와도 되는 컷·
흔적 특징·사실표를 꺼내 쓴다. 종류 이름(label)과 넷째 칸 이름(target_label)은 learning
`ThemeTopicSeeds.StoryType`과 같은 표다(learning이 주제 씨앗 `topic` 첫 칸에 넣음).

가족: ① 숨은 것(HIDDEN, 후보는 장소) — LOST·TREASURE, ③ 동물 주인공(ANIMAL) — PRANK·FOOTPRINT,
② 손에 든 것의 출처·정체(IN_HAND) — ORIGIN·GIFT·SECRET_INGREDIENT, ④ 때·길·방법(WHEN_HOW) —
WHEN·ROUTE·VEHICLE(설계 17.8.17), ⑤ 소리(SOUND) — SOUND(설계 17.8.18).
성질별 칸: 사실표(facts, 있으면 후보 이름을 엔딩 전에 감춤), 대상이 처음부터 손에 있음
(target_in_hand), 정답 후보가 그림에 나와도 되는 컷(answer_cuts), 종류별 흔적 특징(trace),
시작 이야기 끝에 코드가 붙이는 규칙(intro_notes), 단서 앞 시각 붙이기(clue_time), 대상을 그림에
그릴 수 있는지(target_visual), 흔적 단서의 주인 낱말(owner_words), 장소가 맞아야 둘 수 있는
후보(place_needs).
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

StoryTypeCode = Literal[
    "LOST",
    "TREASURE",
    "PRANK",
    "FOOTPRINT",
    "ORIGIN",
    "GIFT",
    "SECRET_INGREDIENT",
    "WHEN",
    "ROUTE",
    "VEHICLE",
    "SOUND",
]
FamilyCode = Literal["HIDDEN", "ANIMAL", "IN_HAND", "WHEN_HOW", "SOUND"]

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
    # '없는 값'(종소리 없음·표 없음처럼 무엇이 없다는 값). 초등학생이 근거로 내세우기 약하고 글 검토
    # CLUE_LOGIC에 걸리기 쉬워 단서로 쓰지 않는다(#634 ④ 사용자 확인 2026-11-17, CLUE_ABSENT).
    # 정답은
    # 있는 값 특징만으로 다른 후보와 갈라져야 함(FACT_TABLE)
    absent: frozenset[str] = frozenset()
    # 범주(후보 → 동물·물건). 있으면 후보 4개는 한 범주에서만(#634 ⑤ 이슈 결정, SAME_KIND)
    groups: dict[str, str] | None = None
    # 특징별 기록 매체(RECORD 날). 소리는 사진으로, 무게·맛은 사진·영상으로 알 수 없음(⑤ 설계
    # 17.8.18 틈 5) — 줄거리 직후 코드가 맞지 않는 매체를 바꿈(checks.fit_media)
    media: dict[str, frozenset[str]] | None = None
    # 정답 공개 전 그림·영상에 감출 것(영어 지시). 없으면 후보 목록(checks 밖
    # prompts._no_candidates)
    image_hide: str | None = None
    # 종료 컷에 정답을 그릴 수 있는지(시각 표는 그릴 것이 없음)
    drawable: bool = True

    def kinds_of(self, feature: str) -> frozenset[str] | None:
        return (self.kinds or {}).get(feature)

    def fact(self, candidate: str, feature: str) -> str | None:
        row = self.rows.get(candidate.strip())
        if row is None or feature not in self.features:
            return None
        return row[self.features.index(feature)]

    def media_of(self, feature: str) -> frozenset[str] | None:
        return (self.media or {}).get(feature)

    def group(self, candidate: str) -> str | None:
        return (self.groups or {}).get(candidate.strip())

    def present(self, candidate: str, feature: str) -> bool:
        """그 후보의 그 특징 값이 '있는 값'인지(표 밖이면 False)."""
        value = self.fact(candidate, feature)
        return value is not None and value not in self.absent

    def separable(self, answer: str, other: str, features: tuple[str, ...] | list[str]) -> bool:
        """정답을 그 후보와 정답의 '있는 값' 특징만으로 가를 수 있는지."""
        return any(
            self.present(answer, f) and self.fact(answer, f) != self.fact(other, f)
            for f in features
        )

    def blocked(self) -> dict[str, list[str]]:
        """정답별로 후보로 둘 수 없는 이름(표의 모든 특징으로도 가를 수 없음). 없으면 빈 사전."""
        out = {
            a: [c for c in self.rows if c != a and not self.separable(a, c, self.features)]
            for a in self.rows
        }
        return {a: cs for a, cs in out.items() if cs}

    def text(self) -> str:
        head = " | ".join([self.name, *self.features])
        return "\n".join([f"  {head}", *(f"  {' | '.join([k, *v])}" for k, v in self.rows.items())])

    def absent_rule(self) -> str:
        """없는 값 규칙(없는 값이 있는 표만)."""
        if not self.absent:
            return ""
        blocked = "; ".join(
            f"정답이 {a}면 후보에 {'·'.join(cs)}를 두지 않음" for a, cs in self.blocked().items()
        )
        return (
            f"- 없는 값 {sorted(self.absent)}은 단서로 쓰지 않는다: 정답의 값이 없는 값인 특징은 "
            "그 테마의 단서 특징(condition.feature)으로 쓰지 않고, allowed에도 없는 값을 넣지 "
            "않는다(코드 검사 CLUE_ABSENT, 무엇이 없다는 말은 근거가 약함). 정답은 features에 넣은 "
            "특징 가운데 정답의 값이 있는 값인 특징만으로 다른 후보와 모두 갈라져야 한다(코드 검사 "
            "FACT_TABLE)" + (f": {blocked}" if blocked else "") + ".\n"
        )

    def extra_rule(self) -> str:
        """범주·기록 매체 규칙(그 칸이 있는 표만)."""
        out = ""
        if self.groups:
            kinds = sorted(set(self.groups.values()))
            out += (
                f"- 후보 4개는 한 범주({'·'.join(kinds)} 가운데 하나)에서만 고른다(섞으면 코드 "
                "검사 "
                "SAME_KIND). 범주: "
                + " / ".join(
                    f"{g}: {'·'.join(c for c, x in self.groups.items() if x == g)}" for g in kinds
                )
                + "\n"
            )
        if self.media:
            out += (
                "- 기록(RECORD) 날의 기록 매체는 특징에 맞게(안 맞으면 코드가 매체를 바꿈): "
                + " / ".join(f"{f}: {'·'.join(sorted(m))}" for f, m in self.media.items())
                + "\n"
            )
        return out

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
            + self.absent_rule()
            + self.extra_rule()
            + "- 엔딩 전 글(title·world·intro·시작 "
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
    # ④: 시작 이야기 끝에 코드가 붙이는 규칙 문장(말투별 '…요.'·'…다.'·'…어.' 세 꼴). 학생 화면에는
    # 시작 이야기만 보여 시각을 가르는 마을 규칙을 여기에 둔다(checks.compose_intro)
    intro_notes: tuple[str, str, str] | None = None
    # 단서 앞에 그때 시각을 붙이는지(#535 add_clue_time). 시간 탐정은 그때가 곧 정답이라 끔
    clue_time: bool = True
    # 대상을 그림에 그릴 수 있는지(시간 탐정의 대상은 '때'라 그릴 것이 없음 — 그리지 말라는 지시와
    # 그림 검토의 대상 판정을 빼고, 시계를 그리지 않게 함)
    target_visual: bool = True
    # 흔적 단서에 넣을 주인 낱말(비면 target에서 뽑음). 동물: '동물', 탈것: '탈것'·'바퀴'
    owner_words: tuple[str, ...] = ()
    # 장소가 맞아야 후보로 둘 수 있는 이름과 그 장소 말(탈것의 배는 물가에서만, VEHICLE_PLACE)
    place_needs: tuple[tuple[str, re.Pattern[str]], ...] = ()
    # ⑤ 설계 17.8.18 틈 2: ④에서 시간 탐정 표시처럼 쓰던 칸(clue_time·target_visual)을 성질별로 나눔
    # 엔딩 전 글·미션·대화에 시각을 쓰지 않음(TIME_WORD, 시간 탐정)
    hide_times: bool = False
    # 마무리 장면에 정답 아닌 후보면 칸 고쳐 쓰기(OUTRO_ANSWER, 시간 탐정·소리 탐정)
    outro_check: bool = False
    # 미션 이야기 조각·대화에서 대상을 말하는 법(없으면 찾는 대상·손에 든 것 문구)
    target_note: str | None = None
    # 정답 모습 칸(answerLook) 필수 — 종료 컷마다 같은 모습으로 그림(동물 주인공·소리 탐정)
    needs_answer_look: bool = False
    # 엔딩 전 글·미션·대화에서 정답만의 값뿐 아니라 그 테마 후보끼리 갈리는 표 값 전부를 막음(소리
    # 탐정:
    # 시작 이야기의 소리 묘사가 단서를 앞질러 말함, 틈 4)
    strict_facts: bool = False
    # 모든 단서에 넣을 낱말(CLUE_OWNER, 소리 탐정 '소리'). 탈것의 온 사람은 target에서 뽑음
    clue_word: str | None = None
    # 모든 단서에 대상 낱말(target)을 넣음(CLUE_OWNER, 출처 찾기·길 — 마지막 확인: '가게 앞 바닥을
    # 봤다'처럼 장소만 말해 그곳이 대상이 온 곳이라는 연결이 없다고 글 검토 CLUE_LOGIC)
    owner_all: bool = False

    @property
    def animal(self) -> bool:
        return self.family == "ANIMAL"

    @property
    def hide_candidates(self) -> bool:
        """후보 이름을 엔딩 전 글·미션·대화·그림에 감추는 종류(사실표가 있는 종류)."""
        return self.facts is not None

    @property
    def no_trace(self) -> bool:
        """사실표 특징 어느 것도 흔적으로 알 수 없는 종류(시간 탐정). 증거 배정의 흔적을 미리
        목격으로 바꿔 모델에 준다(checks.plan_for_type)."""
        table = self.facts
        return (
            table is not None
            and table.kinds is not None
            and all("TRACE" not in (table.kinds_of(f) or ALL_KINDS) for f in table.features)
        )


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
    features=("상자 무게", "흔들면 나는 소리", "선물을 산 가게"),
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
        "선물을 산 가게": frozenset({"SIGHTING", "RECORD"}),
    },
    media={
        "상자 무게": frozenset({"메모", "일지"}),
        "흔들면 나는 소리": frozenset({"녹음", "영상", "메모", "일지"}),
    },
)

# 재료 사실표(#634 ②, 기준안): 음식에 물드는 색은 그림에 보이면 답이 되므로 엔딩 전 그림에 음식을
# 그리지 않고(target_cuts), 엔딩 전 글의 정답 재료 값은 ANSWER_FACT로 막음. '자라는 곳'은 재료를
# 넣는 걸 봐도 알 수 없다고 글 검토 CLUE_LOGIC(② 작은 실측) — 산 가게(목격·장보기 기록)로 바꿈
INGREDIENTS = FactTable(
    name="재료",
    features=("물드는 색", "맛", "재료를 산 가게"),
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
        "재료를 산 가게": frozenset({"SIGHTING", "RECORD"}),
    },
    media={"맛": frozenset({"메모", "일지"})},
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
    owner_words=("동물",),
    needs_answer_look=True,
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
    owner_words=("동물",),
    needs_answer_look=True,
)

# ② 손에 든 것(설계 17.8.13): 대상이 처음부터 손에 있어 공통 규칙의 '대상은 종료 전까지 못 찾음'·
# '대상 몸·겉의 자국은 쓰지 않음'을 이 종류에서는 뒤집는다(대상 자체도 증거)
IN_HAND_COMMON = (
    "- 대상(target)은 처음부터 등장인물이 가지고 있다. 이 종류에서는 공통 규칙의 '대상은 종료 "
    "이야기 전까지 찾지 못한 상태'·'대상 몸이나 겉에 남은 자국은 쓰지 않는다'를 쓰지 않는다: "
    "대상은 장면·대화에 나와도 되고, 대상 자체(묻은 것·밴 냄새·무게·소리·만진 느낌·맛)도 흔적 "
    "증거다. 대상이 지금 어디 있는지 묻지 않고, 대상이 온 곳·대상의 정체(지나간 일)를 묻는다.\n"
    # 마지막 확인: 산 때의 목격과 받은 뒤 들어 본 흔적을 '서로 다른 때의 증거'로 본 글 검토
    # CLUE_LOGIC
    "- 증거는 두 때일 수 있다: 대상을 준비한(사거나 만들거나 보내거나 데려온) 때의 목격·기록과, "
    "받은 뒤 아이가 대상을 직접 살핀 흔적. 둘 다 같은 대상의 증거라 공통 규칙의 '같은 그때'로 "
    "본다(evidence.when은 각각 '선물을 산 때'·'상자를 받은 뒤'처럼 그 증거가 생긴 때).\n"
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
        "(답이 바로 보임). 모든 단서에 대상 낱말(target)을 넣어 그 대상이 온 곳의 증거임을 밝힌다"
        "(코드 검사 CLUE_OWNER, 장소 모습만 말하지 않음). 그날 장소(place)를 정답 "
        "장소로 두지 않는다.\n"
        "- intro: 아이가 대상을 만나거나 받은 데서 시작해 테마 역할의 뭉치가 현장으로 출동해 큰 "
        "질문을 맡는 데까지.\n"
    ),
    target_in_hand=True,
    trace=IN_HAND_TRACE,
    owner_all=True,
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

# ④ 때·길·방법(설계 17.8.17, 사용자 확인 2026-11-17)
# 시간 탐정 마을 규칙표(기준안): 그림자·밝기는 계절마다 달라 시각을 가르는 근거로 애매해 마을
# 규칙으로
# 정함. 값은 단서 문장에 그대로 들어가는 꼴('열린 빵집이 보였대')로 둠(값 낱말이 단서에 그대로
# 있어야
# 함, CLUE_TEXT). 오전 10시·오후 3시는 세 값이 같아 한 테마에 함께 두지 못함(FACT_TABLE)
TIMES = FactTable(
    name="시각",
    features=("종소리", "빵집 문", "가로등"),
    rows={
        "아침 7시": ("종 안 울림", "닫힌 빵집", "꺼진 가로등"),
        "오전 10시": ("종 안 울림", "열린 빵집", "꺼진 가로등"),
        "낮 12시": ("종소리", "열린 빵집", "꺼진 가로등"),
        "오후 3시": ("종 안 울림", "열린 빵집", "꺼진 가로등"),
        "저녁 7시": ("종 안 울림", "열린 빵집", "켜진 가로등"),
        "밤 9시": ("종 안 울림", "닫힌 빵집", "켜진 가로등"),
    },
    # 그때 들리거나 보인 것이라 흔적에 남지 않음: 들은·본 사람의 목격, 그때 찍힌 사진·영상·녹음 기록
    kinds={
        "종소리": frozenset({"SIGHTING", "RECORD"}),
        "빵집 문": frozenset({"SIGHTING", "RECORD"}),
        "가로등": frozenset({"SIGHTING", "RECORD"}),
    },
    absent=frozenset({"종 안 울림"}),
    media={"종소리": frozenset({"녹음", "영상", "일지", "메모"})},
    image_hide="Do not draw any clock or watch (it would show the time).",
    drawable=False,
)
# 시작 이야기 끝에 코드가 붙이는 마을 규칙(말투 '요'·'다'·반말). 경계 시각은 표에 두지 않음(아침
# 7시는
# 가로등이 꺼진 뒤, 저녁 7시는 켜진 뒤·빵집 닫기 전)
TOWN_RULE = (
    "이 마을 종은 낮 12시에만 울리고, 빵집은 오전 9시부터 저녁 8시까지 문을 열고, 가로등은 "
    "저녁 6시부터 아침 6시까지 "
)
TOWN_NOTES = (TOWN_RULE + "켜져요.", TOWN_RULE + "켜진다.", TOWN_RULE + "켜져.")

# 탈것 사실표(기준안). 도착한 곳 바퀴 자국: 자전거·킥보드는 도착한 곳 앞까지 타고 와 세우고
# 버스·기차·여객선은 정류장·역·나루에서 내림(버스에도 바퀴가 있어 '바퀴 자국 없음'만 쓰면 헷갈림 —
# 사용자 확인 이름은 '집 앞 바퀴 자국'이었으나 판정 실측에서 선생님이 분교에 온 이야기와 어긋나
# 바꿈).
# 들고 온 것: 처음 설계의 '들고 온 표'(버스표·기차표)는 값에 후보 이름이 들어가 단서가 정답 이름을
# 그대로 말함(ANSWER_LEAK, 시험에서 발견) → 이름이 없는 물건으로(값에 후보 이름 없음, 시험으로 지킴)
VEHICLES = FactTable(
    name="탈것",
    features=("도착한 곳 바퀴 자국", "들고 온 것", "들린 소리"),
    rows={
        "자전거": ("가는 바퀴 자국", "헬멧", "따르릉 소리"),
        "킥보드": ("작은 바퀴 자국", "헬멧", "드르륵 소리"),
        "버스": ("바퀴 자국 없음", "교통카드", "부릉 소리"),
        "기차": ("바퀴 자국 없음", "좌석표", "덜컹덜컹 소리"),
        "여객선": ("바퀴 자국 없음", "배표", "뱃고동 소리"),
    },
    kinds={
        "도착한 곳 바퀴 자국": frozenset({"TRACE", "RECORD"}),
        "들고 온 것": frozenset({"SIGHTING", "RECORD"}),
        "들린 소리": frozenset({"SIGHTING", "RECORD"}),
    },
    absent=frozenset({"바퀴 자국 없음"}),
    media={"들린 소리": frozenset({"녹음", "영상", "일지", "메모"})},
)
# 길 종류의 흔적 특징: 지나온 길에서 대상에 묻은 것만(이 표만 봄). ②의 IN_HAND_TRACE는 대상 자체를
# 살피는 무게·소리·맛까지 흔적으로 봐서, 길에서 들린 소리가 흔적 날에 배정돼 글 검토 CLUE_LOGIC
# ("새소리는 자리에 남는 흔적이 아님", ④ 판정 실측) — 길의 모양·소리·빛은 목격·기록 날로
ROUTE_TRACE = re.compile(
    r"묻은|묻은 것|가루|흙|모래|진흙|풀물|물기|젖|물방울|밴|냄새|바닥|재질|자국"
)

# 여객선은 물가에서만(VEHICLE_PLACE). '강' 한 글자는 강아지·강당에 걸려 붙은 꼴만
WATER_PLACE = re.compile(
    r"바다|바닷|강가|강변|강물|강둑|강을|강에|항구|포구|섬|호수|부두|나루|선착장|뱃길"
)

WHEN = StoryType(
    code="WHEN",
    label="시간 탐정",
    target_label="밝힐 것",
    family="WHEN_HOW",
    candidate_kind="시각",
    intro_cuts=(
        "사건 장소의 평소 모습과 아이(뭉치 안 나옴, 시계는 보이지 않음)",
        "아이가 이미 끝나 있는 그 일(target의 일, 예: 젖은 화단)을 보고 언제였는지 궁금해함"
        "(시계는 보이지 않음, 뭉치 안 나옴)",
        INTRO_GO,
        INTRO_ARRIVE,
    ),
    outro_cuts=(
        OUTRO_THINK,
        "그 일을 한 사람 앞에 도착해 바라봄",
        "그 사람이 그때 한 일을 웃으며 이야기함(뭉치는 곁에서 지켜봄)",
        "함께 기뻐함",
    ),
    target_cuts=ALL_CUTS,  # 대상이 '때'라 그릴 것이 없음(target_visual)
    outro_rule=(
        "뭉치와 아이가 그 일을 한 사람을 찾아가 정답 시각에 그 일을 했다는 것을 확인하고 고마움을 "
        "전하며 함께 기뻐하는 장면만 쓴다(그 사람은 결말에서 처음 나와도 된다)."
    ),
    rules=(
        "- 사건: 누군가 한 일(target 글, 예: '화단에 물을 준 때'의 물 주기)이 이미 끝나 있고 언제 "
        "했는지 모른다. 그 일을 알아챈 아이(학생 또래)가 등장인물 중 한 명이다. 그 일은 처음부터 "
        "알려진 사실이라 이야기에 나와도 되고, 모르는 것은 때뿐이다. 그 일을 한 사람은 탓하지 "
        "않는다.\n"
        "- target은 주제의 '밝힐 것' 글을 그대로 쓴다(시각을 쓰지 않음). 큰 질문은 그 일을 한 때를 "
        "묻는다(예: '화단에 물을 준 건 언제였을까?').\n"
        + TIMES.rule()
        + "- 시각을 가르는 마을 규칙은 코드가 시작 이야기(intro) 끝에 붙인다: '"
        + TOWN_NOTES[0]
        + "' intro에는 이 규칙과 어떤 시각도 쓰지 않는다.\n"
        "- 이 종류에서는 공통 규칙의 'clue 문장 안에 그때의 시각을 넣는다'와 '시각은 오전·오후 "
        "12시간제로 쓴다'를 쓰지 않는다: 그때가 곧 정답이다. evidence.when은 '화단에 물을 준 "
        "그때'처럼 그 일로 쓰고, 엔딩 전 글(clue·장면·대화 줄 포함)에 어떤 시각(3시·오전 9시·"
        "정오 등)도 쓰지 않는다(코드 검사 TIME_WORD·CANDIDATE_NAME). 다른 날 장면의 때도 시각 "
        "대신 '아침에'·'점심 먹고'처럼 쓴다.\n"
        "- 증거: 그 일을 하던 그때 들린 종소리, 보인 빵집·가로등을 그때 듣거나 본 사람의 목격"
        "(들은 사람의 증언도 SIGHTING), 그때 찍힌 사진·영상·녹음 기록. 단서는 '물을 줄 때 열린 "
        "빵집이 보였대'처럼 그 일과 그때 보이거나 들린 것을 잇는다. 그 일의 흔적(젖은 흙)은 "
        "시각을 알려 주지 않아 단서로 쓰지 않는다(이 종류는 흔적 단서가 없다).\n"
        "- 엔딩 전 장면·콘티에 시계를 두지 않는다(그림에 시각이 보임).\n"
        "- intro: 아이가 그 일을 알아챈 데서 시작해 테마 역할의 뭉치가 현장으로 출동해 큰 질문을 "
        "맡는 데까지.\n"
    ),
    facts=TIMES,
    answer_cuts=frozenset({("OUTRO", 2), ("OUTRO", 3), ("OUTRO", 4)}),
    intro_notes=TOWN_NOTES,
    clue_time=False,
    target_visual=False,
    hide_times=True,
    outro_check=True,
    target_note="그 일은 이야기에 나와도 되지만 그 일을 한 때는 모른다. 어떤 시각(3시·오전 "
    "9시·정오 등)도 쓰지 않는다(시각 계산 문제도 내지 않음)",
)

ROUTE = StoryType(
    code="ROUTE",
    label="어느 길로 왔을까",
    target_label="손에 든 것",
    family="WHEN_HOW",
    candidate_kind="길",
    intro_cuts=(
        "사건 장소의 평소 모습과 아이(뭉치 안 나옴)",
        "아이가 배달된 대상(target)을 받아 들고 어느 길로 왔을지 궁금해함(뭉치 안 나옴)",
        *IN_HAND_INTRO_GO,
    ),
    outro_cuts=(
        OUTRO_THINK,
        "정답 길에 도착해 바라봄",
        "그 길에서 대상을 나른 사람을 만나 반갑게 인사함(뭉치는 곁에서 지켜봄)",
        "함께 기뻐함",
    ),
    target_cuts=ALL_CUTS,
    outro_rule=(
        "뭉치와 아이가 정답 길을 따라 걸어가 대상을 나른 사람을 만나고 고마움을 전하며 함께 "
        "기뻐하는 장면만 쓴다(나른 사람은 결말에서 처음 나와도 된다)."
    ),
    rules=(
        IN_HAND_COMMON
        + "- 사건: 학생 또래 아이가 받은 것(target, 예: 할머니가 보낸 택배 상자·누가 문 앞에 두고 "
        "간 꽃다발)이 어느 길로 왔는지 모른다. 나른 사람을 탓하지 않는다.\n"
        "- 큰 질문은 그것이 지나온 길을 묻는다(예: '택배는 어느 길로 배달됐을까?'). candidates는 "
        "그 장소 둘레의 서로 다른 길 이름이다(골목길·큰길·공원 산책길·강둑길처럼 테마 장소에 "
        "맞게).\n"
        "- 증거: 대상에 묻은 것(흙·풀물·물방울·꽃가루)은 흔적, 그 길로 대상을 나르는 사람을 본 "
        "부분 목격, 그때의 기록(배달 기록 일부·사진). 길 이름이 적힌 것(주소·배달 기록의 길 "
        "이름)은 쓰지 않는다(답이 바로 보임). 모든 단서에 대상 낱말(target)을 넣어 그 대상이 "
        "지나온 "
        "길의 증거임을 밝힌다(코드 검사 CLUE_OWNER). 그날 "
        "장소(place)를 정답 길로 두지 않는다.\n"
        "- intro: 아이가 대상을 받은 데서 시작해 테마 역할의 뭉치가 현장으로 출동해 큰 질문을 "
        "맡는 데까지.\n"
    ),
    target_in_hand=True,
    trace=ROUTE_TRACE,
    trace_only=True,
    owner_all=True,
)

VEHICLE_TARGET_CUTS = frozenset({("OUTRO", 2), ("OUTRO", 3), ("OUTRO", 4)})
VEHICLE = StoryType(
    code="VEHICLE",
    label="무엇을 타고 왔을까",
    target_label="밝힐 것",
    family="WHEN_HOW",
    candidate_kind="탈것",
    intro_cuts=(
        "사건 장소의 평소 모습과 아이(뭉치 안 나옴)",
        "온 사람(target 글의 사람)이 아이와 반갑게 인사함(탈것은 보이지 않음, 뭉치 안 나옴)",
        INTRO_GO,
        INTRO_ARRIVE,
    ),
    outro_cuts=(
        OUTRO_THINK,
        "정답 탈것이 있는 곳(도착한 곳 앞·정류장·역·나루터)에 도착해 바라봄",
        "온 사람이 탈것 곁에서 웃음(뭉치는 곁에서 지켜봄)",
        "함께 기뻐함",
    ),
    target_cuts=VEHICLE_TARGET_CUTS,  # 대상 = 타고 온 탈것(엔딩에서만)
    outro_rule=(
        "뭉치와 아이가 온 사람과 함께 그 사람이 타고 온 탈것을 보러 가 확인하고 함께 기뻐하는 "
        "장면만 쓴다."
    ),
    rules=(
        "- 사건: 손님(target 글의 사람, 예: 삼촌)이 아이 집이나 마을에 왔는데 무엇을 타고 왔는지 "
        "모른다(깜짝 방문 등). 온 사람은 등장인물이고 처음부터 나와도 되지만 타고 온 탈것은 "
        "토요일까지 말하지 않는다. target은 주제의 '밝힐 것' 글을 그대로 쓴다(예: '삼촌이 타고 온 "
        "탈것'). 엔딩 전에는 탈것이 장면·콘티에 나오지 않는다.\n"
        "- 큰 질문은 타고 온 탈것을 묻는다(예: '삼촌은 무엇을 타고 왔을까?').\n"
        + VEHICLES.rule()
        + "- 여객선은 장소가 바닷가·강가·섬처럼 물가일 때만 후보로 둔다(world나 intro에 "
        "바다·강가·항구 같은 물가 말이 있어야 함, 코드 검사 VEHICLE_PLACE).\n"
        "- 증거: 도착한 곳 바퀴 자국은 온 사람이 도착한 곳 앞에 남은 흔적(흔적 단서에는 '바퀴' "
        "낱말)이나 그 자국을 찍은 "
        "사진, 들고 온 것은 온 사람이 그것을 들고 오거나 꺼내는 걸 본 목격이나 그것을 찍은 사진, "
        "들린 소리는 그가 "
        "올 때 소리를 들은 사람의 목격(들은 사람의 증언도 SIGHTING)이나 녹음으로 쓴다. 탈것 이름이 "
        "적힌 것(노선 이름·정류장 이름)은 쓰지 않는다.\n"
        "- 모든 단서(clue)에 온 사람(target 글의 사람, 예: 삼촌)을 넣어 그 사람이 탄 탈것의 "
        "증거임을 밝힌다(예: '삼촌이 올 때 부릉 소리가 났대', 코드 검사 CLUE_OWNER). "
        "목격은 탈것을 본 것이 아니라 온 사람이 들고 온 것을 본 것이나 그가 올 때 소리를 "
        "들은 것이다(탈것을 봤다고 쓰면 엔딩 전에 대상이 나옴).\n"
        "- intro: 손님이 온 데서 시작해 테마 역할의 뭉치가 현장으로 출동해 큰 질문을 맡는 데까지.\n"
    ),
    facts=VEHICLES,
    answer_cuts=VEHICLE_TARGET_CUTS,
    owner_words=("탈것", "바퀴"),
    place_needs=(("여객선", WATER_PLACE),),
)

# ⑤ 소리(설계 17.8.18, 사용자 확인 2026-11-17). 물건은 소리를 내는 것이 분명하고 장면에 저절로
# 나오지
# 않는 바깥 물건만, 동물은 계절을 타지 않는 것만(겨울잠·여름 곤충 없음). 값은 단서 문장에 그대로
# 들어가는 꼴, 소리 난 곳은 흔한 장소 낱말이 아닌 꼴(정답만의 값은 엔딩 전 글에 못 씀)
SOUND_MEDIA = frozenset({"녹음", "영상", "일지", "메모"})
SOUNDS = FactTable(
    name="소리",
    features=("소리 난 곳", "소리 느낌", "소리 나는 밤", "소리 움직임"),
    rows={
        "부엉이": ("높은 나무 위", "우는 소리", "매일 밤", "한곳에서 나는 소리"),
        "고양이": ("지붕 꼭대기", "우는 소리", "매일 밤", "옮겨 다니는 소리"),
        "생쥐": ("천장 안쪽", "긁는 소리", "매일 밤", "옮겨 다니는 소리"),
        "너구리": ("쓰레기통 둘레", "뒤적이는 소리", "매일 밤", "옮겨 다니는 소리"),
        "강아지": ("개집 앞", "낑낑 소리", "매일 밤", "한곳에서 나는 소리"),
        "바람개비": ("화단 가운데", "팔랑이는 소리", "바람 부는 밤", "한곳에서 나는 소리"),
        "녹슨 그네": ("놀이터 구석", "끼익 소리", "바람 부는 밤", "한곳에서 나는 소리"),
        "빈 양동이": ("수돗가 바닥", "똑똑 소리", "비 오는 밤", "한곳에서 나는 소리"),
        "빈 깡통": ("골목 바닥", "데구루루 소리", "바람 부는 밤", "옮겨 다니는 소리"),
        "현수막": ("담장 위", "펄럭이는 소리", "바람 부는 밤", "한곳에서 나는 소리"),
    },
    # 소리는 흔적에 남지 않음: 들은 사람의 목격, 녹음·영상·일지·메모 기록(흔적 0개, 이슈 결정
    # "녹음·목격 위주")
    kinds={
        "소리 난 곳": frozenset({"SIGHTING", "RECORD"}),
        "소리 느낌": frozenset({"SIGHTING", "RECORD"}),
        "소리 나는 밤": frozenset({"SIGHTING", "RECORD"}),
        "소리 움직임": frozenset({"SIGHTING", "RECORD"}),
    },
    groups={
        **{c: "동물" for c in ("부엉이", "고양이", "생쥐", "너구리", "강아지")},
        **{c: "물건" for c in ("바람개비", "녹슨 그네", "빈 양동이", "빈 깡통", "현수막")},
    },
    media={
        "소리 난 곳": frozenset({"영상", "일지", "메모"}),
        "소리 느낌": SOUND_MEDIA,
        "소리 나는 밤": frozenset({"일지", "메모"}),
        "소리 움직임": SOUND_MEDIA,
    },
)
SOUND_TARGET_CUTS = frozenset({("OUTRO", 2), ("OUTRO", 3), ("OUTRO", 4)})

SOUND = StoryType(
    code="SOUND",
    label="소리 탐정",
    target_label="밝힐 것",
    family="SOUND",
    candidate_kind="동물·물건",
    intro_cuts=(
        "사건 장소의 평소 모습과 아이(밤이라도 밝고 포근한 색, 후보 동물·물건은 보이지 않음, 뭉치 "
        "안 "
        "나옴)",
        "아이가 밤에 궁금한 소리를 듣고 귀 기울임(무섭지 않게, 후보는 보이지 않음, 뭉치 안 나옴)",
        INTRO_GO,
        INTRO_ARRIVE,
    ),
    outro_cuts=(
        OUTRO_THINK,
        "정답(answerLook 모습)이 있는 곳에 도착해 바라봄",
        "동물이면 모두 조금 떨어져서 함께 바라봄(만지지 않음), 물건이면 사람이 소리가 나지 않게 "
        "손봄(뭉치는 곁에서 지켜봄)",
        "함께 웃으며 기뻐함",
    ),
    target_cuts=ALL_CUTS,  # 대상이 '소리'라 그릴 것이 없음(target_visual)
    outro_rule=(
        "소리의 정체(정답)가 밝혀지는 장면만 쓴다. 동물이면 모두 조금 떨어져서 함께 바라보며 웃고 "
        "만지거나 붙잡지 않는다. 물건이면 사람이 소리가 나지 않게 손본다(바람개비를 단단히 "
        "꽂음·그네에 "
        "기름칠·양동이를 엎어 둠·깡통을 치움·현수막을 묶음). 뭉치는 곁에서 지켜본다."
    ),
    rules=(
        "- 사건: 아이(학생 또래, 등장인물 중 한 명)가 밤마다 궁금한 소리를 듣는다. 소리는 무섭지 "
        "않은 "
        "궁금증일 뿐이다(귀신·괴물·유령 없음, 코드 검사 UNSAFE). 그 소리는 처음부터 알려진 "
        "사실이라 "
        "이야기에 나와도 되고, 모르는 것은 소리를 낸 것이다.\n"
        "- target은 주제의 '밝힐 것' 글을 그대로 쓴다(후보 이름·표 값 없이). 큰 질문은 그 소리를 "
        "낸 "
        "것을 묻는다(예: '밤마다 들린 소리의 정체는 무엇이었을까?').\n"
        + SOUNDS.rule()
        + "- 엔딩 전 글·미션·대화에는 그 테마 후보끼리 값이 갈리는 표 값(소리 난 곳·소리 느낌 "
        "등)을 쓰지 않는다(정답만의 값이 아니어도 단서를 앞질러 말함, 코드 검사 ANSWER_FACT). "
        "시작 이야기는 '이상한 소리'·'궁금한 소리'처럼 쓴다.\n"
        "- answerLook: 정답 동물·물건의 겉모습 한 줄(종료 그림·영상에서 같은 모습으로 그림). "
        "반드시 "
        "채운다(코드 검사 REQUIRED). incident는 null.\n"
        "- 증거: 그 소리를 들은 사람의 목격(들은 사람의 증언도 SIGHTING), 녹음·영상·일지·메모 "
        "기록. "
        "소리는 흔적에 남지 않아 흔적 단서가 없다. 모든 단서(clue)에 '소리' 낱말을 넣어 그 소리의 "
        "증거임을 밝힌다(코드 검사 CLUE_OWNER, 예: '녹음에 끼익 소리가 담겼어'). 이 종류에서는 "
        "공통 "
        "규칙의 '다섯 단서가 같은 그때'를 '소리가 나던 밤'으로 본다: evidence.when은 '소리가 나던 "
        "밤'이고, 여러 밤의 증거여도 같은 소리면 같은 그때다.\n"
        "- 소리 난 곳 단서는 '소리가 놀이터 구석에서 났대'처럼 소리가 난 자리로 쓰고, 듣는 사람이 "
        "있던 곳('놀이터 구석에서 들었대')으로 쓰지 않는다(⑤ 판정 실측 글 검토 CLUE_LOGIC).\n"
        "- 엔딩 전 장면·콘티에 후보 동물·물건을 내지 않는다.\n"
        "- intro: 아이가 궁금한 소리를 들은 데서 시작해 테마 역할의 뭉치가 현장으로 출동해 큰 "
        "질문을 "
        "맡는 데까지.\n"
    ),
    facts=SOUNDS,
    answer_cuts=SOUND_TARGET_CUTS,
    target_visual=False,
    outro_check=True,
    target_note="그 소리는 이야기에 나와도 되지만 소리를 낸 것은 모른다. 후보끼리 갈리는 소리 값"
    "(소리 난 곳·소리 느낌 등)은 쓰지 않는다",
    needs_answer_look=True,
    strict_facts=True,
    clue_word="소리",
)

STORY_TYPES: dict[str, StoryType] = {
    t.code: t
    for t in (
        LOST,
        TREASURE,
        PRANK,
        FOOTPRINT,
        ORIGIN,
        GIFT,
        SECRET_INGREDIENT,
        WHEN,
        ROUTE,
        VEHICLE,
        SOUND,
    )
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
