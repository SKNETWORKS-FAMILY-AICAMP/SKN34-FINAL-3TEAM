"""줄거리 종류·가족 등록표 (#634, 설계 ai.md 17.8).

종류마다 if문을 흩뿌리지 않고 이 표 하나에서 줄거리 규칙 묶음·콘티 틀·대상이 나와도 되는 컷·
흔적 특징을 꺼내 쓴다. 종류 이름(label)과 넷째 칸 이름(target_label)은 learning
`ThemeTopicSeeds.StoryType`과 같은 표다(learning이 주제 씨앗 `topic` 첫 칸에 넣음).

가족: ① 숨은 것(HIDDEN, 후보는 장소) — LOST·TREASURE, ③ 동물 주인공(ANIMAL, 후보는 동물) —
PRANK·FOOTPRINT. ②④⑤는 1차 실측을 통과한 뒤 이 표에 칸을 채우고 learning 씨앗을 더해 켠다.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

StoryTypeCode = Literal["LOST", "TREASURE", "PRANK", "FOOTPRINT"]
FamilyCode = Literal["HIDDEN", "ANIMAL"]

# 종료 콘티 1컷(단서 정리)은 모든 종류가 같다
OUTRO_THINK = "뭉치가 바닥·탁자에 놓인 단서들 앞에서 생각을 정리함"
INTRO_GO = "뭉치 출동(테마 차림의 뭉치가 혼자 화면 안에서 옆으로 통통 튀어 감)"
INTRO_ARRIVE = "현장 도착(뭉치와 인물들이 모여 큰 질문을 마주함)"


@dataclass(frozen=True)
class StoryType:
    code: StoryTypeCode
    label: str  # learning 씨앗 첫 칸(`줄거리: <label>`)
    target_label: str  # learning 씨앗 넷째 칸 이름(찾는 대상 / 밝힐 것)
    family: FamilyCode
    candidate_kind: str  # 후보 범주(장소·동물)
    intro_cuts: tuple[str, str, str, str]
    outro_cuts: tuple[str, str, str, str]
    target_cuts: frozenset[tuple[str, int]]  # 찾는 대상(③은 정답 동물)이 나와도 되는 컷
    outro_rule: str  # 종료 이야기 마무리 장면(outroStory)
    rules: str  # 줄거리 프롬프트에 붙이는 종류 규칙(plan_user)

    @property
    def animal(self) -> bool:
        return self.family == "ANIMAL"


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

# 동물 사실표(#634 1차 작은 실측: 모델이 지은 동물 특징이 틀려 글 검토 CLUE_LOGIC 7번 중 6번 —
# 너구리 고리무늬 꼬리·고양이 앞발가락 4개·까치 발가락 3개, '다니는 때'처럼 하나로 안 정해지는
# 특징 — 줄거리를 되풀이하다 마감 실패). 증거 배정처럼 코드가 정한다: 후보·특징은 이 표 안에서
# 고르고 값은 코드가 표 값으로 맞춘다(checks.apply_animal_facts). 기준안 — 초등학생이 상식으로
# 받아들이는 것만(고양이는 걸을 때 발톱을 숨겨 발바닥 자국만 남음). 같은 특징의 값끼리는 한쪽이
# 다른 쪽에 들어가지 않게 짓는다('털'은 '깃털'에 들어 있어 '부드러운 털')
ANIMAL_FEATURES = ("몸을 덮은 것", "발자국 발 수", "발자국의 발톱", "꼬리 모양")
ANIMAL_FACTS: dict[str, tuple[str, str, str, str]] = {
    "고양이": ("부드러운 털", "네 발", "발바닥 자국", "가는 꼬리"),
    "너구리": ("부드러운 털", "네 발", "발톱 자국", "굵은 꼬리"),
    "다람쥐": ("부드러운 털", "네 발", "발톱 자국", "복슬 꼬리"),
    "고슴도치": ("뾰족한 가시", "네 발", "발톱 자국", "짧은 꼬리"),
    "쥐": ("부드러운 털", "네 발", "발톱 자국", "맨 꼬리"),
    "까치": ("깃털", "두 발", "발톱 자국", "긴 꽁지"),
    "비둘기": ("깃털", "두 발", "발톱 자국", "넓은 꽁지"),
    "참새": ("깃털", "두 발", "발톱 자국", "짧은 꽁지"),
    "오리": ("깃털", "두 발", "물갈퀴 자국", "뭉툭한 꽁지"),
}


def animal_fact(animal: str, feature: str) -> str | None:
    """사실표 값. 표 밖 동물·특징이면 None."""
    row = ANIMAL_FACTS.get(animal.strip())
    if row is None or feature not in ANIMAL_FEATURES:
        return None
    return row[ANIMAL_FEATURES.index(feature)]


def animal_table_text() -> str:
    head = " | ".join(["동물", *ANIMAL_FEATURES])
    rows = [" | ".join([a, *v]) for a, v in ANIMAL_FACTS.items()]
    return "\n".join([f"  {head}", *(f"  {r}" for r in rows)])


ANIMAL_COMMON = (
    "- target은 주제의 '밝힐 것' 글을 그대로 쓴다(정답 동물 이름을 쓰지 않음, 코드 검사 "
    "TARGET_NAMES). 사건을 알아챈 아이(학생 또래)가 등장인물 중 한 명이다. 후보 동물의 주인은 "
    "등장하지 않는다.\n"
    "- incident: 사건 물건·일 한 줄(예: '떡 접시가 비어 있고 떡 부스러기가 흩어짐'). 엔딩 전에 "
    "보여도 되는 사실이고 그 주 문제의 소재가 된다. 동물 이름을 쓰지 않는다.\n"
    "- answerLook: 정답 동물의 겉모습 한 줄(예: '귀 끝이 까맣고 꼬리가 굵은 갈색 너구리'). 종료 "
    "그림·영상에서 이 모습 그대로 그린다.\n"
    "- 큰 질문은 그 일을 한 동물을 묻는다(예: '떡을 몰래 먹은 건 누구였을까?'). candidates는 "
    "아래 동물 사실표의 동물 가운데 그 장소 둘레에서 볼 법한 4마리를 표 이름 그대로 쓴다(표 밖 "
    "동물·색 낱말·'옆집' 같은 주인 표시 없이, 코드 검사 ANIMAL_TABLE).\n"
    "- 엔딩 전 글(title·world·intro·시작 콘티·place·sceneNote·discovery·missionHook·incident·"
    "인물 모습)에는 후보 동물 이름을 쓰지 않는다(코드 검사 CANDIDATE_NAME). 엔딩 전 장면에 후보 "
    "동물을 등장시키지 않는다.\n"
    "- features는 동물 사실표의 특징 이름 가운데 2~4개를 그대로 쓰고, 후보마다 값은 표 값 그대로 "
    "쓴다(코드가 표 값으로 맞춤. 표에 없는 특징·값을 지어내지 않는다). answerLook은 표의 정답 "
    "동물 값과 맞게 쓴다.\n"
    "- 동물 사실표:\n{animal_table}\n"
    "- 단서는 관찰이다. TRACE는 그 동물이 남긴 흔적(발자국의 발 수·발톱 자국, 떨어진 털·깃털·"
    "가시), SIGHTING은 부분 목격(어두워 꼬리만 봄·뒷모습만 봄), RECORD는 부분 기록(사진에 발끝만·"
    "영상에 꼬리 그림자만)이다. TRACE 날 특징은 몸을 덮은 것·발자국 발 수·발자국의 발톱 가운데서, "
    "꼬리 모양은 목격·기록 날에 쓴다. 목격·기록이 동물 전체 모습이나 이름을 알려 주지 "
    "않는다. '고양이는 밤에 "
    "다닌다' 같은 동물 상식 문장은 단서가 아니다. TRACE 날 단서에는 '동물' 낱말을 넣어 그 "
    "동물의 흔적임을 밝힌다.\n"
    "- 동물의 습성·장난이지 범죄가 아니다. 누구를 탓하거나 도둑·범인으로 부르지 않고 잡아 "
    "가두거나 벌주지 않는다. 경찰관·소방관은 해결사 차림일 뿐 체포·조사 장면을 쓰지 않는다.\n"
    "- 시작 이야기는 아이가 사건(incident)을 알아챈 데서 시작해 테마 역할의 뭉치가 현장으로 "
    "출동해 큰 질문을 맡는 데까지.\n"
).replace("{animal_table}", animal_table_text())

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
)

STORY_TYPES: dict[str, StoryType] = {t.code: t for t in (LOST, TREASURE, PRANK, FOOTPRINT)}
BY_LABEL = {t.label: t for t in STORY_TYPES.values()}

_NEW = re.compile(r"^줄거리: (.+?) / 뭉치 역할: (.+?) / 장소: (.+?) / (찾는 대상|밝힐 것): (.+)$")
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
