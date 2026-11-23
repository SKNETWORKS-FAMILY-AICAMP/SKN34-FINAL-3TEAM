"""주간 테마 초안 코드 검사 (class-diagram 5.5 ThemeChecks, #437).

정답 논리는 줄거리가 함께 만든 후보 특징 표(features)와 요일별 단서 조건(condition)으로
계산해 판정한다. LLM 추리 이야기 생성 연구처럼 논리 구조는 기계가 확인하고, 문장이 조건을
그대로 말하는지·자연스러운지는 검토 모델이 본다(ai.md 17절). 텍스트 시험(2026-11-10)에서
실제로 터진 결함마다 검사를 둔다.

미션은 검사 분담(learning.md 21절)대로 ai 검사(REQUIRED·QUESTION_LENGTH·LEAK)에 테마 몫
(학년별 생각 열기 개수·테마 정답 유출·언어)만 더하고, 요소 code·standardCode·입력 방식
모양은 learning이 본다.

사유 문자열은 "<검사 코드> <자세히>"(요일이 있으면 "<검사 코드> <요일> …")이고
다음 시도의 피드백이 된다.
"""

import difflib
import itertools
import json
import random
import re
from typing import Any

from app.followup.leak_guard import find_text_leaks
from app.mission_draft import checks as mission_checks
from app.mission_draft.models import Draft, MissionDraftRequest
from app.theme_draft import cuts as cut_layout
from app.theme_draft.families import (
    StoryType,
    is_animal,
    kept_target,
    story_type,
    theme_branch,
    type_cuts,
)

DAYS = ("MON", "TUE", "WED", "THU", "FRI")
DAY_KO = dict(zip(DAYS, ("월", "화", "수", "목", "금"), strict=True))
# 요일 배치 기준안(에픽 #436 확인 필요). learning이 다시 검사
DAY_TYPE = {"MON": "ANALYZE", "TUE": "EVALUATE", "WED": "CREATE", "THU": "SOLVE", "FRI": "REFLECT"}

# 학년별 기준안(#437 본문)
CANDIDATES = {3: 4, 4: 4, 5: 4, 6: 4}  # 모든 학년 4개(사용자 결정 2026-11-10)
HINTS = {3: 3, 4: 2, 5: 1, 6: 1}
# 서술·논술 미션 예시 답 문장 수 상한(#782 테마 짜임, 새로 정한 값 기준안 — 확인 전. 사용자 판단
# 2026-11-19 "예시 답이 너무 어려워 초5가 풀 만한 게 아님" → 쉬운 말·짧은 예시 답, 채점 요소 개수는
# 그대로). 풀이(SOLUTION_STEPS)는 단계 형식이라 세지 않음
# #782 설계 v7(사용자 결정 2026-11-22 "예시 답은 5문장으로"): 초3·4도 5문장(3·4·5차 측정 모두
# 초3·4 '5문장(상한 4)'이 50번 안팎 걸리고 5차 미션 단계 실패 9개 중 4개)
EXAMPLE_SENTENCES = {3: 5, 4: 5, 5: 5, 6: 5}
EXAMPLE_LONG_TYPES = ("NARRATIVE", "ESSAY")
# 미션 전 대화 줄 수(#782 테마 짜임, 사용자 결정 2026-11-19 모든 학년 4~5줄. 전에는 초3·초4 3~4줄·
# 초5·초6 2~3줄에 끝 두 줄을 코드가 넣어 모델 줄이 대부분 1줄이었음)
DIALOGUE_LINES = {3: (4, 5), 4: (4, 5), 5: (4, 5), 6: (4, 5)}
LINE_MAX = 40
# 흔적 날 단서는 누구의 흔적인지(찾는 대상 낱말)를 꼭 넣어 그만큼 상한을 늘림(기준안, #535 6차 원인:
# 32자 안에서 대상 낱말이 빠져 글 검토 CLUE_LOGIC "흔적이 대상의 것인지 드러나지 않음"이 늘었음)
TRACE_CLUE_MAX = 46
# 종료 이야기 = 코드가 쓰는 다섯 단서 정리(outro_recap) + LLM이 쓰는 마무리 장면(outroStory). 정리를
# LLM이 쓰면 표와 다르게 요약해 글 검토 CLUE_LOGIC으로 줄거리부터 다시 만들었음(#535 7차 25건 중
# 5건: 허용 값 둘인 단서를 한 값 단서라고 부름, 없는 단서로 후보를 뺐다고 씀). 마무리 장면
# 상한(기준안) — 정리는 길어야 140자 안팎
OUTRO_STORY_MAX = 160
WEEKDAY_WORDS = re.compile(r"[월화수목금]요일")
# 단서 앞 그때 시각 붙이기(CLUE_TIME·add_clue_time)는 #782 테마 짜임에서 뺐다(사용자 결정
# 2026-11-19, 단서를 발견 장면 대사처럼). 붙였던 까닭은 #535 7차 글 검토 CLUE_LOGIC "흔적·기록이
# 그때의 것인지 드러나지 않음"(검사로 고쳐 쓰게 하면 7차 단서 172개 중 133개가 걸림)이라 작은
# 생성으로 다시 확인할 것
# 마지막 틀린 후보는 금요일에 빠져 그날 정답을 찾음(#782 테마 짜임, 사용자 결정 2026-11-19 "금요일에
# 찾게". 전에는 목요일 이후라 목요일에 끝나는 일이 많았음). 목요일까지 후보가 2개 이상 남음
LAST_ELIMINATION_MIN = DAYS.index("FRI")
# 글자 수 상한(기준안, 학년 공통). 단서는 한 줄 글로 보여 주고(learning이 그날 미션 완료 뒤)
# 증거 발견 줄·수사 연결 문장·오늘 온 까닭은 대화 재료라 대화 한 줄(LINE_MAX)과 같음
TEXT_MAX = {
    "title": 20,
    "incident": 60,  # #634 ③ 내부 칸(기준안)
    "answerLook": 60,
    "introPlace": 60,  # #779 컷 장소(기준안, 칸 고쳐 쓰기 상한)
    "outroPlace": 60,
    "bigQuestion": 40,
    "intro": 200,
    "outro": 300,
    "place": 20,
    "sceneNote": 150,
    "clue": LINE_MAX,
    "discovery": LINE_MAX,
    "missionHook": LINE_MAX,
    # 오늘 온 까닭(내부 칸, #782 테마 짜임 기준안): 대화 모델 재료. 대화 한 줄과 같은 상한
    "dayStep": LINE_MAX,
    # 그날 돕는 사람 호칭(#782 테마 짜임 기준안, 예: '떡집 사장님')
    "helper": 12,
    # #782 설계 v10: 국어 부탁 날 아이 답의 쓰임(내부 칸, 기준안). 그날만 보므로 DAY_TEXTS 밖
    "helperUse": LINE_MAX,
    # 그날 미션 지문이 될 증거 내용(내부 칸, #782 기준안). 미션이 question 안에 그대로 넣음
    "missionMaterial": 150,
}
DAY_TEXTS = (
    "place",
    "sceneNote",
    "clue",
    "discovery",
    "missionHook",
    "missionMaterial",
    "dayStep",
    "helper",
)
# 새 테마 시작·종료 영상 콘티 컷 수(#779 2026-11-19 6컷 × 4초). 예전 4컷(4·6·8·6초) 초안은 부분
# 다시 생성에서만 쓰이고 이 검사는 새 줄거리만 봄
CUTS = cut_layout.NEW_CUTS
CAPTION_MAX = 30  # 움직임 captions(웹이 띄움) 글자 상한(기준안). 컷 자막 상한은 cuts.CAPTION_MAX
MUNGCHI_MOODS = ("none", "smile", "surprised", "determined")
# 콘티 scene·action을 칸 하나만 고쳐 쓸 때 알려 주는 글자 상한(기준안, 길이 검사는 하지 않음)
CUT_TEXT_MAX = 80
# 뭉치는 팔이 없어(아래쪽 작은 손만) 손·팔다리를 쓰는 동작을 영상으로 만들면 팔·다리가 새로 생긴다.
# 실측 2026-11-11(auto4·auto5b·auto4d 뭉치 컷 12개 중 9개가 짚기·손 들기·건네기·가리키기·모으기,
# 그런 컷과 뛰는 컷에서 영상 검토 CONTINUITY·MORPH 실패). 낱말은 다른 뜻과 겹치지 않는 꼴만 둔다
# (손전등·놓인·모은 단서 같은 말은 걸리지 않게). '모으·모아·모은다'는 '다섯 흔적을 모아'·
# '단서를 모아 보자'처럼 손 동작이 아닌 말에 걸려 뺌(#535 7차: 종료 1컷 CUT_ACTION 5번, 초4
# auto4가 이 사유로 다시 생성하다 마감 실패). 손으로 모으는 말은 '손을·두 손'으로 잡힘
# #779(실측 2026-11-18): 제자리 통통 튀기도 영상에서 갈색 발이 흰 다리로 바뀌어 뭉치 동작에서 뺌
# (뭉치는 표정·고개 갸웃·몸 살짝 흔들기만). 달리는 컷(cuts.CutSpec who RUN)만 달리기를 허용
# (MUNGCHI_RUN_WORDS)
MUNGCHI_HAND_WORDS = tuple(
    (
        "손을|손으로|손가락|두 손|한 손|양손|손뼉|박수|만세|팔을|양팔|"
        "가리키며|가리키고|가리킨다|가리켜|짚는|짚고|짚어|짚으|건네|건넨|안아|안고|안는|껴안|"
        "놓는|놓고|놓아|내려놓|들어 올|들어올|집어|줍|쥐고|쥔다|뛰|점프|달리|달려|달린|"
        "통통|튀어|튀고|튀며|튄다|튀는|깡충|"
        # #634 동물 주인공: 뭉치가 동물을 붙잡는 꼴(붙잡는 건 중립 인물)
        "잡아|잡고|잡는|붙잡"
    ).split("|")
)
# 출동 컷(시작 3)에서만 뭉치에게 허용하는 달리기 낱말. 화면 쪽으로 달려오는 말은
# APPROACH_WORDS가 막음
MUNGCHI_RUN_WORDS = ("뛰", "달리", "달려", "달린")
# …이·…가로 끝나도 주어가 아닌 낱말(콘티 마디의 주어를 가를 때)
NOT_SUBJECT = tuple("같이 많이 높이 깊이 길이 가까이 바닷가 물가 강가 길가 냇가 창가".split())
# 화면 쪽으로 다가오거나 화면 밖으로 나가면 확대돼 몸이 잘리거나 인물이 사라진다(비교 시험
# 2026-11-11: "화면 쪽으로 다가온다" 컷에서 빠른 모델이 확대해 뭉치 발이 잘림)
# #779: '들어간'은 뺌. 카메라가 뒤에서 따라가며 문 안으로 걸어 들어가는 컷이 이야기 이동을 보여
# 주는 연출이라(만화 연출 시제품 2026-11-18), 인물이 사라지는 것은 영상 검토 CONTINUITY가 봄
APPROACH_WORDS = tuple("다가오|다가온|달려오|달려온|걸어오|걸어온|화면 밖|밖으로".split("|"))
# 사람도 공중 손짓(손뼉·손 흔들기·만세)은 쓰지 않음(#779 사용자 결정 2026-11-19). 줄거리 지시로만
# 막고 코드 검사가 없어, 글 모델이 쓰면 그림 지시엔 손뼉·영상 금지 목록엔 clapping이 함께 들어갔음
# (재검토 2026-11-20, 시험 데이터 "지호가 손뼉을 치며 폴짝 뛴다"가 통과). 종류 역할 글의 "손뼉 없이"
# 같은 부정은 걸지 않음(AIR_HAND_NOT)
AIR_HAND_WORDS = ("손뼉", "박수", "손을 흔", "손 흔들", "만세")
AIR_HAND_NOT = ("손뼉 없이", "박수 없이")
# 컷마다 뭉치가 나오는지·달리기를 허용하는지는 컷 틀(cuts.LAYOUTS, #779)
CANDIDATE_CHARS = (2, 10)
FEATURES = (2, 5)
CHARACTERS = (1, 3)
EVIDENCE_KINDS = ("TRACE", "SIGHTING", "RECORD")
EVIDENCE_KO = {"TRACE": "흔적", "SIGHTING": "목격", "RECORD": "기록"}
# 흔적(TRACE)으로 남을 수 있는 특징(기준안, #535 6차): 대상이 닿거나 지나간 자리의 바닥·면·
# 모양·크기·무게처럼 자국에 남는 것. 빛·그늘·소리·냄새·바람·거리·때·주변 색·풍경은 흔적에 남지
# 않아 흔적 날이면 글 검토 CLUE_LOGIC("'그늘'은 빛의 종류가 아님", 받침 재질 vs 자국 재질)이
# 늘었음(6차 원인 분석, 17.6.8)
TRACE_FEATURE = re.compile(
    r"바닥|땅|흙|모래|재질|재료|물기|젖|마른|무늬|모양|타일|매트|깔개|받침|놓인|면|지름|너비|폭|"
    r"크기|무게|자국|표면"
)
NOT_TRACE_FEATURE = re.compile(
    r"빛|햇|그늘|밝|조명|소리|냄새|바람|거리|시각|시간|꽃|풍경|시설|하늘|벽 색"
)
# 요일별 증거 종류·기록 매체 코드 배정(#535). 모델이 고르게 두면 기록이 단서 100개 중 49~53개로 쏠려
# (실측 2026-11-11, 예시를 빼도 줄지 않음) 이름·주제 씨앗처럼 코드가 정한다. 구성은 흔적·목격 각
# 1개 이상, 기록 2개 이하(기준안, 세 구성 평균이면 종류마다 1.67개)
EVIDENCE_MIXES = (
    ("TRACE", "TRACE", "SIGHTING", "SIGHTING", "RECORD"),
    ("TRACE", "SIGHTING", "SIGHTING", "RECORD", "RECORD"),
    ("TRACE", "TRACE", "SIGHTING", "RECORD", "RECORD"),
)
RECORD_MEDIA = ("사진", "영상", "메모", "일지", "녹음")
# 매체 낱말이 단서·증거 발견 줄에 있는지 볼 때 같은 매체로 보는 말
MEDIUM_WORDS = {
    "사진": ("사진",),
    "영상": ("영상", "녹화"),
    "메모": ("메모",),
    "일지": ("일지",),
    "녹음": ("녹음",),
}
CLUE_TYPES = (
    "목격",
    "기록",
    "시각",
    "잠김",
    "소리",
    "색",
    "냄새",
    "재질",
    "무게",
    "습성",
    "발자국",
    "온도",
    "물기",
    "크기",
)
# #782 설계 v13: HELPER_FIT(부탁 날 돕는 사람의 일이 그 장소에 맞고 아이 답이 쓰이는지)
REVIEW_IDS = (
    "CLUE_LOGIC",
    "ANSWER_HINT",
    "GRADE_VOCAB",
    "STANDARD_FIT",
    "HELPER_FIT",
    "SAFETY",
)
# STORY_LINK: 문제 소재가 수사 연결 문장·오늘 장소·찾은 증거에서 왔는지(#535, 기준안)
MISSION_REVIEW_IDS = ("EXAMPLE_COMPLETE", "STANDARD_FIT", "MATERIAL", "STORY_LINK")

COLOR = re.compile(
    r"빨간|빨강|파란|파랑|노란|노랑|초록|하얀|하양|흰|검은|검정|까만|분홍|주황|보라|갈색|회색|푸른|붉은"
)
FOREIGN = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")  # 가나·한자(일본어로 샌 사례)
# 나머지는 검토 모델. #634 경찰관 역할·동물 장난꾸러기: 체포·수갑·연행·처벌·훔치기·범인(사용자 결정
# 2026-11-16 '범인' 넣음), '도둑'은 '도둑고양이'·'도둑게'·'도둑갈매기'(동물 이름)만 통과
UNSAFE = re.compile(
    r"살인|납치|유괴|폭력|담배|흉기|피투성이|자살|체포|수갑|연행|처벌|훔치|훔쳐|훔친|범인|"
    r"귀신|괴물|유령|"  # #634 ⑤ 밤 소리 이야기가 무서워지지 않게
    r"도둑(?!고양이|게|갈매기)"
)
SPEAKER_PREFIX = re.compile(r"\s*[가-힣A-Za-z]{1,6}\s*:")
NOMINAL_ENDINGS = "음함림름움색"  # 표 값의 명사형 끝(좁음·열림…). 문장에서는 좁았어·열린처럼 활용

Theme = dict[str, Any]  # GeneratedTheme.model_dump() 모양(camelCase)


def compact(text: str | None) -> str:
    return re.sub(r"\s", "", text or "")


def overlaps(a: str | None, b: str | None, n: int) -> bool:
    """a와 b가 공백 뺀 n자 이상 겹치는지."""
    a, b = compact(a), compact(b)
    return len(a) >= n and any(a[i : i + n] in b for i in range(len(a) - n + 1))


def value_in_text(value: str, text: str | None) -> bool:
    """표 값이 단서 문장에 있는지. 활용형(좁음→좁았어)·숫자 표기(2:3→2대3)는 같게 본다."""
    v = compact(value).replace(":", "대")
    c = compact(text).replace(":", "대")
    if v in c:
        return True
    # 값이 '물가 아님'처럼 '…아님'이면 '물가가 아니었어'도 같은 값(40개 측정 r782-final40 오탐)
    if v.endswith("아님") and len(v) > 2 and re.search(re.escape(v[:-2]) + r"\S{0,2}아니", c):
        return True
    return len(v) >= 2 and v[-1] in NOMINAL_ENDINGS and v[:-1] in c


def mentions_value(value: str, text: str | None) -> bool:
    """단서 결론(허용 값)을 미리 말하는지(CLUE_EARLY). 증거 발견 줄·수사 연결 문장·대화 줄에 쓴다.

    정확히 일치하거나, 명사형 끝을 뗀 줄기가 2자 이상일 때만 줄기 일치로 본다. value_in_text와
    달리 1자 줄기(좁음→좁, 젖음→젖)는 보지 않는다: 이 검사는 잡으면 다시 만들게 하므로 오탐이 많은
    1자 줄기를 뺀다(사용자 결정 2026-11-11).
    """
    v = compact(value).replace(":", "대")
    c = compact(text).replace(":", "대")
    if not v:
        return False
    if len(v) == 1:
        # 한 글자 값은 낱말 첫머리에 올 때만 본다('흙탕물'의 '흙'은 잡고, 값 '게'가 '설명해 볼게'의
        # 끝말에 걸리던 오탐은 뺌. 실측 2026-11-15 닫기 3c 대화 CLUE_EARLY 1번)
        return (
            re.search(rf"(?<![가-힣]){re.escape(v)}", (text or "").replace(":", "대")) is not None
        )
    if v in c:
        return True
    stem = v[:-1]
    return v[-1] in NOMINAL_ENDINGS and len(stem) >= 2 and stem in c


# 빠지는 값을 부정으로 말하는 단서(#782, 사용자 2026-11-20 "단서도"): 허용 값이 셋 이상이면 단서가
# 'A나 B나 C였어'로 늘어놓게 됨(저장된 특징 단서 1,156개 중 158개, 14%). 빠지는 값이 한두 개면
# '나무는 아니었어'처럼 말해도 됨. 코드가 빠지는 값(condition 내부 칸 excluded)을 매기고, 그 값과
# 부정 말이 단서에 있으면 부정형으로 봄
# #782 설계 v8: 부정형은 '본 것이 그 값이 아니었다'('바닥은 나무는 아니었어')만. '나무는
# 없었어·묻지 않았어·안 보였어'처럼 본 것 없이 없었다고만 하면 글 검토가 "찾지 못한 것만으로 뺌"
# 으로 잡음(3·4·5차 글 검토 CLUE_LOGIC 87번 중 47번) → CLUE_TEXT로 다시 씀
NEG_WORDS = re.compile(r"아니")
ABSENT_FORM = re.compile(r"없|않|(?<![가-힣])안\s|못\s?(?:봤|들|찾|보)")
# #782 설계 v3(사용자 결정 2026-11-21): 허용 값이 둘 이상이면 늘 부정형. 전에는 셋부터라 둘이면
# '흙이나 나무였어'처럼 늘어놓게 했고, 직접 본 사람이 둘 중 하나라고 말해 어색했음(2차 측정 통과
# 31개 읽기 'A나 B' 14건, 지시문 '모래나 나무처럼 나로 이어'가 시킨 것)
NEG_MIN_ALLOWED, NEG_MAX_EXCLUDED = 2, 2  # 기준안


def negative_form(day: dict) -> bool:
    """그날 단서가 빠지는 값을 부정으로 말하는 꼴인지('바닥은 나무는 아니었어')."""
    excluded = (day.get("condition") or {}).get("excluded") or []
    clue = day.get("clue")
    return (
        bool(excluded)
        and bool(NEG_WORDS.search(str(clue or "")))
        and all(value_in_text(e, clue) for e in excluded)
    )


def clue_says(day: dict) -> list[str]:
    """그날 단서가 알려 주는 값 낱말: 부정형이면 빠지는 값, 아니면 허용 값."""
    cond = day.get("condition") or {}
    return (
        list(cond.get("excluded") or []) if negative_form(day) else list(cond.get("allowed") or [])
    )


# #782 설계 v3(사용자 결정 2026-11-21): 부탁 날 단서는 돕는 사람이 자기가 본 것·가진 기록을
# 직접 말한다. 2차 측정 통과 31개를 읽으니 약속은 "그때 본 걸 알려 줄게"인데 단서가 "~였대" 전해
# 들은 말(부탁 날 147개 중 32개)이거나 흔적만 말하고 그 사람과 연결이 없었음(결함 66건, 가장 많음).
# 전해 들은 말투는 종류 규칙 예시('보였대'·'났대')에서 왔음
HEARSAY_END = re.compile(
    r"(?:었|았|였|했|봤|났|렸|갔|왔|섰|졌|됐|웠|켰|맸|겼|쳤|있|없|이)(?:대|래)요?[!.~]*$|더라"
)
TRACE_LINK = re.compile(r"내가|제가|봤|보았|보니|살펴")
# #782 설계 v4(사용자 결정 2026-11-22): 3차 측정 치명 결함 — "내 일지 보여 줄게" 뒤 남의 일지
# ("받은 뒤 쓴 일지에는"), "내가 본 흔적은 흔들면 흙 소리"(소리는 본 것이 아님)
SENSE_WORDS = (
    ("소리", "흔들어 보니"),
    ("냄새", "맡아 보니"),
    ("향", "맡아 보니"),
    ("맛", "맛보니"),
)
# #782 설계 v4: "관리인이 들은 소리는 …였대"·"윤슬이 들은 소리는"(윤슬은 주인공)처럼 다른 사람이
# 듣거나 본 것. 끝말만 직접 말로 바꾸면 남의 말이 그대로 남아, 다듬지 않고 CLUE_SOURCE로 다시
# 쓰게 함
OTHER_SOURCE = re.compile(r"(?<![가-힣])([가-힣]+)(?:이|가) (?:들은|본|봤|찍은|적은|목격한)")
SENSE_SEEN = re.compile(r"(?<![가-힣])본\s|봤")


def clue_source_problems(theme: Theme, day: dict) -> list[str]:
    """부탁 날 단서가 돕는 사람이 본 것·가진 기록인지(CLUE_SOURCE, 그 단서만 고쳐 씀). 수사 날
    기록 단서는 기록을 따져 확실해진 사실인지(#782 설계 v9)."""
    clue = str(day.get("clue") or "").strip()
    if mission_way(day) != ASK:
        # #782 설계 v9: 수사 날 지문이 그 기록이라 단서가 '메모에는 ~라고 적혀 있어'로 옮기면
        # 지문에 없는 말이 기록에 있다고 하게 됨(5·6차 snd3 수 — 기록 수사 날 7일 중 2일)
        # 미션 방식이 없는 예전 저장본은 보지 않음(그때는 '일지에 ~ 적혀 있어'가 기록 단서 꼴)
        if (
            day.get("missionWay") == INVESTIGATE
            and (day.get("evidence") or {}).get("kind") == "RECORD"
            and RECORD_QUOTE.search(clue)
        ):
            return [
                "수사 날인데 기록에 적힌 말을 옮김 — 지문이 그 기록이라 기록을 따져 확실해진 "
                "사실로 씀('메모를 따져 보니 ~')"
            ]
        return []
    bad = []
    if HEARSAY_END.search(clue):
        bad.append(
            "전해 들은 말 끝(~대·~래·~더라) — 돕는 사람이 자기가 본 것·가진 기록을 직접 말함"
            "('그때 내가 봤어', '내 사진에 ~가 찍혀 있어')"
        )
    if other := other_source(clue):
        bad.append(
            f"다른 사람('{other}')이 듣거나 본 것 — 돕는 사람이 자기가 본 것·가진 기록을 직접 말함"
        )
    kind = (day.get("evidence") or {}).get("kind")
    if kind == "TRACE" and not TRACE_LINK.search(clue):
        bad.append(
            "흔적 날인데 돕는 사람이 본 흔적이라는 말이 없음('내가 창고 앞에서 본 발자국은 ~'처럼)"
        )
    if kind == "TRACE" and sense_of(clue) and SENSE_SEEN.search(clue):
        bad.append(
            f"흔적 날 {sense_of(clue)[0]}{josa(sense_of(clue)[0], '은', '는')} 눈으로 본 것이 "
            f"아님('내가 {sense_of(clue)[1]} ~'처럼 "
            "그렇게 해서 안 것으로)"
        )
    medium = (plan_slot(theme, day.get("day") or "") or {}).get("medium")
    if kind == "RECORD" and medium and not own_record(clue, medium):
        bad.append(
            f"기록 날인데 돕는 사람 자신의 기록이 아님('내 {medium}에 ~'처럼 — 약속은 '도와주면 내 "
            f"{medium}{josa(medium, '을', '를')} 보여 줄게')"
        )
    return bad


RECORD_QUOTE = re.compile(
    r"(?:메모|일지|수첩|기록|녹음|사진|영상)(?:에는|엔|에)\s?.{0,40}(?:적혀|찍혀|녹음돼|담겨|쓰여)"
)
OWN_MADE = re.compile(r"(?:내가|제가) (?:찍은|쓴|적은|가진|남긴|녹음한|찍어 둔|적어 둔)")


def own_record(clue: str, medium: str) -> bool:
    """기록 단서가 돕는 사람 자신의 기록인지(#782 설계 v4): '내 일지'·'내가 찍은 영상'·'메모에
    적었어'(말하는 사람이 적음). '받은 뒤 쓴 일지'·'준비 영상'처럼 누구 것인지 없으면 아님."""
    return bool(
        re.search(rf"(?<![가-힣])(?:내|제)\s?{medium}", clue)
        or OWN_MADE.search(clue)
        or re.search(rf"{medium}에\s?(?:적었|썼|남겼|찍었|담았|녹음했)", clue)
    )


def other_source(clue: str) -> str | None:
    """단서가 말하는 사람이 아닌 다른 사람이 듣거나 본 것이면 그 사람(#782 설계 v4). 없으면 None."""
    m = OTHER_SOURCE.search(clue)
    return m.group(1) if m and m.group(1) not in ("내", "제", "우리") else None


# #782 설계 v8: '향'은 '향해·향한·방향·영향'이 아닐 때만("발자국이 창고 쪽을 향해"가 냄새로 잡혀
# '내가 맡아 보니'가 붙었음)
SENSE_PATTERN = {"향": re.compile(r"(?<![방지영])향(?![해한하했])")}


def sense_of(text: str) -> tuple[str, str] | None:
    """흔적 단서가 말하는 감각(소리·냄새·맛)과 그것을 안 방법 말. 없으면 None."""
    return next(
        (
            (w, how)
            for w, how in SENSE_WORDS
            if (SENSE_PATTERN[w].search(text) if w in SENSE_PATTERN else w in text)
        ),
        None,
    )


def normalize_clue_source(theme: Theme) -> Theme:
    """부탁 날 단서의 출처 말을 코드가 먼저 다듬는다(#782 설계 v4, 모델 호출 없음, 제자리).

    전해 들은 말 끝 → 직접 말('멎었대!' → '멎었어!'), 기록 날 매체 낱말로 시작하면 앞에 '내 ',
    흔적 날 돕는 사람 연결이 없으면 앞에 '내가 보니 '(소리·냄새·맛이면 '내가 흔들어 보니 ' 등).
    글자 수 상한을 넘으면 그 다듬기는 하지 않는다(CLUE_SOURCE가 잡아 고쳐 쓰기). 이미 다듬은 글은
    그대로라 여러 번 불러도 같다. 줄거리·칸 고쳐 쓰기·단서만 고쳐 쓰기 뒤마다 finalize_texts가
    부름."""
    for d in theme.get("days") or []:
        if not isinstance(d, dict) or mission_way(d) != ASK or not d.get("clue"):
            continue
        text = str(d["clue"]).strip()
        limit = day_text_max(d, "clue", theme)
        if other_source(text):  # 남이 들은·본 것은 끝말만 바꾸지 않음(CLUE_SOURCE가 다시 쓰게)
            continue
        for pattern, repl in HEARSAY_FIX:
            text = pattern.sub(repl, text)
        kind = (d.get("evidence") or {}).get("kind")
        medium = (plan_slot(theme, d.get("day") or "") or {}).get("medium")
        if kind == "RECORD" and medium and text.startswith(medium) and len(text) + 2 <= limit:
            text = f"내 {text}"
        # #782 설계 v6: 맡겨 둔 대상 자체의 흔적은 맡겨지기 전에 본 것(KEPT_TRACE). v7: '맡기기
        # 전에'는 말한 사람이 맡긴 사람이 되어 다른 날 맡긴 사람과 부딪혀(5차 hand6b)
        # '맡겨지기 전에'
        before = object_self_trace(theme, d) and not KEPT_TRACE_WHEN.search(text)
        if kind == "TRACE" and not TRACE_LINK.search(text):
            sense = sense_of(text)
            lead = f"내가 {sense[1]} " if sense else "내가 보니 "
            lead = f"맡겨지기 전에 {lead}" if before else lead
            if len(lead + text) <= limit:
                text = lead + text
        elif before and text.startswith(("내가 ", "제가 ")) and len(text) + 8 <= limit:
            text = f"맡겨지기 전에 {text}"
        d["clue"] = text
    return theme


def _final(word: str) -> int:
    """끝 글자 받침 번호(0이면 받침 없음, 한글이 아니면 0)."""
    last = (word or " ")[-1]
    return (ord(last) - 0xAC00) % 28 if "가" <= last <= "힣" else 0


def josa(word: str, with_final: str, without: str) -> str:
    return with_final if _final(word) else without


def josa_ro(word: str) -> str:
    """'으로'·'로'(받침 없거나 ㄹ이면 '로')."""
    return "로" if _final(word) in (0, 8) else "으로"


HEARSAY_FIX = (
    (
        re.compile(
            r"(었|았|였|했|봤|났|렸|갔|왔|섰|졌|됐|웠|켰|맸|겼|쳤|있|없)(?:대|래)요?([!.~]*)$"
        ),
        r"\g<1>어\g<2>",
    ),
    (re.compile(r"이(?:대|래)요?([!.~]*)$"), r"이야\g<1>"),
    (re.compile(r"더라([!.~]*)$"), r"어\g<1>"),
)


def story_clue_template(theme: Theme, day: dict) -> str | None:
    """부탁 날 사건 단서의 출처만 코드가 고친 문장: 전해 들은 말 끝을 직접 말로('멎었대!' →
    '멎었어!'), 흔적 날에 돕는 사람과 연결이 없으면 '내가 보니'를 앞에. 내용은 모델 글 그대로."""
    text = str(day.get("clue") or "").strip()
    for pattern, repl in HEARSAY_FIX:
        text = pattern.sub(repl, text)
    if (day.get("evidence") or {}).get("kind") == "TRACE" and not TRACE_LINK.search(text):
        sense = sense_of(text)
        text = f"내가 {sense[1]} {text}" if sense else f"내가 보니 {text}"
    return text if text != str(day.get("clue") or "").strip() else None


def clue_template(theme: Theme, day: dict) -> str | None:
    """단서를 코드가 쓰는 틀 문장(#782 설계 v3): CLUE_SOURCE·CLUE_TEXT를 두 번 고쳐 써도 걸릴 때.

    꼴은 조건대로(값 하나는 그대로, 둘 이상은 빠지는 값을 부정으로), 부탁 날 출처는 증거 종류대로
    (목격 '내가 봤어', 기록 '내 {매체}에', 흔적 '내가 본 ~ 흔적'), 수사 날은 '증거를 따져 보니'.
    찾는 대상 낱말(CLUE_OWNER)·소리 낱말·배정 매체 낱말·산 근거 말과 산 물건(CLUE_PROOF)이 늘
    들어가고, 글자 수 상한 안에서 가장 긴 꼴을 고른다. 부탁 날 사건 단서는 출처만 고친다
    (story_clue_template). 고칠 것이 없으면 None."""
    cond = day.get("condition") or {}
    way = mission_way(day)
    if is_story(cond):
        return story_clue_template(theme, day) if way == ASK else None
    feature = str(cond.get("feature") or "").strip()
    allowed = [str(a) for a in cond.get("allowed") or []]
    excluded = [str(e) for e in cond.get("excluded") or []]

    def said(quote: str) -> str | None:
        def q(v: str) -> str:
            return f"{quote}{v}{quote}"

        if len(allowed) == 1:
            v = allowed[0]
            return f"{q(v)}{josa(v, '이었', '였')}어!"
        if excluded:
            last = excluded[-1]
            return "도 ".join(q(e) for e in excluded) + (
                "도 아니었어!" if len(excluded) > 1 else f"{josa(last, '이', '가')} 아니었어!"
            )
        return None

    quoted, plain = said("'"), said("")
    if quoted is None or plain is None:
        return None
    topic = f"{feature}{josa(feature, '은', '는')} " if feature else ""
    # 무엇에 대한 단서인지(특징 이름)를 먼저 지키고, 넘치면 따옴표를 빼고, 그래도 넘치면 특징
    # 이름을 뺌
    cores = [topic + quoted, topic + plain, quoted, plain] if feature else [quoted, plain]
    words = [] if story_type(theme).hide_times else target_words(theme)  # 시각 종류는 '때'뿐
    subj = clue_person(theme) or (words[0] if words else "")
    kind = (day.get("evidence") or {}).get("kind")
    medium = (plan_slot(theme, day.get("day") or "") or {}).get("medium") or "기록"
    seen = "들었" if subj == "소리" else "봤"
    ga, obj = josa(subj, "이", "가"), josa(subj, "을", "를")
    # 대상 낱말이 특징 이름에 이미 있으면(소리 탐정 '소리 난 곳') 앞말에서 빼도 CLUE_OWNER를 지킴
    bare = bool(subj) and subj in feature
    kept_verb = {"사진": "찍혀", "영상": "찍혀", "녹음": "담겨"}.get(medium, "적혀")
    if way != ASK:  # 수사 날: 따져서 확실해진 사실(기록 날은 배정 매체 낱말)
        what = f"{medium}{josa(medium, '을', '를')} " if kind == "RECORD" else "증거를 "
        leads = [f"{subj} {what}따져 보니 " if subj and not bare else f"{what}따져 보니 "]
        if feature in PROOF_FEATURES:  # #782 설계 v8: 산 가게는 산 근거 말(CLUE_PROOF)
            thing = PROOF_FEATURES[feature]
            leads = [f"{thing}{josa(thing, '을', '를')} 계산한 {what}따져 보니 "]
    elif feature in PROOF_FEATURES:  # 산 가게: 산 근거 말(계산)과 산 물건 낱말을 늘 넣음
        thing = PROOF_FEATURES[feature]
        leads = (
            [
                f"내 {medium}에 {thing}을 계산한 곳이 {kept_verb} 있어. ",
                f"내 {medium} 속 {thing} 계산, ",
            ]
            if kind == "RECORD"
            else [f"그때 내가 {thing}을 계산하는 걸 봤어. ", f"내가 {thing} 계산을 봤어. "]
        )
    elif kind == "RECORD":
        about = f"{subj}{ga} {kept_verb} 있어. " if subj else f"{kept_verb} 있어. "
        leads = [
            f"내 {medium}에 {about}",
            *([f"내 {medium} 속 {subj}, "] if subj else []),
            f"내 {medium}엔 ",
        ]
    elif kind == "TRACE":
        # #782 설계 v6 KEPT_TRACE(v7 맡겨지기 전). v8: 소리·맛·냄새 특징은 본 것이 아니라 그렇게
        # 해서 안 것(CLUE_SOURCE — 전에는 틀 문장이 '내가 본 ~ 흔적'이라 늘 걸림)
        seen = "맡겨지기 전 내가 본" if kept_target(theme) else "내가 본"
        if sense := sense_of(feature):
            pre = "맡겨지기 전에 " if kept_target(theme) else ""
            how = f"{pre}내가 {sense[1]}"
        leads = [f"{seen} {subj} 흔적, " if subj else f"{seen} 흔적, "]
        if sense:
            leads = [f"{how} {subj} " if subj else f"{how} "]
    else:
        leads = (
            [f"그때 내가 {subj}{obj} {seen}어. ", f"내가 {subj}{obj} {seen}어. "]
            if subj
            else ["그때 내가 봤어. "]
        ) + ([f"내가 {seen}어. "] if bare or not subj else [])
    limit = day_text_max(day, "clue", theme)
    # 대상 낱말이 필요한 단서(CLUE_OWNER: 흔적 날·출처·길·소리·탈것)는 앞말이든 특징 이름이든
    # 어딘가에 늘 남김
    owner = kind == "TRACE" or story_type(theme).owner_all or bool(clue_person(theme))
    every = [lead + core for core in cores for lead in leads]
    options = [t for t in every if not (owner and subj) or subj in t] or every
    return next((t for t in options if len(t) <= limit), options[-1])


def mark_excluded(theme: Theme) -> Theme:
    """부정형으로 말할 수 있는 요일 condition에 빠지는 값(excluded)을 매긴다(제자리, 내부 칸)."""
    table, _ = feature_table(theme)
    for d in theme.get("days") or []:
        cond = d.get("condition")
        if not isinstance(cond, dict):
            continue
        values = set((table.get(cond.get("feature")) or {}).values())
        allowed = set(cond.get("allowed") or [])
        excluded = sorted(values - allowed)
        if (
            cond.get("kind") in ("RULE", "HINT")
            and len(allowed) >= NEG_MIN_ALLOWED
            and 1 <= len(excluded) <= NEG_MAX_EXCLUDED
        ):
            cond["excluded"] = excluded
        else:
            cond.pop("excluded", None)
    return theme


def early_values(day: dict, text: str | None) -> list[str]:
    """그날 단서가 알려 주는 값(clue_says) 중 text가 미리 말하는 값."""
    return [a for a in clue_says(day) if mentions_value(a, text)]


def prev_values(theme: Theme, day: str, text: str | None) -> list[str]:
    """앞 요일 단서 허용 값 중 text가 말하는 값(그날 허용 값과 같은 값은 뺌 — early_values가 봄).

    #782 테마 짜임(사용자 결정 2026-11-19 "어제 한 일만 잇기"): 문제는 순서 없이 토요일까지 몰아서
    풀 수 있어 앞 요일 단서를 아직 못 얻은 학생이 있다. 오늘 대화·오늘 온 까닭은 어제 한 일만
    이어받고 단서 결과는 말하지 않는다."""
    days = theme.get("days") or []
    names = [d.get("day") for d in days]
    if day not in names:
        return []
    own = set(clue_says(theme_day(theme, day)))
    before = [a for d in days[: names.index(day)] for a in clue_says(d) if a and a not in own]
    return [a for a in dict.fromkeys(before) if mentions_value(a, text)]


# 학생이 글로 할 수 없는 활동을 그 이름으로 시키는 말(ACT_NAME, #782 사용자 결정 2026-11-19).
# 글로 대신하는 방식(TEXT_ONLY, 사용자 결정 2026-11-11)은 그대로 두고 이름만 막는다. 저장된 실측
# 미션 5,780개 중 409개(7.1%)가 '발표 글을 써 봐'·'목소리·몸짓을 괄호에'·'컴퍼스로 그리는 순서를
# 글로'·'끊어 읽기 표시'처럼 시켰고, 발표와 상관없는 읽기 습관·감상 태도 성취기준에서도 '발표 글'을
# 지어냈다. 자료로 나온 말(면담 기록, 검색 결과)은 막지 않고 시키는 말만 본다. '검색어 만들기'는
# 6국06-01의 생각 부분이라 막지 않는다
ACT_NAMES = {
    "발표": re.compile(
        r"발표\s*(?:글|문|자료|할\s*(?:글|말|내용))|발표(?:해|하)\s*(?:보|봐|자|기|려|볼)"
    ),
    "목소리·몸짓 넣어 쓰기": re.compile(
        r"(?:목소리|몸짓|손짓|표정)[^.?!\n]{0,20}(?:괄호|넣어\s*(?:써|쓰))"
    ),
    "그리기": re.compile(
        r"그리(?:는|기|릴)\s*(?:순서|차례|과정|방법)|그려\s*(?:보|봐)|컴퍼스로[^.?!\n]{0,10}그리"
    ),
    # #782 설계 v8: '그래프를 만들어'·'그래프로 정리해'(3·4·5차 미션 검토 시키는 말 18번)
    "그래프로 나타내기": re.compile(
        r"그래프(?:로|를)\s*(?:나타내|그려|그리|만들어|만들자|만들기|정리해)"
    ),
    "재기": re.compile(r"(?:줄자|자|저울)로\s*(?:다시\s*)?(?:재어|재\s?보|재\s?봐|재자|재기|달아)"),
    "걸어 보기": re.compile(r"걸어\s*(?:보|봐)"),
    "그림에서 찾기": re.compile(r"그림에서\s*찾아"),
    "소리 내어·끊어 읽기": re.compile(r"소리\s*내어|낭독|끊어\s*읽|띄어\s*읽"),
    "검색하기": re.compile(r"검색해\s*(?:보|봐)|검색(?:하|해)(?:자|기)"),
    "토의·토론 글": re.compile(r"토의\s*글|토론\s*글|토의에\s*보탤"),
}


def act_names(text: str | None) -> list[str]:
    """text가 학생에게 글로 할 수 없는 활동을 그 이름으로 시키는 말(ACT_NAMES 이름)."""
    return [name for name, p in ACT_NAMES.items() if p.search(text or "")]


# #782 설계 v7: 지문(이야기 속 글)이라도 시키는 끝으로 맺은 문장(5차 hand4b·way3 지문 "이 자료를
# 그래프로 나타내 보자" — 미션 검사는 지문 문장을 이야기 속 사실로 보고 빼서 못 잡았음)
# v8: '주세요·줄래요·볼래·보렴·하렴'(실제 지문 7개 중 '…살펴봐 주세요'를 놓침)
ORDER_END = re.compile(
    r"(?:보자|봐|봐요|하자|해\s?줘|줘|줄래|줄래요|주세요|볼까|볼까요|볼래|볼래요|봅시다|보세요|"
    r"하세요|보렴|하렴)\s*[.?!]*\s*$"
)
# #782 설계 v8: 지문 끝의 부탁·쓰임 문장("…경험 모음에 실으려 해요"). 미션이 자기 말로 옮겨
# 질문 앞에 두므로 지문 그대로 쓰기(MATERIAL_MISSING)에서 뺌(지문 빠짐 37번 중 28번)
REQUEST_END = re.compile(
    r"(?:줄래|주세요|부탁|싶어|싶다|싶어요|기다려|기다릴게|기다려요|실으려|싣고|붙일게|붙이려|"
    r"해\s?줘|좋겠어|좋겠어요|도와줘)[^.?!\n]{0,6}[.?!]*\s*$"
)


def act_orders(text: str | None) -> list[str]:
    """text의 문장 중 활동 이름을 시키는 끝으로 맺은 문장의 활동 이름."""
    found = [
        a
        for s in re.findall(r"[^.?!\n]+[.?!]*", text or "")
        if ORDER_END.search(s)
        for a in act_names(s)
    ]
    return list(dict.fromkeys(found))


def theme_day(theme: Theme, day: str) -> dict:
    return next(d for d in theme["days"] if d["day"] == day)


# 칸 하나만 고쳐 쓰면 되는 줄거리 검사 사유(fix_theme). 이야기 틀·정답 논리·표에 닿지 않는 글 칸만
FIX_PATH = re.compile(
    r"^(?:title|bigQuestion|intro|outro|incident|answerLook|introPlace|outroPlace"
    r"|(?:MON|TUE|WED|THU|FRI)\."
    r"(?:place|sceneNote|clue|discovery|missionHook|missionMaterial|dayStep|helper|helperUse)"
    r"|(?:introCuts|outroCuts)[1-6]\.caption)$"
)
# 콘티 scene·action은 뭉치 동작 검사(CUT_ACTION)·그림에 나오면 안 되는 이름(CUT_TARGET, #765)일
# 때만 그 칸을 고쳐 쓴다(정답 유출은 다시 생성)
CUT_FIX_PATH = re.compile(r"^(?:introCuts|outroCuts)[1-6]\.(?:scene|action)$")
FIX_REASON = (
    re.compile(r"^LENGTH (\S+) \d+자 > \d+$"),
    re.compile(r"^CUT_ACTION ((?:introCuts|outroCuts)[1-6])\.(scene|action) "),
    # #765 그림에 나오면 안 되는 대상·후보 이름이 컷 설명에 있으면 그 칸만 고쳐 씀
    re.compile(r"^CUT_TARGET ((?:introCuts|outroCuts)[1-6])\.(scene|action) "),
    # #779 자막 꼴('이름: 대사', 말하는 사람이 그 컷에 보임)·자막 있는 컷이 비면 그 자막만 고쳐 씀
    re.compile(r"^CUT_SPEAKER ((?:introCuts|outroCuts)[1-6])\.(caption) "),
    # #779 종료 1컷 자막은 뭉치가 정답을 말함(경찰관 떡집 콘티: "장난꾸러기 찾았다!"로 정답이 빠짐)
    re.compile(r"^CUT_ANSWER ((?:introCuts|outroCuts)[1-6])\.(caption) "),
    # #779 종료 6컷(엔딩)은 그 컷에 보이는 인물이 뭉치에게 고마워함(사용자 결정 2026-11-19)
    re.compile(r"^CUT_THANKS ((?:introCuts|outroCuts)[1-6])\.(caption) "),
    re.compile(r"^REQUIRED ((?:introCuts|outroCuts)[1-6])\.(caption)$"),
    re.compile(
        r"^CLUE_EARLY (MON|TUE|WED|THU|FRI) "
        r"(discovery|sceneNote|missionMaterial|missionHook|dayStep)에 "
    ),
    # #782 테마 짜임: 오늘 온 까닭이 앞 요일 단서 결과를 말하면 그 칸만 고쳐 씀
    re.compile(r"^PREV_CLUE (MON|TUE|WED|THU|FRI) (dayStep)에 "),
    re.compile(r"^REQUIRED (MON|TUE|WED|THU|FRI)\.(dayStep)$"),
    # #782 설계 v10: 국어 부탁 날 아이 답의 쓰임이 비면 그 칸만 써 넣음
    re.compile(r"^REQUIRED (MON|TUE|WED|THU|FRI)\.(helperUse)$"),
    # #782: 수사 연결 문장이 학생이 할 수 없는 활동 이름(발표 글 등)으로 청하면 그 칸만 고쳐 씀
    re.compile(r"^ACT_NAME (MON|TUE|WED|THU|FRI) (missionHook|missionMaterial)에 "),
    # #782 미션 방식 흐름(사용자 결정 2026-11-20): 단서·장면 메모·수사 연결 문장 그 칸만
    re.compile(r"^EVIDENCE_EARLY (MON|TUE|WED|THU|FRI) (sceneNote|missionHook)에 "),
    re.compile(r"^HOOK_SELF (MON|TUE|WED|THU|FRI) (missionHook)에 "),
    re.compile(
        r"^HELPER_SAME (MON|TUE|WED|THU|FRI) "
        r"(helper|sceneNote|missionHook|missionMaterial|dayStep) "
    ),
    re.compile(r"^DAY1_TIME (MON) (dayStep)에 "),
    # #782 설계 v7: 오늘 온 까닭
    re.compile(r"^DAY_STEP_MADE (TUE|WED|THU|FRI) (dayStep)에 "),
    re.compile(r"^SELF_NAME (MON|TUE|WED|THU|FRI) (dayStep)에 "),
    # #782 설계 v6
    re.compile(r"^KEPT_TRACE (MON|TUE|WED|THU|FRI) (clue) "),
    # #782 설계 v12: 9차 치명 결함 종류(그 칸만 고쳐 씀)
    re.compile(r"^KEPT_CARRY (MON|TUE|WED|THU|FRI) (clue) "),
    re.compile(r"^GIFT_CARRY (MON|TUE|WED|THU|FRI) (clue) "),
    re.compile(r"^STORY_FEATURE (MON|TUE|WED|THU|FRI) (clue) "),
    re.compile(r"^RECORD_HEARSAY (MON|TUE|WED|THU|FRI) (clue) "),
    # #782 설계 v13: 수사 날 증언에 그날 단서 내용이 없으면 그 지문만 고쳐 씀
    re.compile(r"^TESTIMONY_MISSING (MON|TUE|WED|THU|FRI) (missionMaterial) "),
    re.compile(r"^SOUND_TELLER (MON|TUE|WED|THU|FRI) (dayStep)에 "),
    re.compile(r"^EVENT_NAME (MON|TUE|WED|THU|FRI) (clue|dayStep|missionMaterial)에 "),
    re.compile(r"^SOUND_SEEN (MON|TUE|WED|THU|FRI) (clue) "),
    re.compile(r"^SEEN_TRACE (intro|incident)에 "),
    # #782 설계 v7
    re.compile(r"^INTRO_CLOCK (intro)에 "),
    # #782 설계 v10: 아직 안 열린 행사는 지문도 그 칸만, 아이가 이미 아는 것(시작 이야기·오늘 온
    # 까닭)도 그 칸만
    re.compile(r"^EVENT_LATER (MON|TUE|WED|THU|FRI) (clue|missionMaterial)에 "),
    re.compile(r"^INTRO_(?:HEARD|FOUND) (intro)에 "),
    re.compile(r"^INTRO_(?:HEARD|FOUND) (MON|TUE|WED|THU|FRI) (dayStep)에 "),
    re.compile(r"^STORY_SELF (MON|TUE|WED|THU|FRI) (clue)에 "),
    # #782 설계 v9
    re.compile(r"^MATERIAL_RECORD (MON|TUE|WED|THU|FRI) (missionMaterial)에 "),
    re.compile(r"^GRADE_MATH (MON|TUE|WED|THU|FRI) (missionMaterial|missionHook)에 "),
    re.compile(r"^ANSWER_LEAK (\S+?)에 "),
    re.compile(r"^CANDIDATE_NAME (\S+?)에 "),  # #634 엔딩 전 글의 후보 이름(사실표 종류)
    re.compile(r"^ANSWER_FACT (\S+?)에 "),  # #634 ② 엔딩 전 글의 정답만의 표 값
    re.compile(r"^CLUE_WORDING (MON|TUE|WED|THU|FRI) (clue) "),
    re.compile(r"^CLUE_OWNER (MON|TUE|WED|THU|FRI) (clue) "),
    # #782 설계 v3: 부탁 날 단서가 전해 들은 말이거나 흔적 날에 돕는 사람과 연결이 없으면 그 단서만
    re.compile(r"^CLUE_SOURCE (MON|TUE|WED|THU|FRI) (clue) "),
    # 단서 문장의 허용 값 낱말이 빠지거나 허용 밖 값이 들어가면 그 단서만 고쳐 씀(#535 7차: 흔적
    # 단서에 대상 낱말을 넣으며 값 낱말이 빠져 CLUE_TEXT 0.5 → 2.0, 줄거리 전체를 다시 만들며
    # 되풀이됨)
    re.compile(r"^CLUE_TEXT (MON|TUE|WED|THU|FRI) (clue) "),
    # #782 테마 짜임: 사건 단서에 후보 이름·특징 값이 섞이면 그 단서만 고쳐 씀
    re.compile(r"^STORY_VALUE (MON|TUE|WED|THU|FRI) (clue) "),
    re.compile(r"^OUTRO_RECAP (outro) "),
    re.compile(r"^OUTRO_ANSWER (outro) "),  # #634 ④ 시간 탐정 마무리 장면의 다른 시각
    re.compile(r"^HIDE_SPOT (MON|TUE|WED|THU|FRI) (sceneNote|discovery|clue|missionHook) "),
    re.compile(r"^CLUE_PROOF (MON|TUE|WED|THU|FRI) (clue) "),
    re.compile(r"^TIME_WORD (\S+?)에 "),  # #634 ④ 시간 탐정 엔딩 전 글의 시각
    # #782 설계 v4: 소리 탐정 시작 이야기·큰 질문의 '밤마다', 맡겨 둔 대상의 다른 맡긴 곳
    re.compile(r"^SOUND_NIGHT (intro|bigQuestion)에 "),
    re.compile(
        r"^KEPT_PLACE (MON|TUE|WED|THU|FRI) (clue|sceneNote|discovery|missionMaterial|missionHook) "
    ),
    # #634 ③: 사건(incident)·정답 동물 모습(answerLook)이 비면 그 칸만 써 넣음(판정 실측 3건이
    # 이 사유로 줄거리를 다시 만듦)
    re.compile(r"^REQUIRED (incident|answerLook|introPlace|outroPlace)$"),  # 장소는 #779
    # 증거 종류(evidence.kind)는 그대로 두고 단서 문장만 그 종류에 맞게 고쳐 씀(실측 2026-11-11:
    # 단서 글자 수 초과와 섞이면 줄거리 전체를 다시 만들어 상한까지 실패, 글 20건 1건·전체 실측
    # 1건). 배정(evidencePlan)과 종류가 다르면 fix_theme이 종류를 배정대로 바꾸고 그날 단서·증거
    # 발견 줄·수사 연결 문장을 고쳐 씀(#535). 매체만 다르면 단서·증거 발견 줄만
    re.compile(r"^CLUE_EVIDENCE (MON|TUE|WED|THU|FRI) (clue|discovery|missionHook) "),
)


# 단서 말투(CLUE_WORDING). 실측 2026-11-11 글 검토 CLUE_LOGIC 20건 중 4건은 허용 값 여럿을
# '모두' 있었던 것처럼 썼고(조건은 그중 하나), RULE 단서에 '~수도 있다'처럼 흐리게 써서 후보를
# 뺄 수 없었다. '반듯한'·'번듯한'의 '듯'은 흐린 말이 아님
ALL_VALUES_WORDS = re.compile(r"모두|전부|둘 다|셋 다|넷 다")
HEDGE_WORDS = re.compile(r"수도 있|지도 모르|것 같|(?<![반번])듯|아마")


def clue_wording_problems(day: dict) -> list[str]:
    clue = day.get("clue") or ""
    cond = day.get("condition") or {}
    out = []
    if len(cond.get("allowed") or []) >= 2 and (m := ALL_VALUES_WORDS.search(clue)):
        out.append(f"허용 값 여럿을 모두 있었던 것처럼 씀('{m.group()}', 그중 한 곳·하나로 씀)")
    if cond.get("kind") == "RULE" and (m := HEDGE_WORDS.search(clue)):
        out.append(f"후보를 빼는 단서를 흐리게 씀('{m.group()}', 단정해서 씀)")
    # 쪽지 꼴('오후 3시 목격: 짧은 꼬리.')은 학생이 읽는 한 줄 글로 딱딱함(#634 작은 실측 2차).
    # 비율 '2:3'·시각 '3:30'은 빼고 칸 고쳐 쓰기로 문장으로
    if re.search(r"(?<!\d)\s*[:：](?!\d)", clue):
        out.append("단서를 '목격:'처럼 쪽지 꼴로 씀(누가 무엇을 봤는지 한 문장으로)")
    return out


# 단서 문장이 기록(사진·영상·녹음 등)을 말하면 증거 종류는 RECORD, RECORD면 기록 낱말이 있어야 함
# (실측 2026-11-11: 사진을 근거로 한 단서에 evidence가 SIGHTING이라 글 검토 CLUE_LOGIC으로 실패)
RECORD_WORDS = ("사진", "영상", "녹음", "기록", "일지", "메모", "녹화", "동영상", "cctv", "CCTV")


def clue_evidence_mismatch(day: dict) -> bool:
    clue = day.get("clue") or ""
    kind = (day.get("evidence") or {}).get("kind")
    has_record = any(w in clue for w in RECORD_WORDS)
    return (has_record and kind != "RECORD") or (kind == "RECORD" and not has_record)


# 손에 든 것 종류의 목격 날 단서가 대상에 남은 것을 말하는 꼴(마지막 확인 3차: 길 종류에서 '상자에
# 묻은 먼지 색'을 목격 날에 써서 글 검토 CLUE_LOGIC 3건 "흔적인데 목격으로 표시")
SIGHTING_TRACE_WORDS = re.compile(r"흔적|자국|묻은|묻어|묻었|얼룩|남아 있|남은")


def sighting_names_trace(theme: Theme, day: dict) -> bool:
    """손에 든 것 종류에서 목격 날 단서가 흔적을 말하는지(CLUE_EVIDENCE, 칸 고쳐 쓰기)."""
    if not story_type(theme).target_in_hand:
        return False
    if (day.get("evidence") or {}).get("kind") != "SIGHTING":
        return False
    return bool(SIGHTING_TRACE_WORDS.search(str(day.get("clue") or "")))


def evidence_plan(seed: str) -> dict[str, dict[str, str | None]]:
    """요일별 증거 종류·기록 매체 배정 {요일: {kind, medium}}.

    같은 씨앗이면 같은 배정(다시 생성해도 바뀌지 않게, 이름 고르기와 같은 방식). 구성 하나를 골라
    요일에 섞고 기록 날마다 서로 다른 매체를 고른다."""
    rng = random.Random(f"{seed}-evidence")
    kinds = list(rng.choice(EVIDENCE_MIXES))
    rng.shuffle(kinds)
    media = iter(rng.sample(RECORD_MEDIA, kinds.count("RECORD")))
    return {
        day: {"kind": kind, "medium": next(media) if kind == "RECORD" else None}
        for day, kind in zip(DAYS, kinds, strict=True)
    }


def plan_for_type(
    plan: dict[str, dict[str, str | None]], kind: StoryType | None
) -> dict[str, dict[str, str | None]]:
    """흔적으로 알 수 있는 특징이 없는 종류(시간 탐정)는 배정의 흔적을 목격으로 바꿔 모델에 준다.

    줄거리 뒤 fit_evidence_plan도 같은 쪽으로 바꾸지만, 모델이 흔적 배정을 받으면 흔적 단서를 지어
    CLUE_EVIDENCE 칸 고쳐 쓰기가 늘어서 미리 맞춤(#634 ④, 흔적 0개 — 사용자 확인 2026-11-17).
    """
    if kind is None:
        return plan
    out = {d: dict(slot) for d, slot in plan.items()}
    if kind.no_trace:
        for slot in out.values():
            if slot.get("kind") == "TRACE":
                slot.update(kind="SIGHTING", medium=None)
    # 표의 어느 특징도 쓰지 않는 매체(소리 탐정의 사진)는 미리 다른 매체로(#634 ⑤ 틈 5)
    table = kind.facts
    if table is not None and table.media and set(table.media) == set(table.features):
        usable = [m for m in RECORD_MEDIA if any(m in ms for ms in table.media.values())]
        used = {slot.get("medium") for slot in out.values()}
        for slot in out.values():
            if slot.get("kind") == "RECORD" and slot.get("medium") not in usable:
                new = next((m for m in usable if m not in used), usable[0])
                slot["medium"] = new
                used.add(new)
    return out if out != plan else plan


def traceable(feature: str | None, kind: StoryType | None = None) -> bool:
    """그날 특징이 흔적(TRACE)으로 남을 수 있는지(TRACE_FEATURE 기준안).

    종류별 흔적 특징(families: 동물은 몸 흔적만, 손에 든 것은 대상에 묻거나 밴 것·대상 자체를 더함).
    """
    f = feature or ""
    if kind is not None and kind.trace is not None:
        if kind.trace.search(f):
            return True
        if kind.trace_only:
            return False
    return bool(TRACE_FEATURE.search(f)) and not NOT_TRACE_FEATURE.search(f)


# 사건 단서(#782 테마 짜임, 사용자 결정 2026-11-19): 후보를 빼지 않는 날은 후보 특징 표 대신 사건이
# 어떻게 벌어졌는지 새 사실을 준다(예: '부스러기가 창틀 쪽으로 이어져 있었어'). 전에는 후보를 빼지
# 않는 날이 앞 요일 단서를 되풀이했다(저장된 실측 develop 37테마 중 11개). 조건은 feature ''·allowed
# []이고 rulesOut은 비며 응답 clueFeature는 null(learning·웹이 이미 처리)
STORY = "STORY"


def is_story(cond: dict) -> bool:
    return cond.get("kind") == STORY


def story_value_hits(theme: Theme, table: dict[str, dict[str, str]], clue: str | None) -> list[str]:
    """사건 단서가 말하면 안 되는 낱말: 후보 이름과 후보 특징 표의 값(말하면 몰래 후보를 가름)."""
    values = sorted({v for vals in table.values() for v in vals.values() if v})
    names = [c for c in theme.get("candidates") or [] if c and compact(c) in compact(clue)]
    return list(dict.fromkeys([*names, *[v for v in values if mentions_value(v, clue)]]))


# 미션 방식(#782 테마 짜임, 기준안 — 확인 전): 그날 미션이 이야기에 들어오는 길. ASK 부탁(돕는
# 사람의 일을 도와주면 보답으로 본 것을 알려 줌), INVESTIGATE 수사(돕는 사람이 가진 증거를 읽고
# 따짐). 코드가 줄거리 전에 정하고 줄거리 내부 칸 missionWay에 넣는다(응답에 없음). 함께 발견(일을
# 같이 하다 그 자리에서 흔적 발견)은 뺐다(사용자 결정 2026-11-20 "A+C"): 40개 측정 r782-final40에서
# 함께 발견이 있는 테마는 18개 중 9개 실패(없는 테마 22개 중 4개) — 단서 조건과 '그 일을 하던
# 자리'를 함께 맞추느라 우연이 지나치거나('물뿌리개 곁에서 강아지 발자국') 논리가
# 어긋남('상자를 저울에 올리니 묵직한 상자')
ASK, INVESTIGATE = "ASK", "INVESTIGATE"
MISSION_WAYS = (ASK, INVESTIGATE)
# 수사 날은 증거를 따지는 활동이 곧 성취기준 행동인 '판단하기' 읽기·매체 성취기준 날만(서술·논술).
# 작은 생성 r782-ways-rd3~rd5 수사 날 8개: 사실·의견(4국02-04)·출처(4국02-05)·매체 신뢰성(6국06-02)
# 5개는 모두 목격 메모·취재 기록을 따져 자연스러웠고, 요약·주장(6국02-01)·추론(6국02-02) 3개는
# 지문이 일반론("한 가지 말만 믿지 않는 편이 좋습니다")이거나 돕는 사람 속을 추론하게 함(사용자 결정
# 2026-11-20). 중심 생각 간추리기(4국02-02)·예측하며 읽기(4국02-03)도 요약할 긴 글·이어지는 글이
# 필요해 뺌(부탁 날 돕는 사람의 안내문·쪽지로)
INVESTIGATE_STANDARDS = frozenset({"4국02-04", "4국02-05", "6국06-02"})
INVESTIGATE_INPUTS = ("NARRATIVE", "ESSAY")


def mission_way(day: dict) -> str:
    """그날 미션 방식. 칸이 없으면(예전 저장본) 수사 — 예전 수사 연결 문장·지문은 증거의 한
    부분이었음."""
    way = day.get("missionWay")
    return way if way in MISSION_WAYS else INVESTIGATE


# 미션 방식과 증거 종류의 짝(#782, 2026-11-20 작은 생성 r782-ways-rd3를 읽고 찾음): 수사 날에 증거가
# 흔적이면 읽고 따질 말·글이 없다('주인의 생각을 추론해 볼래?'). 흔적은 본 사람이 알려 주고(부탁),
# 목격·기록은 본 사람이 알려 주거나 그 말·기록을 따진다
WAY_FITS = {
    "TRACE": (ASK,),
    "SIGHTING": (ASK, INVESTIGATE),
    "RECORD": (ASK, INVESTIGATE),
}


def way_fits(way: str, kind: str | None) -> bool:
    return way in WAY_FITS.get(str(kind), MISSION_WAYS)


def testimony_day(day: dict) -> bool:
    """수사 날 지문이 증언 하나인 꼴인지(#782 설계 v13): 그때 직접 보거나 적은 사람의 증언에 그날
    단서 내용이 들어 있고, 단서는 따져서 확실해진 그 내용. missionWay 칸에 INVESTIGATE가 적힌
    날만(칸이 없는 예전 저장본은 예전 규칙 — 지문에 단서 결론을 쓰지 않음). 새 줄거리는
    plan_theme이 모든 요일에 칸을 넣음."""
    return day.get("missionWay") == INVESTIGATE


def testimony_ok(theme: Theme, path: str) -> list[str]:
    """수사 날 지문(그날 missionMaterial)에 있어도 되는 그날 단서 값(단서가 알려 주는 값). 그 밖의
    칸·날은 빈 목록."""
    head, _, key = path.partition(".")
    if key != "missionMaterial" or head not in DAYS:
        return []
    d = theme_day(theme, head)
    return clue_says(d) if testimony_day(d) else []


def mission_way_plan(
    days: list[tuple[str, list[str], str]],
    plan: dict[str, dict[str, str | None]],
    rng: random.Random,
) -> tuple[dict[str, str], dict[str, dict[str, str | None]]]:
    """요일마다 미션 방식과 증거 배정을 함께 정한다(days: [(요일, 성취기준 코드, 입력 방식)], plan:
    요일별 증거 종류·매체 배정) → (방식, 요일 순서를 맞춘 증거 배정).

    방식은 그날 증거 종류에 맞는 것만(WAY_FITS), 수사는 판단하기 성취기준 + 서술·논술 날만.
    연달아 같은 방식이 가장 적은 배정을 고르고(수사 날이 드물어 부탁이 이어질 수 있음 — 돕는
    사람은 요일마다 다름), 그러려고 증거 배정의 요일 순서를 바꾼다(한 주 증거 구성은 그대로,
    순서는 원래 씨앗으로 섞은 것). 같은 씨앗이면 같은 배정.
    """
    names = [d for d, _, _ in days]
    can = [
        bool(codes) and all(c in INVESTIGATE_STANDARDS for c in codes) and how in INVESTIGATE_INPUTS
        for _, codes, how in days
    ]
    slots = [plan[d] for d in names]
    best: tuple[int, int] | None = None
    found: list[tuple[tuple[int, ...], tuple[str, ...]]] = []
    for order in sorted(set(itertools.permutations(range(len(slots))))):
        kinds = [slots[i].get("kind") for i in order]
        options = [
            [w for w in WAY_FITS.get(str(k), MISSION_WAYS) if w != INVESTIGATE or ok]
            for k, ok in zip(kinds, can, strict=True)
        ]
        moved = sum(i != j for i, j in enumerate(order))
        for ways in itertools.product(*options):
            score = (sum(a == b for a, b in itertools.pairwise(ways)), moved)
            if best is None or score < best:
                best, found = score, []
            if score == best:
                found.append((order, ways))
    order, ways = rng.choice(found)
    return (
        dict(zip(names, ways, strict=True)),
        {d: dict(slots[i]) for d, i in zip(names, order, strict=True)},
    )


def refit_ways(theme: Theme) -> list[str]:
    """줄거리 뒤 코드가 증거 배정을 옮겨(fit_evidence_plan) 그날 방식과 증거가 안 맞게 되면(수사
    날이 흔적이 되면) 그날을 부탁으로 바꾼다(본 사람이 알려 줌, 부탁은 모든 증거와 맞음).
    바꾼 요일을 돌려준다 — 그날 단서·증거 발견 줄은 증거가 바뀌어 어차피 고쳐 쓰고, 할 일·지문은
    부탁에 맞게 고쳐 쓴다(WAY_FIX)."""
    changed = []
    for d in theme.get("days") or []:
        kind = (d.get("evidence") or {}).get("kind")
        slot = plan_slot(theme, d.get("day") or "") or {}
        if d.get("missionWay") in MISSION_WAYS and not way_fits(
            d["missionWay"], slot.get("kind") or kind
        ):
            d["missionWay"] = ASK
            changed.append(d["day"])
    return changed


# 미션 방식 흐름 검사(#782, 사용자 결정 2026-11-20 "이 설계대로"). 작은 생성(r782-ways-rd3)에서
# 부탁 날 약속이 엉뚱하고(3/4), 장면 메모의 흔적이 문제 전 대화로 새고, 수사 날 돕는 사람이 자기
# 생각을 추측하라고 함 → 칸만 고쳐 씀(부탁 약속은 그 요일 대화만 다시)
EVIDENCE_EARLY_WORDS = re.compile(r"흔적|자국")
HOOK_SELF_WORDS = re.compile(r"(?<![가-힣])내\s?(?:생각|마음|기분|속마음)|나의\s?(?:생각|마음)")
GUESS_WORDS = re.compile(r"추론|추측|짐작|맞혀|알아맞|헤아려")
# #782 설계 v8: 들은·맛본·맡은 날 약속('들은 걸 알려 줄게', '내 녹음을 들려줄게')
# #782 설계 v11: 모델이 자유롭게 쓴 약속 꼴('얘기해 줄게'·'알려 줄 거야'·'말해 줄 수 있어')을
# 못 알아보면 약속을 대신 넣다가 줄이 늘어남(8차 b '약속이 없음' 다수)
ASK_PROMISE_VERB = re.compile(
    r"(?:알려|보여|말해|들려|얘기해|이야기해)\s?"
    r"(?:줄게|줄께|드릴게|드릴께|줄\s?거야|줄\s?수\s?있|줄래|드릴\s?수|줄\s?테니)"
    # #782 설계 v12: 10차 '들은 소리 이야기도 해 줄게'·'들린 소리를 전해 줄게'
    r"|이야기\s?(?:도|를)?\s?해\s?(?:줄게|줄께|드릴게|줄\s?거야)|전해\s?(?:줄게|줄께|드릴게)"
)
ASK_PROMISE_CASE = re.compile(
    # #782 설계 v9: '내가 들은 소리를'·'맡은 냄새를'·'맛본 걸'
    r"본\s?[걸것거]|봤|그때|들은\s?(?:[걸것거]|소리)|맡은\s?(?:[걸것거]|냄새)|맛본\s?[걸것거]|"
    # #782 설계 v12: 10차 '내가 본 장면을'·'살펴본 우산들의 모습을'·'잠들 무렵 들린 소리를'(맞는
    # 약속인데 '약속 없음'으로 잡음 — 10차 '약속 없음' 14번 중 7번)
    r"(?<![가-힣])본\s|살펴본|들린\s|들은\s|" + "|".join(RECORD_WORDS)
)
# #782 설계 v10: 사건 단서 날은 단서 마지막 말이 듣기('소리가 났어·들렸어')일 때만 들은 날. v9는
# 단서 어디든 '소리'가 있으면 들은 날이라 "그 소리가 난 뒤 창문에 달빛이 비쳤어"(본 것)도 '들은
# 소리'로 약속했음. 쉼표·'뒤'에서 끊은 마지막 말을 본다
CLAUSE_CUT = re.compile(r"[,.!?…~]|\s뒤(?:에|로)?(?=\s|$)")
# #782 설계 v12: '이어졌어·멎었어'도 소리 이야기(12차 snd5b), '흔들렸어'의 '들렸'은 아님(13차 snd3b)
HEARD_END = re.compile(
    r"소리[^,]*?(?:났|(?<!흔)들렸|들었|울렸|이어졌|멎었|그쳤|멈췄)[가-힣\s]{0,6}$"
)
# 약속 감각이 그날 단서와 다름: 본 날인데 '들은·들려'(기록 아님), 들은 날인데 '본·봤'('들어 봤'은
# 듣기)
# 8차 a: '본 걸 들려줄게'(이야기해 줄게)의 '들려'를 들은 것으로 봐 대화를 29번 다시 만듦 →
# '들은 소리·것'·'들었'·'들렸'만 들은 것
PROMISE_HEARD = re.compile(r"(?<!만)들은\s?(?:소리|것|걸|거)|들었|들렸")
PROMISE_SEEN = re.compile(r"(?<![가-힣])본\s?(?:[걸것거]|게|대로)|(?<![어아])(?<![어아]\s)봤")
# #782 설계 v12: 약속 말에 붙은 지금 일('오늘 본 것'·'아까')·전해 들은 말('전해 들은 소리')
PROMISE_NOW = re.compile(r"(?<![가-힣])(?:오늘|아까|방금)")
PROMISE_HEARSAY = re.compile(r"전해\s?들|들었대|했대|였대|이었대")
PROMISE_IF = re.compile(r"(?:면|다면|으면)(?:[,\s]|$)")
PROMISE_WHAT = {
    "SEEN": "본 것",
    "HEARD": "들은 소리",
    "TASTED": "맛본 것",
    "SMELLED": "맡은 냄새",
}


# #782 설계 v12: 단서 문장이 본 것이라고 말함('본 ○○'·'내가 봤어'·'눈으로', SOUND_SEEN).
# '흔들어 보니'·'따져 보니'는 본 것이 아님
CLUE_SEEN = re.compile(r"(?<![가-힣])본\s|(?:내가|제가|직접)\s?(?:봤|보았|보니)|눈으로")


def promise_clause(text: str) -> str:
    """약속 줄에서 조건('~하면') 뒤 약속 말(#782 설계 v12). 조건이 없으면 줄 전체."""
    return PROMISE_IF.split(text or "")[-1]


def last_clause(text: str) -> str:
    """쉼표·문장 끝·'뒤'에서 끊은 마지막 말(#782 설계 v10)."""
    parts = [p.strip() for p in CLAUSE_CUT.split(text or "") if p.strip()]
    return parts[-1] if parts else ""


def promise_sense(theme: Theme, day: dict | str) -> tuple[str, str | None]:
    """부탁 날 돕는 사람이 도와주면 알려 줄 것의 감각(#782 설계 v10). (감각, 기록 매체).

    RECORD(배정 매체, 배정이 없는 예전 저장본은 증거 발견 줄의 기록 낱말, 없으면 '기록') /
    특징 이름의 감각(소리 HEARD·맛 TASTED·냄새·향 SMELLED) / 사건 단서 날(특징 없음)은 단서 마지막
    말이 듣기일 때만 HEARD, 그 밖은 SEEN. 대화 요청의 약속 뜻·코드 대신 문장(ask_promise)·대화
    검사(ASK_PROMISE)가 같이 쓴다."""
    d = theme_day(theme, day) if isinstance(day, str) else day
    if (d.get("evidence") or {}).get("kind") == "RECORD":
        found = next((w for w in RECORD_WORDS if w in str(d.get("discovery") or "")), "기록")
        return "RECORD", (plan_slot(theme, str(d.get("day") or "")) or {}).get("medium") or found
    feature = str((d.get("condition") or {}).get("feature") or "")
    clue = str(d.get("clue") or "")
    if feature:
        if "맛" in feature:
            return "TASTED", None
        if "냄새" in feature or SENSE_PATTERN["향"].search(feature):
            return "SMELLED", None
        base = "HEARD" if "소리" in feature else "SEEN"
    else:
        base = "HEARD" if HEARD_END.search(last_clause(clue)) else "SEEN"
    # #782 설계 v12: 사건 단서 날은 마지막 말(알려 주는 사실)이 소리 이야기일 때만 들은 날(HEARD_END
    # 넓힘). '내가 들은 그 밤, … 종이 장식이 흔들렸어'는 본 날(13차 snd5 — 앞말의 '들은'만 보고 들은
    # 날로 정했다가 약속이 어긋남). 소리 특징 단서를 '본'으로 쓰면 SOUND_SEEN이 단서를 고침
    return base, None


def promise_meaning(theme: Theme, day: dict | str) -> str:
    """약속 뜻의 목적어('본 것을'·'들은 소리를'·'자기 일지를', #782 설계 v10). 대화 요청과 대화
    검사 사유가 같은 말을 쓴다."""
    sense, medium = promise_sense(theme, day)
    what = f"자기 {medium or '기록'}" if sense == "RECORD" else PROMISE_WHAT[sense]
    return what + josa(what, "을", "를")


def ask_promise_mismatch(theme: Theme, day: dict, lines: list[dict[str, str]]) -> str | None:
    """부탁 날 돕는 사람의 약속 줄 감각이 그날 단서와 다르면 그 설명(#782 설계 v10). 약속 줄이
    없거나(ask_promise_missing이 봄) 부탁 날이 아니면 None."""
    helper = str(day.get("helper") or "").strip()
    if mission_way(day) != ASK or not helper:
        return None
    said = [
        x["text"]
        for x in lines
        if x.get("speaker") == helper and ASK_PROMISE_VERB.search(x["text"])
    ]
    if not said:
        return None
    # #782 설계 v12: 약속 말(조건 '~하면' 뒤)에 지금 일·전해 들은 말이 붙으면 그때 본 단서와 어긋남
    # (9차 '도와주면 오늘 본 것도 알려 줄게' 42줄 중 저장 결과 7·8·9차에서 잘못 잡은 것 0).
    # 조건('오늘 글을 같이 써 주면')의 '오늘'은 됨
    promised = [promise_clause(t) for t in said]
    if all(PROMISE_NOW.search(t) for t in promised):
        return "약속에 '오늘·아까'처럼 지금 일을 붙임"
    if all(PROMISE_HEARSAY.search(t) for t in promised):
        return "약속을 전해 들은 말로 함"
    sense, medium = promise_sense(theme, day)
    if sense == "RECORD":
        medium = medium or "기록"
        words = RECORD_WORDS if medium == "기록" else MEDIUM_WORDS.get(medium, (medium,))
        fits = [t for t in said if any(w in t for w in words)]
        return None if fits else f"기록 날인데 약속에 자기 {medium}이(가) 없음"
    if sense == "SEEN" and all(
        PROMISE_HEARD.search(t)
        and not PROMISE_SEEN.search(t)
        and not any(w in t for w in RECORD_WORDS)
        for t in said
    ):
        return "본 것을 알려 줄 날인데 '들은' 것을 약속함"
    if sense == "HEARD" and all(PROMISE_SEEN.search(t) for t in said):
        return "들은 소리를 알려 줄 날인데 '본' 것을 약속함"
    return None


# 약속 같은 줄: 약속 말이 있거나 '도와주면 ~ 줄게'(부탁 '도와줄래?'는 아님)
PROMISE_ISH = re.compile(
    r"도와\s?주면[^?]*(?:줄게|줄께|드릴게)|도와준다면[^?]*(?:줄게|줄께|드릴게)|"
    + ASK_PROMISE_VERB.pattern
)


# #782 설계 v11: 돕는 사람의 부탁 문장(물음·'부탁'·'~해 줘·줄래'). 약속을 대신 넣을 때 덮어쓰지
# 않음(부탁이 사라지면 그날 미션으로 잇는 말이 없어짐)
HELPER_REQUEST = re.compile(r"\?|부탁|줄래|도와\s?줘|해\s?줘|주세요|주겠니")


def line_sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=[.?!])\s+", text or "") if p.strip()]


def put_promise(
    lines: list[dict[str, str]], helper: str, sentence: str, grade: int
) -> list[dict[str, str]] | None:
    """약속 줄을 코드 문장으로 바꿔 넣는다(#782 설계 v10, v12부터 마지막 시도에도 남은 사유가
    ASK_PROMISE뿐일 때만). #782 설계 v11: 돕는 사람의 부탁 문장(HELPER_REQUEST)은 덮어쓰지 않는다.

    ① 돕는 사람 줄에 약속 같은 문장(부탁 아님)이 있으면 그 문장을 바꿈. 바꾼 줄이 40자를 넘으면
       그 줄에 부탁이 없을 때만 줄 전체를 바꾸고, 부탁이 있으면 약속 문장만 빼고 ②로
    ② 줄 수가 학년 상한 아래면 마지막 뭉치 줄 앞에 돕는 사람의 말로 넣음
    ③ 상한이면 돕는 사람의 첫 줄(곤란한 말)을 바꿈 — 부탁 문장이 든 줄은 부탁은 두고 나머지 문장
       자리에 약속(40자 안일 때만, 아니면 다음 돕는 사람 줄), 돕는 사람 줄이 모두 부탁뿐이면 첫
       줄의 부탁 뒤에 붙임(40자 안일 때만). 돕는 사람이 말하지 않았으면 마지막 줄 앞 줄(첫 줄은
       코드가 붙인 오늘 온 까닭이라 두고)
    넣을 수 없으면 None."""
    if len(sentence) > LINE_MAX or len(lines) < 2:
        return None
    out = [dict(x) for x in lines]
    for i, x in enumerate(out):
        if x.get("speaker") != helper:
            continue
        parts = line_sentences(str(x.get("text") or ""))
        hits = [
            j for j, p in enumerate(parts) if PROMISE_ISH.search(p) and not HELPER_REQUEST.search(p)
        ]
        if not hits:
            continue
        kept = " ".join(
            sentence if j == hits[0] else p
            for j, p in enumerate(parts)
            if j == hits[0] or j not in hits
        )
        if len(kept) <= LINE_MAX:
            out[i] = {**x, "text": kept}
            return out
        rest = [p for j, p in enumerate(parts) if j not in hits]
        if not any(HELPER_REQUEST.search(p) for p in rest):
            out[i] = {**x, "text": sentence}
            return out
        out[i] = {**x, "text": " ".join(rest)}  # 약속 문장만 빼고 부탁은 둠
        break
    line = {"speaker": helper, "text": sentence}
    if len(out) + 1 <= DIALOGUE_LINES[grade][1]:
        return [*out[:-1], line, out[-1]]
    mine = [i for i, x in enumerate(out[:-1]) if i and x.get("speaker") == helper]
    if not mine:
        if len(out) < 3:  # 첫 줄·마지막 줄밖에 없으면 바꿀 줄이 없음
            return None
        out[-2] = line
        return out
    for i in mine:
        parts = line_sentences(str(out[i].get("text") or ""))
        asks = [p for p in parts if HELPER_REQUEST.search(p)]
        if not asks:  # 곤란한 말만 있는 줄
            out[i] = {**out[i], "text": sentence}
            return out
        if len(asks) < len(parts) and len(text := " ".join([*asks, sentence])) <= LINE_MAX:
            out[i] = {**out[i], "text": text}
            return out
    parts = line_sentences(str(out[mine[0]].get("text") or ""))
    if all(HELPER_REQUEST.search(p) for p in parts):
        text = " ".join([*parts, sentence])
        if len(text) <= LINE_MAX:
            out[mine[0]] = {**out[mine[0]], "text": text}
            return out
    return None


def hook_asks_self(day: dict) -> bool:
    """수사 연결 문장이 돕는 사람 자신의 생각·마음을 추측하게 하는지('내 생각', 호칭 '주인의
    생각')."""
    hook = str(day.get("missionHook") or "")
    names = [w for w in str(day.get("helper") or "").split() if len(w) >= 2]
    own = (
        re.compile(r"(?:" + "|".join(map(re.escape, names)) + r")의\s?(?:생각|마음|기분|속마음)")
        if names
        else None
    )
    # '내 생각이 바뀐 까닭을 정리해 줄래?'(돌아보기 날 그 사람이 쓴 글 정리)는 됨 — 그 사람 속을
    # 추측·짐작하게 할 때만(실측 r782-ways-rd4 오탐)
    if not GUESS_WORDS.search(hook):
        return False
    return bool(HOOK_SELF_WORDS.search(hook) or (own and own.search(hook)))


# #782 설계 v9: 부탁 날 지문이 돕는 사람 자신의 기록('내 메모에는 이렇게 적혀 있어')이면 미션
# 전에 그날 증거가 보이고 단서와 어긋남(6차 치명 way6 화). 5·6차 부탁 날 261일 중 이 꼴은 그
# 1건. '기록'은 '기록장'처럼 일 자료 이름에도 쓰여 '내 ~'·'~에는 이렇게'만 봄
OWN_RECORD_MATERIAL = re.compile(
    r"(?<![가-힣])(?:내|제)\s?(?:메모|일지|수첩|녹음|사진|영상|기록)(?![가-힣]*장)"
    r"|(?:메모|일지|수첩|기록)(?:에는|엔)\s?(?:이렇게|다음)"
)


def way_problems(day: dict) -> list[str]:
    """요일 글 칸의 미션 방식 흐름 문제(줄거리 검사, 모두 그 칸만 고쳐 씀)."""
    bad: list[str] = []
    way, name = mission_way(day), day.get("day")
    if way == ASK and OWN_RECORD_MATERIAL.search(str(day.get("missionMaterial") or "")):
        bad.append(
            f"MATERIAL_RECORD {name} missionMaterial에 돕는 사람 자신의 기록(부탁 날 지문은 그 "
            "사람이 하는 일의 자료 — 안내문·쪽지·시·셀 수. 그 사람의 기록은 미션을 마친 뒤 "
            "단서로 나옴)"
        )
    # 부탁 날 증거는 문제를 마친 뒤 단서로 나옴. 장면 메모는 대화·그림 재료라 흔적을 쓰면 문제 전에
    # 새어 나감(어제 찾은 흔적을 말하는 오늘 온 까닭·대화 첫 줄은 정상이라 장면 메모만 봄)
    if way == ASK and EVIDENCE_EARLY_WORDS.search(str(day.get("sceneNote") or "")):
        bad.append(
            f"EVIDENCE_EARLY {name} sceneNote에 흔적·자국(부탁 날은 돕는 사람이 그 일을 하는 "
            "모습만, 증거는 문제 뒤 단서로)"
        )
    # 할 일 문장(대화 재료)도 흔적·자국은 같음(실측 r782-ways-rd6 초4 '흔적이 자리도 살필래?').
    # '도와주면 내가 본 흔적도 알려 줄게' 같은 약속은 됨. 기록 낱말(영상·사진·메모)은 보지 않음 —
    # 매체 성취기준 날 할 일에 원래 들어가는 낱말이라(40개 측정 r782-final40: '말·글·영상을 비교해
    # 볼래?'·'사진을 안전하게 나누는 방법' 등 44번 잘못 잡음)
    hook = str(day.get("missionHook") or "")
    if way == ASK and EVIDENCE_EARLY_WORDS.search(hook) and not ASK_PROMISE_VERB.search(hook):
        bad.append(
            f"EVIDENCE_EARLY {name} missionHook에 흔적·자국(부탁 날 할 일은 돕는 사람의 일만, "
            "증거는 문제 뒤 단서로)"
        )
    if hook_asks_self(day):
        bad.append(
            f"HOOK_SELF {name} missionHook에 돕는 사람 자신의 생각·마음을 추측하게 하는 말"
            "(따질 것은 증거 속 사람의 말·기록, 또는 그 사람이 맡은 일)"
        )
    return bad


# 월요일 '어제'(#782, 저장된 테마 230개 중 9개, r782-ways-rd3 초5는 이 모순으로 글 검토 실패):
# 첫날은 시작 이야기의 사건 직후라 어제 한 일이 없다. 시작 이야기가 밤·전날
# 일이면('어젯밤'·'밤마다') 됨
DAY1_YESTERDAY = re.compile(r"어제|어젯밤|전날|지난밤")
DAY1_NIGHT = re.compile(r"어제|어젯밤|전날|지난밤|밤마다|밤새|며칠")
# 문제 글이 사건 때를 그날 기준 지난 때로 씀(#782 설계 v13: 15차 치명 snd6b 수요일 '어젯밤 민박집
# 방에서 알 수 없는 소리가 들렸지만' — 사건은 월요일 전 일. 저장 결과 7~15차 통과 258개 테마에서
# 이 1건만, 잘못 잡은 것 0). 그냥 '어제'는 어제 다녀간 일로도 써서 뺌
INCIDENT_AGO = re.compile(r"어젯\s?밤|어젯\s?저녁|어제\s?(?:밤|저녁|새벽)|지난\s?밤|그저께|엊그제")


def day1_time(theme: Theme, text: str) -> bool:
    """월요일 글에 시작 이야기에 없는 '어제'가 있는지."""
    intro = str(theme.get("introStory") or theme.get("intro") or "")
    return bool(DAY1_YESTERDAY.search(text)) and not DAY1_NIGHT.search(intro)


HELPER_REGEN_DAYS = 3  # 돕는 사람 문제가 이 요일 수 이상이면 줄거리를 다시(기준안)


# #782 설계 v3(사용자 결정 2026-11-21): 돕는 사람은 일 → 사람 → 장소 순서로 정한다. 장소를 먼저
# 두고 그 장소 사람에게 성취기준 일을 맡기니 "운동장 선생님이 모래밭에서 시 감상 글을 부탁"처럼
# 동떨어졌음(2차 측정 억지 30일 중 13일). 국어 부탁 날은 성취기준 영역(코드 셋째·넷째 자리,
# 돌아보기는
# 생각 유형)마다 그 일을 하는 사람 호칭과 아이 답의 쓰임을 코드가 준다. 기준안 — 확인 전
# #782 설계 v9: 돌아보기 날 따로 둔 틀('방문자 쉼터 담당자'·'처음 온 아이들에게 줄 경험 모음')을
# 뺌 — 성취기준과 상관없이 늘 같은 틀이라 6차 측정 억지 13일 중 6일이 "경험 모음이 그 사람 일과
# 안 맞음". 돌아보기 날도 그날 성취기준 영역의 일 틀을 쓴다
HELPER_FRAMES: dict[str, tuple[tuple[str, ...], str, tuple[str, ...]]] = {
    # 영역: (호칭 후보, 아이 답의 쓰임, 질문에 있어야 할 쓰임 낱말)
    "05": (
        ("동네 시인", "그림책 작가", "이야기 할머니", "책방 주인"),
        "작품 소개판에 붙일게",
        ("소개판", "게시판", "모음"),
    ),
    "02": (
        ("소식지 기자", "작은 도서관 사서", "마을 소식판 담당자"),
        "소식지에 실을게",
        ("소식지", "소식판"),
    ),
    "03": (
        ("게시판 담당자", "행사 준비 담당자", "편지함 지기"),
        "게시판에 붙일게",
        ("게시판", "편지"),
    ),
    "04": (
        ("안내 방송 담당자", "표지판 목수", "안내문 쓰는 직원"),
        "안내판·방송 글로 쓸게",
        ("안내판", "방송", "표지판", "안내문"),
    ),
    "06": (
        ("마을 방송부원", "영상 기록가", "마을 소식 기자"),
        "마을 방송·영상 안내에 쓸게",
        ("방송", "영상"),
    ),
}
# #782 설계 v10: 줄거리 지시문에는 호칭 목록 대신 영역의 일 종류만 준다(7차 같은 호칭 17번 —
# 코드가 준 호칭 둘 중에서만 골라 한 주·여러 테마에 같은 사람이 되풀이됨). 모델이 그날 성취기준의
# 일 → 그 일을 하는 사람 → 아이 답의 쓰임(helperUse) → 장소 순서로 정한다. HELPER_FRAMES는 예전
# 저장본 쓰임 낱말용 데이터로만 남긴다(#782 설계 v11: 대신용 틀로 쓰던 돕는 사람 검토 review_helpers
# 는 뺌). 기준안 — 확인 전
AREA_WORK = {
    "01": "듣기·말하기 — 남의 말을 듣고 정리하거나 자기 생각을 말로 전하는 일",
    "02": "읽기 — 글을 읽고 간추리거나 추론해 남에게 전하는 일",
    "03": "쓰기 — 남에게 알리거나 마음·의견을 전하는 글을 쓰는 일",
    "04": "문법 — 낱말·문장을 바르게 고치거나 다듬어 남이 읽을 글로 만드는 일",
    "05": "문학 — 시·이야기 같은 작품을 읽고 느낌을 나누거나 작품을 소개하는 일",
    "06": "매체 — 기사·영상·안내 같은 매체 자료를 살펴 남에게 알리는 일",
}
KOREAN_AREA = re.compile(r"^\d국(\d\d)-")
# 그래프로 나타내고 해석하는 수학 성취기준(그리기만 하는 성취기준은 learning AUTO_EXCLUDED로
# 이미 뺌).
# 글로만 답하니 미션 검토 STANDARD_FIT "핵심 행동이 없음"(목요일 수학 실패 6건 중 3건)
GRAPH_STANDARDS = frozenset({"4수04-01", "4수04-02", "4수04-03", "6수04-02", "6수04-03"})


def frame_area(codes: list[str], thinking: str) -> str | None:
    """국어 성취기준의 일 틀 영역(돌아보기 날도 영역대로, #782 설계 v9). 수학은 None."""
    if not any(KOREAN_AREA.match(c) for c in codes):
        return None
    area = next(m.group(1) for c in codes if (m := KOREAN_AREA.match(c)))
    return area if area in HELPER_FRAMES else "02"


def day_frames(
    days: list[tuple[str, list[str], str]], ways: dict[str, str], rng: random.Random
) -> dict[str, dict[str, Any]]:
    """요일마다 성취기준 코드와, 국어 부탁 날이면 그날 일 종류(work)·대신용 호칭 둘·아이 답의
    쓰임(내부 칸 dayFrames). days는 (요일, 성취기준 코드, 생각 유형). 같은 호칭이 두 요일에 나오지
    않게 고른다. #782 설계 v10: 줄거리 지시문에는 work만 주고 roles·use·useWords는 대신용 틀과
    예전 저장본(부분 다시 생성 #537)용으로 그대로 둔다."""
    used: set[str] = set()
    out: dict[str, dict[str, Any]] = {}
    for day, codes, thinking in days:
        frame: dict[str, Any] = {"codes": list(codes)}
        area = frame_area(codes, thinking) if ways.get(day) == ASK else None
        if area:
            roles, use, words = HELPER_FRAMES[area]
            free = [r for r in roles if r not in used] or list(roles)
            picked = rng.sample(free, min(2, len(free)))
            used.update(picked)
            real = next(m.group(1) for c in codes if (m := KOREAN_AREA.match(c)))
            work = AREA_WORK.get(real) or AREA_WORK[area]
            frame |= {"work": work, "roles": picked, "use": use, "useWords": list(words)}
        out[day] = frame
    return out


def frame_of(theme: Theme, day: str) -> dict[str, Any]:
    return (theme.get("dayFrames") or {}).get(day) or {}


def helper_use_day(theme: Theme, day: dict) -> bool:
    """#782 설계 v10: 국어 부탁 날(dayFrames에 일 틀이 있는 부탁 날) — helperUse를 쓰는 날."""
    return mission_way(day) == ASK and bool(frame_of(theme, str(day.get("day"))).get("roles"))


# #782 설계 v10: 쓰임 낱말은 helperUse의 마지막 '에·에다·으로·로' 앞 말에서 뽑는다('책 추천
# 카드에 붙일게' → 추천·카드). 낱말 끝에 붙은 조사만(뒤가 띄어쓰기·끝)
USE_PARTICLE = re.compile(r"(?:에다|에|으로|로)(?=\s|$)")
USE_NOT_NOUN = re.compile(
    r"(?:해|하고|하는|하며|해서|하여|게|고|며|서|로|을|를|이|가|은|는|의|와|과)$"
)


def use_words(text: str) -> list[str]:
    """helperUse에서 쓰임 낱말(마지막 조사 앞 말의 두 글자 이상 한글 낱말, 조사가 없으면 전체)."""
    found = list(USE_PARTICLE.finditer(text or ""))
    head = (text or "")[: found[-1].start()] if found else text or ""
    # 합칠 때: 동사·조사가 붙은 말('정리해'·'두 줄로'·'써서')은 쓰임 낱말이 아님 — 흔한 말로 통과됨
    words = [w for w in re.findall(r"[가-힣]{2,}", head) if not USE_NOT_NOUN.search(w)]
    return list(dict.fromkeys(words))


def day_use(theme: Theme, day: str) -> tuple[str, list[str]]:
    """국어 부탁 날 아이 답의 쓰임 (글, 쓰임 낱말). 모델이 쓴 helperUse에서 뽑고, 비었거나 낱말이
    없으면(예전 저장본) dayFrames 쓰임·쓰임 낱말. 국어 부탁 날이 아니면 ('', [])."""
    frame = frame_of(theme, day)
    if not frame.get("useWords"):
        return "", []
    use = str(theme_day(theme, day).get("helperUse") or "").strip()
    # helperUse가 틀의 쓰임과 같거나 낱말이 없으면(예전 저장본) 틀의 쓰임 낱말로 봄
    if use != frame.get("use") and (words := use_words(use)):
        return use, words
    return str(frame.get("use") or ""), list(frame["useWords"])


def helper_problems(theme: Theme) -> list[str]:
    """돕는 사람이 앞 요일과 같거나 등장인물·찾는 대상·후보면 그날 돕는 사람을 바꿔 씀(HELPER_SAME).

    실측 r782-ways-rd4: 등장인물(떡집 사장님·캠핑장 관리인)이 매일 돕는 사람이 되어 같은 사람이 사흘
    '도와주면 본 걸 알려 줄게'를 함('왜 처음부터 안 알려 줘?'). 바꾸는 날은 helper와, 옛 호칭이
    나오는 그날 장면 메모·수사 연결 문장·미션 지문·오늘 온 까닭을 함께 고쳐 씀(그 요일만 한 호출).
    사흘 이상이면 HELPER_WEEK로 줄거리를 다시 만든다.
    """
    taken = {compact(c.get("name")) for c in theme.get("characters") or []}
    taken |= {compact(theme.get("target")), *(compact(c) for c in theme.get("candidates") or [])}
    taken.discard("")
    seen: set[str] = set()
    bad: list[str] = []
    flagged: list[str] = []
    for d in theme.get("days") or []:
        name = compact(d.get("helper"))
        if not name:
            continue
        # #782 설계 v10: 국어 부탁 날 배정 호칭 검사는 뺌(모델이 그날 일을 하는 사람을 정함).
        # #782 설계 v11: 억지는 미션 검토 STORY_LINK·글 검토·측정 판정이 봄(review_helpers 뺌)
        why = (
            "등장인물·찾는 대상·후보가 돕는 사람"
            if name in taken
            else "앞 요일과 같은 돕는 사람"
            if name in seen
            else ""
        )
        seen.add(name)
        if not why:
            continue
        flagged.append(d["day"])
        old = str(d.get("helper") or "")
        words = [w for w in old.split() if len(w) >= 2] or [old]
        fields = ["helper"] + [
            k
            # 다음 날 오늘 온 까닭의 옛 호칭은 아래에서 따로(#782 설계 v7)
            for k in ("sceneNote", "missionHook", "missionMaterial")
            if any(w in str(d.get(k) or "") for w in words)
        ]
        # #782 설계 v7: 다음 날 오늘 온 까닭에 옛 호칭이 있으면 그 칸도(어제 일은 이름 없이 써도 됨)
        days_all = theme.get("days") or []
        after = days_all[days_all.index(d) + 1] if days_all.index(d) + 1 < len(days_all) else None
        if after and any(w in str(after.get("dayStep") or "") for w in words):
            bad.append(
                f"HELPER_SAME {after['day']} dayStep 어제 돕는 사람 호칭이 바뀜('{old}'): "
                "옛 호칭을 빼고 씀"
            )
        bad += [
            f"HELPER_SAME {d['day']} {k} {why}('{old}'): "
            + (
                "그날 성취기준의 일을 하는 다른 사람으로"
                if helper_use_day(theme, d)
                else "그 장소에 있는 다른 사람으로"
            )
            + " 바꾸고 이 칸의 옛 호칭도 새 호칭으로"
            for k in fields
        ]
    # 사흘 이상이면 칸 고쳐 쓰기로 이야기 절반을 바꾸게 되어(실측 r782-ways-rd4 초3·초4는 칸 18개)
    # 줄거리를 다시 만든다(FIX_REASON에 없는 코드)
    if len(flagged) >= HELPER_REGEN_DAYS:
        return [
            f"HELPER_WEEK 돕는 사람이 {len(flagged)}일({'·'.join(flagged)}) 등장인물이거나 "
            "앞 요일과 같음(요일마다 그날 장소의 다른 사람, 등장인물 아님)"
        ]
    return bad


# 약속 줄 같음 비교에서 뺄 글자(띄어쓰기·문장부호, #782 설계 v13)
PROMISE_PUNCT = re.compile(r"[\s,.!?~·…'\"‘’“”]")


def same_week_promises(theme: Theme, dialogues: dict[str, list[dict]]) -> dict[str, list[str]]:
    """같은 주에 돕는 사람의 약속 줄이 글자 그대로 같은 뒤 요일들과 그 사유(#782 설계 v13).

    요일 대화는 따로 동시에 만들어 서로 못 본다. 같은 감각 요일이 둘이면 "그 일을 도와주면, 그때
    들은 소리를 알려 줄게."처럼 똑같아짐(11·12·13차 매번 1~2건, 저장 결과에서 잘못 잡은 것 0).
    띄어쓰기·문장부호·끝의 '요'만 다르면 같은 줄로 본다."""
    seen: dict[str, str] = {}
    out: dict[str, list[str]] = {}
    for d in theme.get("days") or []:
        day, helper = d.get("day"), str(d.get("helper") or "").strip()
        if mission_way(d) != ASK or not helper:
            continue
        for x in dialogues.get(str(day)) or []:
            text = str(x.get("text") or "")
            if x.get("speaker") != helper or not ASK_PROMISE_VERB.search(text):
                continue
            # 끝의 '요'도 뺌('알려 줄게'·'알려 줄게요'는 같은 줄, 측정 기준과 같은 잣대 — 14차 snd6)
            key = re.sub(r"요$", "", PROMISE_PUNCT.sub("", text))
            if key not in seen:
                seen[key] = str(day)
                continue
            out.setdefault(str(day), []).append(
                f"PROMISE_SAME {day} 약속 줄이 {seen[key]} 요일과 같음('{text}') — "
                f"같은 뜻을 {seen[key]} 요일과 다른 말로"
            )
    return out


def ask_promise_missing(day: dict, lines: list[dict[str, str]]) -> bool:
    """부탁 날 대화에 돕는 사람이 '도와주면 그때 본 걸 알려 줄게'처럼 사건에서 본 것·가진 기록을
    알려 주겠다는 약속이 없는지."""
    helper = str(day.get("helper") or "").strip()
    if mission_way(day) != ASK or not helper:
        return False

    def kept(text: str) -> bool:
        m = ASK_PROMISE_VERB.search(text)
        if not m:
            return False
        # '도와주면 알려 줄게'처럼 알려 줄 것을 따로 말하지 않으면 됨. '~을/를/걸 알려 줄게'처럼
        # 말하면 그것이 본 것·그때·기록이어야 함(실측 '인사말 만들 때 살펴볼 점을'·'고마운 걸')
        names_thing = re.search(r"(?:을|를|걸)\s*$", text[: m.start()])
        return not names_thing or bool(ASK_PROMISE_CASE.search(text))

    return not any(kept(x["text"]) for x in lines if x.get("speaker") == helper)


def kind_fits(kind: StoryType, feature: str | None, evidence: str | None) -> bool:
    """그날 특징을 그 증거 종류로 알 수 있는지. 사실표 특징은 표의 kinds, 그 밖은 흔적만 본다
    (TRACE면 traceable, 목격·기록은 어떤 특징이든 됨 — #535부터의 규칙 그대로)."""
    if not feature:  # 사건 단서(특징 없음)는 어떤 증거 종류로도 씀
        return True
    table = kind.facts
    allowed = table.kinds_of(feature or "") if table is not None else None
    if allowed is not None:
        return evidence in allowed
    return evidence != "TRACE" or traceable(feature, kind)


def fit_evidence_plan(theme: Theme) -> list[str]:
    """흔적 배정을 흔적으로 남을 수 있는 특징의 날로 옮긴다(#535 6차, 요일별 강제 배정은 유지).

    배정은 줄거리보다 먼저 정해지고 특징은 모델이 고르므로, 줄거리를 만든 뒤 흔적 날 특징이 흔적에
    남지 않는 것(빛·소리 등)이면 흔적이 맞는 다른 날(목격 날 먼저, 다음 기록 날)과 배정을 통째로
    바꾼다(기록 매체도 함께 옮김). 맞는 날이 없으면 그 날을 목격으로 바꾼다(요일마다 증거가 섞이는
    목표는 유지, 흔적 0개가 될 수 있음). 바뀐 요일 목록을 돌려주고 evidencePlan을 고친다.
    """
    plan = theme.get("evidencePlan") or {}
    if not plan:
        return []
    feat = {
        d.get("day"): (d.get("condition") or {}).get("feature") for d in theme.get("days") or []
    }
    kind = story_type(theme)
    changed: list[str] = []
    for day in DAYS:
        slot = plan.get(day) or {}
        if kind_fits(kind, feat.get(day), slot.get("kind")):
            continue
        mine = slot.get("kind")
        # 바꿔도 두 날 모두 맞는 날(목격 날 먼저, 다음 기록·흔적 날). 사실표 특징이면 목격·기록 날도
        # 바뀔 수 있음(#634 ②: 소리를 목격 날에 둔 경우)
        order = [
            o
            for k in ("SIGHTING", "RECORD", "TRACE")
            for o in DAYS
            if o != day and (plan.get(o) or {}).get("kind") == k and k != mine
        ]
        swap = next(
            (
                o
                for o in order
                if kind_fits(kind, feat.get(day), (plan.get(o) or {}).get("kind"))
                and kind_fits(kind, feat.get(o), mine)
            ),
            None,
        )
        if swap:
            plan[day], plan[swap] = plan[swap], plan[day]
            # 단서 종류('발자국'은 흔적 날, '목격'·'기록'은 그 날)도 배정을 따라 함께 바꿈
            a, b = theme_day(theme, day), theme_day(theme, swap)
            a["clueType"], b["clueType"] = b.get("clueType"), a.get("clueType")
            changed += [day, swap]
        else:
            # 맞는 짝이 없으면 그 특징으로 알 수 있는 종류로 바꿈(흔적이 아니면 목격 먼저, 기록이면
            # 아직 안 쓴 매체). 요일마다 증거가 섞이는 목표는 유지(구성이 조금 바뀔 수 있음)
            new = next(
                (k for k in ("SIGHTING", "RECORD", "TRACE") if kind_fits(kind, feat.get(day), k)),
                "SIGHTING",
            )
            used_media = {(plan.get(o) or {}).get("medium") for o in DAYS}
            medium = next((m for m in RECORD_MEDIA if m not in used_media), RECORD_MEDIA[0])
            plan[day] = {"kind": new, "medium": medium if new == "RECORD" else None}
            d = theme_day(theme, day)
            used = {x.get("clueType") for x in theme.get("days") or []}
            want = {"SIGHTING": "목격", "RECORD": "기록", "TRACE": "발자국"}[new]
            if d.get("clueType") in ("발자국", "목격", "기록") and want not in used:
                d["clueType"] = want
            changed.append(day)
    theme["evidencePlan"] = plan
    return list(dict.fromkeys(changed))


def fit_media(theme: Theme) -> list[str]:
    """기록 날 매체를 그날 특징에 맞춘다(사실표 media, #634 ⑤ 설계 17.8.18 틈 5).

    배정은 줄거리보다 먼저 정해져 소리 특징 날에 사진이 올 수 있음. 맞지 않으면 다른 날이 쓰지
    않는 맞는 매체로 바꾸고(없으면 맞는 매체 첫째) 바뀐 요일을 돌려준다(그날 단서·증거 발견 줄은
    CLUE_EVIDENCE 칸 고쳐 쓰기).
    """
    plan = theme.get("evidencePlan") or {}
    table = story_type(theme).facts
    if not plan or table is None or not table.media:
        return []
    changed = []
    for d in theme.get("days") or []:
        slot = plan.get(d.get("day")) or {}
        allowed = table.media_of(str((d.get("condition") or {}).get("feature") or ""))
        if slot.get("kind") != "RECORD" or allowed is None or slot.get("medium") in allowed:
            continue
        used = {(plan.get(o) or {}).get("medium") for o in DAYS if o != d.get("day")}
        ordered = [m for m in RECORD_MEDIA if m in allowed]
        slot["medium"] = next((m for m in ordered if m not in used), ordered[0])
        changed.append(d["day"])
    theme["evidencePlan"] = plan
    return changed


def target_words(theme: Theme) -> list[str]:
    """흔적 단서가 누구의 흔적인지 밝힐 때 쓸 찾는 대상 낱말(마지막 낱말과, 이름이면 그 앞 명사).

    동물 주인공 가족은 '동물'로 고정(#634: target이 '눈길에 발자국을 남긴 동물'처럼 설명 글이라
    앞 낱말 '남긴'이 대상 낱말로 뽑혔음, 설계 17.8.5).
    탈것 찾기는 '탈것'·'바퀴'(#634 ④, families.owner_words).
    """
    if owner := story_type(theme).owner_words:
        return list(owner)
    toks = [t for t in re.split(r"\s+", str(theme.get("target") or "").strip()) if t]
    if not toks:
        return []
    words = [toks[-1]]
    if (
        len(toks) >= 2
        and len(toks[-2]) >= 2
        and not re.search(r"(의|께|은|는|한|된|운|던|든|난|큰|작은)$", toks[-2])
        and not _adnominal(toks[-2])
    ):
        words.append(toks[-2])
    return words


PERSON_OF_TARGET = re.compile(r"^\s*(.+?)(?:이|가) 타고 온")


def clue_person(theme: Theme) -> str | None:
    """모든 단서에 넣을 낱말(CLUE_OWNER, 공백 뺀 꼴): 탈것 찾기의 온 사람('삼촌이 타고 온 탈것' →
    '삼촌'), 소리 탐정의 '소리'(families.clue_word). 그 밖·형식 밖은 None."""
    t = story_type(theme)
    if t.clue_word:
        return t.clue_word
    if t.code != "VEHICLE":
        return None
    m = PERSON_OF_TARGET.match(str(theme.get("target") or ""))
    return compact(m.group(1)) if m else None


def _adnominal(word: str) -> bool:
    """꾸미는 말(끝 글자 받침이 ㄴ·ㄹ: '숨긴'·'남긴'·'잃어버릴')인지. 대상 낱말에서 뺀다(#634 작은
    실측: '할아버지가 숨긴 타임캡슐'의 '숨긴'이 대상 낱말이 됨). 받침 ㄴ으로 끝나는 명사('도서관')도
    빠지지만 마지막 낱말이 남아 흔적 단서 검사는 그대로 됨."""
    last = word[-1]
    if not "가" <= last <= "힣":
        return False
    return (ord(last) - 0xAC00) % 28 in (4, 8)  # 받침 ㄴ(4)·ㄹ(8)


def apply_facts(theme: Theme) -> list[str]:
    """사실표 종류(동물·선물·재료)의 특징 표 값을 사실표 값으로 맞춘다(#634, 사실표는 families).

    모델이 지은 동물 특징이 틀려 글 검토 CLUE_LOGIC으로 줄거리를 되풀이했음(1차 작은 실측). 표 밖
    후보·특징은 그대로 두고 check_theme이 FACT_TABLE로 다시 만들게 한다. 값을 바꾼 특징 이름을
    돌려준다(그 특징을 쓰는 날 단서는 칸 고쳐 쓰기).
    """
    table = story_type(theme).facts
    if table is None:
        return []
    changed = []
    for f in theme.get("features") or []:
        name = str(f.get("name") or "")
        old = {str(v.get("candidate")): v.get("value") for v in f.get("values") or []}
        for v in f.get("values") or []:
            fact = table.fact(str(v.get("candidate") or ""), name)
            if fact is not None and v.get("value") != fact:
                v["value"] = fact
                changed.append(name)
        if name not in changed:
            continue
        new = {str(v.get("candidate")): v.get("value") for v in f.get("values") or []}
        # 그 특징을 쓰는 날 허용 값은 '허용하던 후보'의 새 값으로 옮김(빼려던 후보를 그대로 두는
        # 뜻). 겹쳐서 논리가 깨지면 뒤의 repair_logic·check_logic이 봄
        for d in theme.get("days") or []:
            cond = d.get("condition") or {}
            if cond.get("feature") != name:
                continue
            kept = [c for c, val in old.items() if val in (cond.get("allowed") or [])]
            cond["allowed"] = list(dict.fromkeys(str(new[c]) for c in kept if c in new))
    return list(dict.fromkeys(changed))


def fact_table_problems(theme: Theme) -> list[str]:
    """후보·특징이 사실표 안인지, 값이 표 값인지(FACT_TABLE, 줄거리 다시 생성)."""
    table = story_type(theme).facts
    if table is None:
        return []
    bad = []
    outside = [c for c in theme.get("candidates") or [] if c.strip() not in table.rows]
    if outside:
        bad.append(
            f"FACT_TABLE 후보 {outside}는 {table.name} 사실표 밖(표 이름 그대로: "
            f"{list(table.rows)})"
        )
    names = [f.get("name") for f in theme.get("features") or []]
    if odd := [n for n in names if n not in table.features]:
        bad.append(
            f"FACT_TABLE 특징 {odd}는 {table.name} 사실표 밖"
            f"(표 특징 이름 그대로: {list(table.features)})"
        )
    wrong = [
        f"{f.get('name')}·{v.get('candidate')}"
        for f in theme.get("features") or []
        for v in f.get("values") or []
        if (fact := table.fact(str(v.get("candidate") or ""), str(f.get("name") or "")))
        and v.get("value") != fact
    ]
    if wrong:
        bad.append(f"FACT_TABLE 특징 값이 사실표와 다름 {wrong}")
    # 한 범주(#634 ⑤ 이슈 결정: 소리 탐정 후보는 동물만 또는 물건만)
    kinds = {table.group(c) for c in theme.get("candidates") or [] if table.group(str(c))}
    if table.groups and len(kinds) > 1:
        bad.append(
            f"SAME_KIND 후보 {theme.get('candidates')}가 여러 범주({sorted(kinds)})에 걸침(한 "
            "범주에서만 4개)"
        )
    # 코드가 정한 후보 4개·정답(plan_theme 내부 칸 candidatePlan, 같은 씨앗). 사실표가 있는 모든
    # 종류(#782, 처음에는 소리 탐정만 — #634 ⑤)
    plan = theme.get("candidatePlan") or {}
    if (
        plan
        and len(kinds) <= 1
        and (
            sorted(str(c).strip() for c in theme.get("candidates") or [])
            != sorted(plan.get("candidates") or [])
            or str(theme.get("answer") or "").strip() != plan.get("answer")
        )
    ):
        bad.append(
            f"SAME_KIND 후보·정답이 정해진 것과 다름(candidates {plan.get('candidates')}, "
            f"answer {plan.get('answer')} 그대로)"
        )
    # 소리 탐정(strict_facts): 후보끼리 값이 모두 같은 특징은 단서가 될 수 없고 시작 이야기의
    # '밤마다'가 그 단서를 앞질러 말함(⑤ 판정 실측 글 검토 ANSWER_HINT: 동물 후보의 '매일 밤')
    if story_type(theme).strict_facts:
        cands = [str(c).strip() for c in theme.get("candidates") or []]
        used = [n for n in names if n in table.features]
        if flat := [f for f in flat_features(table, cands) if f in used]:
            bad.append(
                f"FACT_TABLE 특징 {flat}는 후보 {cands}의 값이 모두 같아 단서가 될 수 없음"
                "(features에서 뺌)"
            )
    # 정답을 다른 후보와 있는 값 특징만으로 가를 수 있어야 함(#634 ④: 없는 값은 단서로 못 쓰고,
    # 모든 값이 같은 후보(오전 10시·오후 3시)는 정답을 가릴 수 없음)
    answer = str(theme.get("answer") or "").strip()
    used = [n for n in names if n in table.features]
    if answer in table.rows and used:
        stuck = [
            c.strip()
            for c in theme.get("candidates") or []
            if c.strip() != answer
            and c.strip() in table.rows
            and not table.separable(answer, c.strip(), used)
        ]
        if stuck:
            note = f", 없는 값 {sorted(table.absent)}은 단서로 못 씀" if table.absent else ""
            bad.append(
                f"FACT_TABLE 정답 {answer}을 후보 {stuck}와 features {used}의 있는 값만으로 가를 "
                "수 "
                f"없음{note}(후보를 바꾸거나 가를 특징을 features에 넣음)"
            )
    return bad


def outro_other_candidates(theme: Theme) -> list[str]:
    """시간 탐정 마무리 장면(outroStory)에 나온 정답 아닌 후보 시각(OUTRO_ANSWER, 칸 고쳐 쓰기).

    코드 정리는 정답만 남았다고 하는데 모델의 마무리 장면이 다른 시각을 확인해 모순(④ 판정 실측:
    정답 오전 10시인데 '사서가 낮 12시라고 확인'). 정답 이름을 지운 뒤 다른 후보 이름·머리
    낱말('7시')을 찾는다(정답 '저녁 7시'와 후보 '아침 7시'처럼 머리 낱말이 같으면 정답을 다 써야
    통과).
    """
    if not story_type(theme).outro_check or "outroStory" not in theme:
        return []
    answer = compact(theme.get("answer"))
    text = compact(theme.get("outroStory")).replace(answer, "") if answer else ""
    found = []
    for c in theme.get("candidates") or []:
        if compact(c) == answer:
            continue
        words = [compact(c), *[compact(t) for t in str(c).split()[-1:]]]
        if any(w and w in text for w in words):
            found.append(str(c).strip())
    return found


def flat_features(table: Any, cands: list[str]) -> list[str]:
    """그 후보들의 값이 모두 같은 사실표 특징(표 밖 후보가 있으면 빈 목록)."""
    if not cands or any(c not in table.rows for c in cands):
        return []
    return [f for f in table.features if len({table.fact(c, f) for c in cands}) == 1]


def clue_absent_problems(theme: Theme) -> list[str]:
    """단서 조건에 '없는 값'(CLUE_ABSENT, 줄거리 다시 생성). 그날 특징을 바꿔야 해서 문장만 고쳐
    쓰는 것으로는 못 고침(#634 ④ 설계 17.8.17)."""
    table = story_type(theme).facts
    if table is None or not table.absent:
        return []
    bad = []
    for d in theme.get("days") or []:
        cond = d.get("condition") or {}
        if hits := [a for a in cond.get("allowed") or [] if a in table.absent]:
            bad.append(
                f"CLUE_ABSENT {d['day']} 단서 조건에 없는 값 {hits}(무엇이 없다는 말은 근거가 "
                "약함 — 정답의 값이 있는 값인 특징으로 단서를 씀)"
            )
    return bad


def place_problems(theme: Theme) -> list[str]:
    """장소가 맞아야 둘 수 있는 후보(VEHICLE_PLACE: 여객선은 물가에서만, 줄거리 다시 생성)."""
    t = story_type(theme)
    if not t.place_needs:
        return []
    text = " ".join(
        [
            str(theme.get("world") or ""),
            intro_story(theme),
            *(str(d.get("place") or "") for d in theme.get("days") or []),
        ]
    )
    cands = [str(c).strip() for c in theme.get("candidates") or []]
    return [
        f"VEHICLE_PLACE 후보 {name}은 물가 장소에서만(world·intro에 바다·강가·항구 같은 물가 말이 "
        "없음 — 후보를 바꾸거나 물가 장소로)"
        for name, need in t.place_needs
        if name in cands and not need.search(text)
    ]


# 시간 탐정(#634 ④): 그때가 곧 정답이라 엔딩 전 글의 어떤 시각도 답을 흘림(후보 시각이 아니어도
# '오전 9시 수업'처럼 시각을 쓰면 후보와 견주게 됨). 숫자 시각, 우리말 시각('세 시'), 정오·자정.
# '2시간'·'두 시장'처럼 시각이 아닌 말은 뒤 글자로 뺌
TIME_WORD = re.compile(
    r"\d{1,2}\s?시(?![가-힣])|\d{1,2}\s?시(?=[에쯤부까였반의엔가이도])"
    r"|(?<![가-힣])(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|열한|열두)\s?시"
    r"(?=\s|$|[에쯤부까였반의엔가이도,.!?])"
    r"|정오|자정"
)
# #782 설계 v10: 시간 탐정 단서의 '시각'·'몇 시'(숫자가 없어도 시각이 적힌 기록이라는 말).
# '몇 시간'은 뺌
CLOCK_MENTION = re.compile(r"시각|몇\s?시(?!간)")


# #782 설계 v4: 시간 탐정 시작 이야기는 그 일을 알아챈 그날이라 때를 가리키는 말이 정답 시각과
# 어긋나거나 미리 알려 줌(3차 way5b "점심을 먹고 온 아이가 먹이 준 일이 끝난 걸 앎"인데 정답 오후
# 3시). 다른 요일 장면의 '아침에'는 다른 날이라 그대로 둠
DAYPART = re.compile(r"아침|점심|저녁|오전|오후|새벽|해 질|해가 지|(?<![가-힣])낮|(?<![가-힣])밤")
# #782 설계 v4: 소리 탐정의 '밤마다'는 특징 '소리 나는 밤' 값(매일 밤·비 오는 밤·바람 부는 밤)을
# 미리 말하거나 어긋남(3차 snd4: 시작 "손님들도 밤마다 들었다" 뒤 단서 "매일 밤 났다")
# 표 값 낱말('매일 밤' 등)은 기존 검사(ANSWER_FACT·strict_facts)가 잡으므로 같은 뜻의 말만. 후보가
# 모두 같은 값이면(동물은 모두 '매일 밤') 말해도 아무것도 알려 주지 않아 보지 않음
SOUND_NIGHT = re.compile(r"밤마다|날마다|매일매일")
# #782 설계 v4: 관리실에 맡겨 둔 대상인데 다른 곳에 맡겼다고 씀(3차 hand6b "준비실에 맡겼다")
KEPT_AT = re.compile(r"([가-힣]+)에\s?맡(?:겼|겨|긴|김)")
KEPT_FIELDS = ("clue", "sceneNote", "discovery", "missionMaterial", "missionHook")


def normalize_sound_target(theme: Theme) -> Theme:
    """소리 탐정 대상 글은 주제 글('밝힐 것')을 그대로 쓰는 칸이라 '밤마다'(특징 '소리 나는 밤' 값을
    미리 말함)를 코드가 '밤에'로 바꾼다(#782 설계 v4, 제자리). 씨앗은 learning에서 '밤에'로 고쳤고
    관리자 자유 글·예전 씨앗을 위해 둔다."""
    if story_type(theme).code == "SOUND":
        theme["target"] = SOUND_NIGHT.sub("밤에", str(theme.get("target") or ""))
    return theme


# #782 설계 v6: 맡겨 둔 대상은 맡기기 전에 그것을 줍거나 나르거나 맡긴 사람만 살필 수 있음(4차 측정
# hand5b: 분실물 선반의 장갑을 거리의 목수가 "내가 보니"로 살핌)
KEPT_TRACE_WHEN = re.compile(
    r"맡겨지기 전|맡기기 전|맡길 때|주울 때|주웠|배달|날랐|나를 때|나르|건넬|건넸|가져올|가져왔"
    r"|받을 때|받았을 때"
)
# 대상 물건 자체를 말하는 특징(맡긴 뒤에는 맡긴 곳 사람만 봄). 길바닥·대문·창문처럼 온 곳·
# 지나온 길의 특징은 아님(길 종류는 흔적 표에 바닥·재질도 있어 종류별 흔적 표로는 못 가름)
OBJECT_SELF_FEATURE = re.compile(
    r"묻은|밴|가루|무게|소리|냄새|향|틈|밑면|포장|매듭|붙은|끈|안쪽|완충재|흙빛|느낌"
)
# 단서 문장이 대상에 묻은·붙은·밴 것을 말하는 꼴(특징 이름이 '바닥 재질'이어도 "털장갑 털 사이
# 알갱이"·"털장갑 밑면의 흙"이면 대상 자체를 살핀 것 — 4차 hand5b)
OBJECT_ON = re.compile(r"묻은|묻어|묻었|붙은|붙어|밴 |배어|틈|털 사이|밑면|안쪽|겉면|표면")
# v7: 돕는 사람이 자기가 맡겼다고 하면 다른 날 맡긴 사람과 부딪힘(5차 hand6b: 월요일 "선생님이
# 맡기는 걸 봤어" ↔ 수요일 "내가 맡기기 전에")
# v8: '내가 맡아 두며·두고'(손에 든 것 종류 예시가 이 꼴이었음)
KEPT_SELF = re.compile(r"(?:내가|제가) (?:맡아 ?(?:둔|뒀|두었|놓은|놨|두며|두고)|맡기|맡겼)")
# #782 설계 v12: 출처 찾기 물건은 시작 이야기의 다른 사람(관리실 직원·선생님)이 주워 맡겼는데 돕는
# 사람이 자기가 줍거나 날랐다고 함(9차 hand5b '맡기기 전에 내가 털장갑을 나르며 맡아 보니'·hand6
# '내가 옮기며 보니' — 저장 결과 7·8·9차에서 5건 모두 실제 충돌, 잘못 잡은 것 0)
KEPT_CARRY = re.compile(
    r"(?:내가|제가)[^!?.]{0,20}(?:나르|날라|날랐|주워|주웠|주운|들고\s?(?:가|오|와)|옮기|옮겼)"
)
# #782 설계 v6: 아이가 직접 발견한 발자국은 흐릿해야 그 모양을 단서로 받는 게 말이 됨(4차
# new4b·new5)
SEEN_BLUR = re.compile(r"지워|뭉개|흐릿|흐려|알아보기 어렵|알아볼 수 없|반쯤|희미")
# #782 설계 v7: 잃어버린 것·보물 쪽지 시작 이야기에는 몇 시를 쓰지 않음(INTRO_CLOCK). v6
# EVENT_TIME은 시작 이야기의 첫 시각을 '알아챈 때'로 봤는데 "10시 25분 알아챔·10시 20분 무렵
# 놓침"이 같이 있거나 증거가 "9시가 되기 전"이면 맞는 글을 잡았음(5차 오탐 3, auto5 7번 걸려
# 마감). 시각은 증거 칸에만 두면 알아챈 때와 엇갈릴 수 없음(4차 new5b)
CLOCK = re.compile(r"(?<!\d)(\d{1,2})\s?시(?!간)(?:\s?(\d{1,2})\s?분)?")
# v8: '오후 세 시'처럼 한글 수도
KO_CLOCK = re.compile(
    r"(?<![가-힣])(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|열한|열두)\s?시(?![간작])"
)


def object_self_trace(theme: Theme, day: dict) -> bool:
    """맡겨 둔 대상 자체의 흔적 단서인지(#782 설계 v6): 맡겨 두는 종류 + 부탁 날 + 흔적 + 대상
    물건 특징."""
    feature = str((day.get("condition") or {}).get("feature") or "")
    clue = str(day.get("clue") or "")
    return (
        kept_target(theme)
        and mission_way(day) == ASK
        and (day.get("evidence") or {}).get("kind") == "TRACE"
        and (
            bool(OBJECT_SELF_FEATURE.search(feature))
            or (names_target(theme, clue) and bool(OBJECT_ON.search(clue)))
        )
    )


def kept_trace_problems(theme: Theme) -> list[str]:
    """맡겨 둔 대상을 지금 살핀 것처럼 쓴 흔적 단서(KEPT_TRACE)·다른 사람이 맡아 둔 말
    (KEPT_PLACE)."""
    if not kept_target(theme):
        return []
    bad = []
    for d in theme.get("days") or []:
        clue = str(d.get("clue") or "")
        if object_self_trace(theme, d) and not KEPT_TRACE_WHEN.search(clue):
            bad.append(
                f"KEPT_TRACE {d['day']} clue 관리실에 맡겨 둔 대상을 지금 살핀 것처럼 씀(맡겨지기 "
                "전에 본 것으로, '맡겨지기 전에 내가 보니 ~')"
            )
        if (
            story_type(theme).code == "ORIGIN"
            and theme_branch(theme) != "동물"
            and KEPT_CARRY.search(clue)
        ):
            bad.append(
                f"KEPT_CARRY {d['day']} clue 물건은 시작 이야기의 사람이 주워 맡겼는데 돕는 사람이 "
                "자기가 줍거나 날랐다고 씀(맡겨지기 전에 그 물건이 놓여 있을 때나 주운 사람이 들고 "
                "지날 때 곁에서 본 것으로, '맡겨지기 전에 그 ○○가 놓여 있을 때 보니 ~')"
            )
        if KEPT_SELF.search(clue) and "관리실" not in str(d.get("helper") or ""):
            bad.append(
                f"KEPT_PLACE {d['day']} clue 대상은 관리실에 맡겨 두었는데 돕는 사람이 자기가 맡아 "
                "두었거나 맡겼다고 씀(맡긴 곳은 관리실, 돕는 사람은 맡겨지기 전에 본 사람)"
            )
    return bad


def seen_trace_problems(theme: Theme) -> list[str]:
    """동물 종류 시작 이야기·사건에서 아이가 본 발자국이 또렷하면(SEEN_TRACE, 칸 고쳐 쓰기)."""
    if story_type(theme).code not in ("PRANK", "FOOTPRINT"):
        return []
    fields = (("intro", intro_story(theme)), ("incident", str(theme.get("incident") or "")))
    return [
        f"SEEN_TRACE {key}에 아이가 본 발자국이 또렷함(반쯤 지워지거나 뭉개져 모양을 알아볼 수 "
        f"없게 "
        "— 또렷한 모양은 먼저 본 사람이 알려 주는 단서)"
        for key, text in fields
        if "발자국" in text and not SEEN_BLUR.search(text)
    ]


def intro_clock_problems(theme: Theme) -> list[str]:
    """잃어버린 것·보물 쪽지 시작 이야기(모델 몫)에 몇 시가 있으면(INTRO_CLOCK, 시작 이야기 고쳐
    쓰기, #782 설계 v7)."""
    if story_type(theme).code not in ("LOST", "TREASURE"):
        return []
    found = CLOCK.search(intro_story(theme)) or KO_CLOCK.search(intro_story(theme))
    return (
        [
            f"INTRO_CLOCK intro에 몇 시('{found.group(0)}')를 씀(이 종류의 시작 이야기에는 "
            "시각을 쓰지 않음 — 시각은 증거 칸에만, 오후·저녁 같은 말은 됨)"
        ]
        if found
        else []
    )


def intro_story_problems(theme: Theme) -> list[str]:
    """시작 이야기·큰 질문이 그날 단서 특징을 미리 말하거나 어긋나는 꼴(칸 고쳐 쓰기, #782 v4)."""
    t = story_type(theme)
    bad = []
    # 모델 몫(introStory)이 따로 있을 때만 봄(합친 intro에는 코드가 붙인 마을 규칙 '오후 7시')
    if t.hide_times and "introStory" in theme and (m := DAYPART.search(intro_story(theme))):
        bad.append(
            f"TIME_WORD intro에 때를 가리키는 말 '{m.group()}'(시작 이야기는 그 일을 알아챈 때를 "
            "말하지 않음 — 정답 시각과 어긋나거나 미리 알려 줌)"
        )
    nights = feature_table(theme)[0].get("소리 나는 밤") or {}
    if t.code == "SOUND" and len(set(nights.values())) > 1:
        for key in ("intro", "bigQuestion"):
            text = intro_story(theme) if key == "intro" else str(theme.get(key) or "")
            if m := SOUND_NIGHT.search(text):
                bad.append(
                    f"SOUND_NIGHT {key}에 '{m.group()}'(어느 밤에 나는지가 단서 특징이라 "
                    f"'밤에'로만)"
                )
    if kept_target(theme):
        for d in theme.get("days") or []:
            for key in KEPT_FIELDS:
                text = str(d.get(key) or "")
                m = KEPT_AT.search(text)
                # 찾는 대상 낱말이 함께 있을 때만(지문의 '가방을 사물함에 맡겼다' 같은 딴
                # 이야기 제외)
                if m and "관리실" not in m.group(1) and names_target(theme, text):
                    bad.append(
                        f"KEPT_PLACE {d['day']} {key} 대상은 관리실에 맡겨 두었는데 "
                        f"'{m.group(0)}'(다른 곳에 맡겼다고 쓰지 않음)"
                    )
    return bad


def time_word_problems(theme: Theme) -> list[str]:
    """시각을 감추는 종류(시간 탐정)의 엔딩 전 글·단서에 시각(TIME_WORD, 칸 고쳐 쓰기)."""
    if not story_type(theme).hide_times:
        return []
    fields = [*candidate_name_fields(theme)]
    fields += [(f"{d['day']}.clue", str(d.get("clue") or "")) for d in theme.get("days") or []]
    bad = []
    for path, text in fields:
        if m := TIME_WORD.search(text):
            bad.append(
                f"TIME_WORD {path}에 시각 '{m.group()}'(그때가 정답이라 엔딩 전 글에 시각을 "
                "쓰지 않음 — '그 일을 할 때'·'아침에'처럼)"
            )
        # #782 설계 v10: 단서에 시각이 적혔다는 말('일지에 그 시각이 적혀 있어')도 그때를 바로 알려
        # 주는 기록이라 시간 탐정 단서에 쓰지 않음(숫자 시각이 없어도)
        elif path.endswith(".clue") and (m := CLOCK_MENTION.search(text)):
            bad.append(
                f"TIME_WORD {path}에 시각이 적혔다는 말 '{m.group()}'(그때가 정답이라 시각이 적힌 "
                "기록이면 단서 없이 풀림 — 그때 보이거나 들린 것으로)"
            )
    return bad


def answer_facts(theme: Theme) -> list[str]:
    """정답만 가진 사실표 값(다른 후보 누구도 같은 특징에서 그 값을 갖지 않음). 엔딩 전 글에 나오면
    단서 없이 정답이 보인다(#634 ② 설계: '분홍빛 떡'이면 딸기, ANSWER_FACT)."""
    table = story_type(theme).facts
    answer = str(theme.get("answer") or "").strip()
    cands = [str(c).strip() for c in theme.get("candidates") or []]
    if table is None or answer not in table.rows:
        return []
    out = []
    for feature in table.features:
        mine = table.fact(answer, feature)
        others = {table.fact(c, feature) for c in cands if c != answer}
        if mine and mine not in others:
            out.append(mine)
    return out


def secret_values(theme: Theme) -> list[str]:
    """엔딩 전 글·미션·대화에 쓰지 않는 표 값. 보통은 정답만의 값(answer_facts), 소리 탐정처럼
    strict_facts인 종류는 그 테마 후보끼리 값이 갈리는 표 값 전부(후보 모두 같은 값은 정보가 없어
    허용, #634 ⑤ 설계 17.8.18 틈 4)."""
    t = story_type(theme)
    table = t.facts
    if table is None or not t.strict_facts:
        return answer_facts(theme)
    cands = [str(c).strip() for c in theme.get("candidates") or [] if str(c).strip() in table.rows]
    out: list[str] = []
    for feature in table.features:
        vals = [table.fact(c, feature) for c in cands]
        if len(set(vals)) > 1:
            out += [v for v in dict.fromkeys(vals) if v]
    return out


def answer_fact_hits(theme: Theme, text: str | None) -> list[str]:
    return [v for v in secret_values(theme) if compact(v) in compact(text)]


# 보물 쪽지(#634 ①): 숨긴 곳은 끝까지 모르는 답인데 엔딩 전 글이 '숨긴 자리에서 흔적을 찾았다'처럼
# 이미 아는 듯이 써서 글 검토 CLUE_LOGIC(1차 판정 2회 8번 중 7번이 보물 쪽지)
HIDE_SPOT = re.compile(r"숨(?:긴|겨 ?둔|겨 ?놓은) ?(?:자리|곳|장소|위치)")


# 산 가게 단서는 그 가게에서 '샀다'는 근거가 있어야 함(#634 ② 작은 실측 1~3차: "가게에 간·나온
# 모습만으로는 거기서 샀다는 근거가 없음"이 되풀이, 프롬프트로 좁혀도 남아 코드 검사로)
BUY_WORDS = re.compile(r"샀|사는|사 가|사 오|사러|사서|계산|영수증|스티커|구입|주문")
# 산 가게 특징과 단서에 꼭 있어야 할 산 물건 낱말. 마지막 확인에서 '상자를 산 가게'로 읽혀 글 검토
# CLUE_LOGIC("상자를 산 가게는 선물을 산 가게를 가르는 근거가 아님") → 특징 이름·단서에 산 물건을
# 밝힘
PROOF_FEATURES = {"선물을 산 가게": "선물", "재료를 산 가게": "재료"}


def clue_proof_problems(theme: Theme) -> list[str]:
    """산 가게 단서에 산 근거 말·산 물건 낱말이 없으면(CLUE_PROOF, 칸 고쳐 쓰기)."""
    if story_type(theme).facts is None:
        return []
    bad = []
    for d in theme.get("days") or []:
        feature = (d.get("condition") or {}).get("feature")
        if feature not in PROOF_FEATURES:
            continue
        clue = str(d.get("clue") or "")
        if not BUY_WORDS.search(clue):
            bad.append(
                f"CLUE_PROOF {d['day']} clue 산 가게 단서에 그 가게에서 산 근거(샀다·계산·영수증·"
                "스티커)가 없음(가게에 간·나온 모습만으로는 근거가 안 됨)"
            )
        elif (thing := PROOF_FEATURES[feature]) not in clue:
            bad.append(
                f"CLUE_PROOF {d['day']} clue 산 가게 단서에 '{thing}' 낱말이 없음(상자·다른 물건이 "
                f"아니라 {thing}을 산 가게임을 밝힘)"
            )
    return bad


def hide_spot_problems(theme: Theme) -> list[str]:
    """보물 쪽지 엔딩 전 글에 '숨긴 자리·숨긴 곳'(HIDE_SPOT, 칸 고쳐 쓰기)."""
    bad = []
    for d in theme.get("days") or []:
        for k in ("sceneNote", "discovery", "clue", "missionHook", "missionMaterial"):
            if m := HIDE_SPOT.search(str(d.get(k) or "")):
                bad.append(
                    f"HIDE_SPOT {d['day']} {k} 숨긴 곳은 아직 모르는데 '{m.group()}'이라고 씀"
                    "(보물을 들고 지나간 길·잠시 내려놓은 자리로)"
                )
    return bad


def names_target(theme: Theme, text: str | None) -> bool:
    """글에 찾는 대상 낱말이 있는지(한 글자 낱말은 낱말 첫머리만, mentions_value와 같은 규칙).

    한 글자 낱말을 대상 이름의 다른 낱말과 붙여 쓴 꼴도 인정한다('떡 모양 틀'의 '떡틀'·
    '모양틀', #535 7차 auto3d 오탐). 대상 이름에 있는 낱말과 붙은 것만 보므로 '볼게'의 '게'
    같은 말은 그대로 뺀다.
    """
    toks = [t for t in re.split(r"\s+", str(theme.get("target") or "").strip()) if t]
    for w in target_words(theme):
        if len(w) == 1:
            if re.search(rf"(?<![가-힣]){re.escape(w)}", text or ""):
                return True
            if any(compact(t + w) in compact(text) for t in toks if t != w):
                return True
        elif compact(w) in compact(text):
            return True
    return False


def candidate_words(theme: Theme) -> list[str]:
    """후보 이름과 머리 낱말('옆집 고양이' → '옆집 고양이'·'고양이'). 동물 주인공 가족 검사용."""
    words: list[str] = []
    for c in theme.get("candidates") or []:
        toks = [t for t in re.split(r"\s+", str(c).strip()) if t]
        words += [str(c).strip(), *toks[-1:]]
    return list(dict.fromkeys(w for w in words if w))


def candidate_names(theme: Theme, text: str | None) -> list[str]:
    """글에 나온 후보 이름·머리 낱말(#634 ③: 엔딩 전 글에 후보 동물을 내지 않음).

    두 글자 이상은 공백을 뺀 글에서 찾고, 한 글자 낱말('쥐'·'새')은 앞뒤가 다른 글자와 붙지 않은
    꼴(조사는 허용)만 본다('개울'·'소리'의 '개'·'소'는 빼려고).
    """
    found = []
    for w in candidate_words(theme):
        if len(compact(w)) == 1:
            pattern = (
                rf"(?<![가-힣]){re.escape(w)}(?:이|가|은|는|을|를|도|의|와|과|랑|야)?(?![가-힣])"
            )
            hit = re.search(pattern, text or "") is not None
        else:
            hit = compact(w) in compact(text)
        if hit:
            found.append(w)
    return found


# 낱말 뒤에 붙어도 같은 낱말로 보는 조사(#765 cut_names_target). 길게 붙는 것부터 시도함
JOSA = (
    r"(?:에서|에게|한테|처럼|까지|부터|이랑|으로|이나"
    r"|이|가|은|는|을|를|도|의|와|과|랑|만|에|로|나)?"
)


def cut_target_word(theme: Theme, text: str | None) -> str | None:
    """콘티 컷 설명에 나온 찾는 대상 이름·낱말(#765 CUT_TARGET), 없으면 None.

    대상 전체 이름(공백 무시), 대상 마지막 낱말이 한 낱말로 쓰인 것(뒤에 조사만 허용), 그 앞
    낱말(target_words, 꾸미는 말 빼고 — '강아지 보리'의 '강아지')은 뒤에 조사가 붙은 것만 본다.
    흔적 단서용 names_target처럼 공백을 뺀 글 안을 찾으면 '체험 배지'의 '체험'이 '체험관'에, '관찰
    통'의 '통'이 '통통'에 걸렸고, 앞 낱말을 조사 없이도 보면 '나무 이름표'의 '나무'가 수목원 장면
    '나무 사이의 빈 길'에, '전시 그림'의 '전시'가 '전시 담당 선생님'에 걸렸다(#535 실측 줄거리).
    """
    target = str(theme.get("target") or "").strip()
    if not target or not text:
        return None
    if compact(target) in compact(text):
        return target
    head, *front = target_words(theme)
    josa = JOSA.removesuffix("?")  # 앞 낱말은 조사가 꼭 붙어야
    for w, after in ((head, JOSA), *((w, josa) for w in front)):
        if re.search(rf"(?<![가-힣]){re.escape(w)}{after}(?![가-힣])", text):
            return w
    return None


def cut_names_target(theme: Theme, text: str | None) -> bool:
    return cut_target_word(theme, text) is not None


def cut_target_problems(theme: Theme) -> list[str]:
    """그림에 나오면 안 되는 대상·후보 이름이 콘티 scene·action에 있는지(#765, 칸 고쳐 쓰기).

    컷 설명은 그 컷 첫 그림·영상 지시와 그림 검토 SCENE_FIT에 그대로 들어가, 대상이 나오면 안 되는
    컷에 '강아지가 … 서 있다'고 쓰면 그리면 ANSWER_HINT, 안 그리면 SCENE_FIT으로 어느 쪽도 통과하지
    못한다(운영 2026-11-18 OUTRO2). 대상: 잃어버린 것·보물 쪽지는 target_cuts 밖 컷의 대상 이름,
    사실표 종류는 answer_cuts 밖 종료 컷의 후보 이름(families.StoryType.hidden_*_cuts).
    """
    t = story_type(theme)
    bad = []
    for scene, key in (("INTRO", "introCuts"), ("OUTRO", "outroCuts")):
        hidden = type_cuts(t, len(theme.get(key) or []) or CUTS)  # #779 컷 수에 맞춘 컷 번호
        for i, cut in enumerate(theme.get(key) or [], 1):
            for k in ("scene", "action"):
                text = str(cut.get(k) or "")
                if (scene, i) in hidden.hidden_target and (word := cut_target_word(theme, text)):
                    bad.append(
                        f"CUT_TARGET {key}{i}.{k} 대상이 나오지 않는 컷에 찾는 대상 낱말 "
                        f"'{word}'(없다는 말도 쓰지 않음)"
                    )
                if (scene, i) in hidden.hidden_candidate and (
                    names := candidate_names(theme, text)
                ):
                    bad.append(f"CUT_TARGET {key}{i}.{k} 후보가 나오지 않는 컷에 후보 이름 {names}")
                # #779: 동물을 뺀 종료 컷(target_off_cuts)에 '동물'로 쓰면 이름 검사를 지나가 그
                # 컷 그림에 동물이 나왔음(5차 콘티 종료 6컷 "동물이 길을 향한다")
                elif (scene, i) in t.target_off_cuts and (
                    word := next((w for w in t.owner_words if w in text), None)
                ):
                    bad.append(
                        f"CUT_TARGET {key}{i}.{k} 동물이 나오지 않는 컷에 '{word}'(이미 떠남)"
                    )
    return bad


def candidate_name_fields(theme: Theme) -> list[tuple[str, str]]:
    """동물 주인공 가족에서 엔딩 전에 보이는 글 칸 [(경로, 글)](종료 이야기·종료 콘티·단서 빼고).

    단서는 학생이 그날 미션을 마친 뒤 보고 후보 목록과 함께 나오므로 뺀다(설계 17.8.5).
    """
    fields = [
        (k, intro_story(theme) if k == "intro" else str(theme.get(k) or ""))
        for k in (
            "title",
            "world",
            "intro",
            "bigQuestion",
            "styleNote",
            "outfit",
            "incident",
            "introPlace",
        )
    ]
    fields += [
        (f"{d['day']}.{k}", str(d.get(k) or ""))
        for d in theme.get("days") or []
        for k in (
            "place",
            "sceneNote",
            "discovery",
            "missionHook",
            "missionMaterial",
            "dayStep",
            "helper",
        )
    ]
    fields += [
        (f"characters.{c.get('name')}", f"{c.get('name') or ''} {c.get('look') or ''}")
        for c in theme.get("characters") or []
    ]
    fields += [
        (f"introCuts{i + 1}.{k}", str(c.get(k) or ""))
        for i, c in enumerate(theme.get("introCuts") or [])
        for k in ("scene", "action", "caption")
    ]
    return fields


def day_text_max(day: dict, key: str, theme: Theme | None = None) -> int:
    """요일 글 칸 상한. 흔적 날 단서는 대상 낱말을 넣으므로 TRACE_CLUE_MAX(기준안). #782 설계
    v8: 모든 단서에 온 사람·'소리' 낱말이 필요한 종류(탈것·소리 탐정, clue_person)도 같은 상한
    (빠지는 값 둘 + 사람 낱말 + '내 녹음에'를 넣으면 40자를 넘음)."""
    if key == "clue" and (
        (day.get("evidence") or {}).get("kind") == "TRACE"
        or (theme is not None and clue_person(theme))
    ):
        return TRACE_CLUE_MAX
    return TEXT_MAX[key]


def intro_story(theme: Theme) -> str:
    """시작 이야기의 모델 몫(코드가 끝에 붙이는 규칙 문장 빼고). 엔딩 전 글 검사는 이것을 본다(마을
    규칙의 '낮 12시'·'오전 9시'가 후보 시각·정답 이름 검사에 걸리지 않게)."""
    return str(theme.get("introStory", theme.get("intro")) or "")


def compose_intro(theme: Theme) -> Theme:
    """시작 이야기 = 모델 몫 + 종류 규칙 문장(#634 ④ 시간 탐정 마을 규칙, families.intro_notes).

    규칙 문장의 말투는 모델 몫 끝에 맞춘다('…요.'면 '켜져요.', '…다.'면 '켜진다.', 그 밖은 '켜져.',
    종료 이야기 정리와 같은 방식). introStory가 없으면(사람이 쓴 테마·규칙 없는 종류) 그대로 둔다.
    """
    notes = story_type(theme).intro_notes
    if not notes or "introStory" not in theme:
        return theme
    story = str(theme.get("introStory") or "").strip()
    for note in notes:  # 모델이 규칙을 옮겨 써도 한 번만 붙게
        story = story.replace(note, "").strip()
    theme["introStory"] = story
    if re.search(r"요[.!?]?$", story):
        note = notes[0]
    elif re.search(r"다[.!?]?$", story):
        note = notes[1]
    else:
        note = notes[2]
    theme["intro"] = f"{story} {note}".strip()
    return theme


# #782 설계 v7(사용자 결정 2026-11-22): 오늘 온 까닭은 모델이 "오늘 여기 온 까닭"으로 쓴다. 코드
# 문장(v3)은 한 주가 같은 꼴이라 사용자가 거절했고("너무 똑같이 반복"), 어제 돕는 사람 이름을
# 꼭 넣게 한 v5는 그 사람이 하지 않은 부탁·소개·지시를 지어냈다(5차 화~금 92줄 중 들은 것만
# 말한 줄 10). 코드 문장은 빈 칸(예전 저장본)·두 번 고쳐도 걸릴 때·대화 첫 줄로 못 쓸 때만.
# 앞 요일 단서 결과는 말하지 않음(PREV_CLUE와 같은 뜻)
DAY_STEP_LATER = (
    "어제 들은 걸 떠올리며 {p}{ro} 와 봤어.",
    "{p}에서도 본 사람이 있을지 몰라 와 봤어.",
    "{p}{ro} 가면 더 알 수 있을 것 같았어.",
)


def day_step_text(theme: Theme, index: int) -> str:
    """그날 코드 오늘 온 까닭(월: 조사 시작, 화~금: 요일마다 다른 꼴). 40자 안이고 그날·앞 요일
    단서 값을 말하지 않는 꼴 중 첫 것. 장소 이름에 단서 값이 있으면 장소를 뺀 꼴."""
    days = theme.get("days") or []
    d = days[index]
    place = str(d.get("place") or "").strip()
    limit = TEXT_MAX["dayStep"]
    if index == 0:
        # #782 설계 v4: 모델이 쓴 대상 글은 넣지 않음(3차 way3b)
        options = [f"{place}에서 조사를 시작했어.", "오늘부터 조사를 시작했어."]
    else:
        form = DAY_STEP_LATER[(index - 1) % len(DAY_STEP_LATER)]
        options = [
            form.format(p=place, ro=josa_ro(place)),
            form.format(p="여기", ro="로"),
            "어제 들은 걸 떠올리며 여기로 와 봤어.",
        ]
    for text in options:
        if (
            len(text) <= limit
            and not early_values(d, text)
            and not prev_values(theme, d["day"], text)
        ):
            return text
    return options[-1]


def first_speaker(theme: Theme) -> str:
    """대화 첫 줄(오늘 온 까닭) 화자: 첫 등장인물(사건을 겪은 아이)."""
    chars = theme.get("characters") or []
    return str(chars[0].get("name") or "") if chars else "뭉치"


def day_step_of(theme: Theme, day: str) -> str:
    """그날 오늘 온 까닭. 예전 저장본(부분 다시 생성)처럼 칸이 비면 그 자리에서 코드 문장
    (#782 설계 v4 B4: 전에는 대화 첫 줄이 '(없음 …)'이 될 수 있었음)."""
    d = theme_day(theme, day)
    if step := str(d.get("dayStep") or "").strip():
        return step
    return day_step_text(theme, (theme.get("days") or []).index(d)) if d.get("place") else ""


def first_line_problems(theme: Theme, day: str, text: str) -> list[str]:
    """대화 첫 줄(첫 등장인물이 말하는 오늘 온 까닭)로 쓸 수 없는 까닭(#782 설계 v7). 대화 검사의
    줄 검사와 같은 것 — 첫 줄은 코드가 붙여 대화를 다시 만들어도 안 고쳐짐(5차: 월요일 까닭의 자기
    이름으로 통과 23개 중 9개 월요일 대화 빠짐)."""
    d = theme_day(theme, day)
    bad = []
    if self_named(theme, text):
        bad.append("SELF_NAME")
    if len(text) > LINE_MAX:
        bad.append("LINE_LENGTH")
    if SPEAKER_PREFIX.match(text):
        bad.append("SPEAKER_IN_TEXT")
    if FOREIGN.search(text):
        bad.append("LANGUAGE")
    if early_values(d, text):
        bad.append("CLUE_EARLY")
    if prev_values(theme, day, text):
        bad.append("PREV_CLUE")
    if day == "MON" and day1_time(theme, text):
        bad.append("DAY1_TIME")
    # #782 설계 v10: 아이가 이미 아는 것(소리를 직접 들음·대상을 주움)도 첫 줄로 쓰지 않음
    bad += list(dict.fromkeys(code for code, _ in child_known(theme, text, True)))
    return bad


def split_long_lines(lines: list[dict], grade: int) -> list[dict]:
    """40자 넘는 대화 줄을 문장 경계에서 같은 화자 두 줄로 나눈다(#782 설계 v8). 나눈 줄이 모두
    40자 안이고 첫 줄(코드가 붙임)을 더해도 학년 줄 수 상한 안일 때만. 3·4·5차 40자 넘은 대화
    줄 198줄 중 거의 다가 부탁과 약속('도와주면 그때 본 걸 알려 줄게')을 한 줄에 붙인 것."""
    out = list(lines)
    hi = DIALOGUE_LINES[grade][1]
    for i in range(len(out) - 1, -1, -1):
        text = str(out[i].get("text") or "")
        if len(text) <= LINE_MAX:
            continue
        parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+", text) if p.strip()]
        if len(parts) < 2 or any(len(p) > LINE_MAX for p in parts):
            parts = comma_split(text)  # #782 설계 v9: 한 문장이면 쉼표에서(6차 new6b 수 대화 빠짐)
        if len(parts) < 2:
            continue
        if len(out) - 1 + len(parts) + 1 > hi:
            continue
        out[i : i + 1] = [{**out[i], "text": p} for p in parts]
    return out


def comma_split(text: str) -> list[str]:
    """한 문장 긴 줄을 가운데에 가까운 쉼표에서 둘로(두 쪽 모두 40자 안일 때만). 없으면 []."""
    cuts = [m.end() for m in re.finditer(r",\s", text)]
    ok = [c for c in cuts if max(len(text[:c].strip()), len(text[c:].strip())) <= LINE_MAX]
    if not ok:
        return []
    cut = min(ok, key=lambda c: abs(c - len(text) / 2))
    return [text[:cut].strip(), text[cut:].strip()]


def first_line_text(theme: Theme, day: str) -> str:
    """대화 첫 줄로 붙일 오늘 온 까닭. 첫 줄로 쓸 수 없으면(first_line_problems) 코드 문장. 대화
    노드(with_first_line)와 대화 지시문이 같은 줄을 쓴다(#782 설계 v7)."""
    step = day_step_of(theme, day)
    if step and first_line_problems(theme, day, step):
        return day_step_text(theme, (theme.get("days") or []).index(theme_day(theme, day)))
    return step


def with_first_line(theme: Theme, day: str, lines: list[dict], grade: int) -> list[dict]:
    """대화 앞에 오늘 온 까닭을 첫 등장인물의 말로 붙인다(#782 설계 v3). 붙여서 학년 줄 수 상한을
    넘으면 모델의 앞쪽 줄(오늘 온 까닭을 되풀이하는 줄)부터 지워 맞춘다(#782 설계 v4 B2: 3차 측정
    way4 'LINE_COUNT 6줄'로 그날 대화가 빠짐). 마지막 줄(뭉치)은 지우지 않는다. 까닭이 첫 줄로 쓸
    수 없으면(first_line_problems) 코드 문장으로 붙인다(#782 설계 v7)."""
    step = first_line_text(theme, day)
    if not step:
        return list(lines)
    rest = list(lines)
    hi = DIALOGUE_LINES[grade][1]
    while len(rest) + 1 > hi and len(rest) > 1:
        rest.pop(0)
    return [{"speaker": first_speaker(theme), "text": step}, *rest]


def fill_day_steps(theme: Theme) -> Theme:
    """비어 있는 요일 dayStep만 코드 문장으로 채운다(제자리). #782 설계 v5부터 오늘 온 까닭은 모델이
    쓰고(코드가 쓰면 한 주가 같은 꼴), 코드 문장은 빈 칸·두 번 고쳐도 걸릴 때만(fix_theme)."""
    days = theme.get("days") or []
    for i, d in enumerate(days):
        if isinstance(d, dict) and d.get("place") and not str(d.get("dayStep") or "").strip():
            d["dayStep"] = day_step_text(theme, i)
    return theme


# #782 설계 v7: 오늘 온 까닭에 어제 돕는 사람이 하지 않은 일(부탁·소개·지시·건넴)이나 오늘 할
# 일을 씀(5차 화~금 92줄 중 52줄을 잡음 — "행사 준비 담당자가 부탁한 둥근 표시판 일을 도우러",
# "체험 도구 담당자가 소개한 체험관으로"). 장소·돕는 사람 호칭은 지우고 봄('영상 기록가'·'기록방')
DAY_STEP_MADE = re.compile(
    r"부탁|달라|도와|도우러|도우려|돕[자고는]|라\s?해|라며|라던|라고\s?(?:해|했)|자고|보래|보라|"
    # v8: '가져갔을지'(대상 이야기)·'많다고'·기록 매체(어제 돕는 사람이 실제로 보여 준 기록은
    # 참말)·'어제 일을 떠올리며'는 뺌
    r"건넨|건네|건넸|가져다\s?준|가져왔|소개|권한|권해|안내한|안내를|안내해|보여\s?준|보여\s?줘|"
    r"보여서|이어\s?준|일로|일을\s?(?:도|돕)|필요하다|모은다|시킨|불러|자료를|"
    r"알려\s?준\s?(?:\S+\s?){1,4}?(?:을|를)\s?만나"
)


def self_named(theme: Theme, text: str) -> bool:
    """첫 등장인물(대화 첫 줄 화자)이 자기 이름을 말하는지(앞 글자가 한글이면 다른 낱말)."""
    name = first_speaker(theme)
    return len(name) >= 2 and bool(re.search(rf"(?<![가-힣]){re.escape(name)}", text or ""))


def day_step_problems(theme: Theme) -> list[str]:
    """오늘 온 까닭 검사(칸 고쳐 쓰기, 두 번째에도 걸리면 코드 문장, #782 설계 v7).

    - DAY_STEP_MADE 화~금: 어제 돕는 사람이 하지 않은 일·오늘 할 일, 어제·오늘이 아닌 다른 날
      돕는 사람(그 사람과 오늘 사이에 일이 없음)
    - SELF_NAME 모든 요일: 대화 첫 줄로 첫 등장인물이 말하는데 자기 이름"""
    days = theme.get("days") or []
    if tuple(d.get("day") for d in days) != DAYS:  # 요일이 어긋나면 DAYS가 먼저 잡음(어제가 없음)
        return []
    names = [str(x.get(k) or "") for x in days for k in ("place", "helper")]
    bad = []
    for i, d in enumerate(days):
        step = str(d.get("dayStep") or "").strip()  # 빈 칸은 REQUIRED가 잡음
        if not step:
            continue
        rest = step
        for name in sorted({n for n in names if n}, key=len, reverse=True):
            rest = rest.replace(name, "□")  # 빈칸이 아닌 자리표시('알려 준 □를 만나')
        made = sorted({m.group(0) for m in DAY_STEP_MADE.finditer(rest)})
        # 어제·오늘 호칭을 먼저 지우고 봄('작은 도서관 사서' 안의 '도서관 사서')
        near = [str(x.get("helper") or "").strip() for x in days[max(i - 1, 0) : i + 1]]
        others = step
        for name in sorted({n for n in near if n}, key=len, reverse=True):
            others = others.replace(name, "□")
        made += [
            f"다른 날 돕는 사람 '{h}'"
            for h in dict.fromkeys(str(x.get("helper") or "").strip() for x in days)
            if h and h not in near and compact(h) in compact(others)
        ]
        if i and made:
            bad.append(
                f"DAY_STEP_MADE {d['day']} dayStep에 어제 돕는 사람이 하지 않은 일이나 오늘 할 "
                f"일({'·'.join(made)}) — 오늘 여기 온 까닭만(어제 일은 들은 것만, 부탁은 대화에서 "
                "그날 사람이 함)"
            )
        if self_named(theme, step):
            bad.append(
                f"SELF_NAME {d['day']} dayStep에 '{first_speaker(theme)}' 이름(대화 첫 줄로 그 "
                "인물이 직접 하는 말이라 자기 이름을 쓰지 않음, '나'의 말로)"
            )
    return bad


# #782 설계 v7: 비밀 재료 음식은 토요일 잔치에 낼 것이라 잔치·대회는 아직 열리지 않음(5차 hand5
# "내가 대회에서 눈으로 직접 본 할머니 떡").
# #782 설계 v10(2.3): 종류와 상관없이 시작 이야기가 앞으로 열릴 행사를 말하면(토요일 대회, 별 보기
# 모임 직전) 끝 이야기 전 단서·지문·미션 글이 그 행사를 이미 열린 것처럼 쓰지 않음. v7 낱말 목록
# (비밀 재료만, '대회에서·때·날')은 7차 hand5 '대회장 안으로 간 시각'·auto4b '별빛 캠핑을 마친 네
# 마음'을 못 잡아 이 검사로 바꿈(비밀 재료는 시작 이야기에 없어도 토요일 잔치·대회를 늘 앞일로 봄)
EVENT_NOUN = r"(?:대회|잔치|축제|모임|행사|발표회|장터|시식회|캠핑|공연)"
EVENT_FUTURE_MARK = re.compile(
    r"(?:토요일|일요일|주말|다음\s?주|내일|모레)(?:에|의|에는|에\s?열릴|에\s?열리는|에\s?있을)?\s"
    rf"((?:[가-힣]+\s){{0,2}}[가-힣]*?{EVENT_NOUN})"
)
EVENT_BEFORE_MARK = re.compile(
    rf"((?:[가-힣]+\s){{0,2}}[가-힣]*?{EVENT_NOUN})\s?(?:을|를)?\s?(?:직전|앞둔|앞두고)"
)
SECRET_EVENTS = ("잔치", "대회", "축제", "시식회")
# 행사 낱말 바로 뒤가 앞일 뜻이면 됨('대회에 낼'·'잔치 준비'·'모임을 앞둔'·'대회 때 쓸')
EVENT_FUTURE_AFTER = re.compile(
    r"\s?(?:에서|에|을|를|이|가|의|때)?\s?"
    r"(?:낼|내려|내기|내놓|나갈|나가려|나가기|나간대|나간다|가져갈|가져가려|가져가기|쓸|쓰려|먹을|"
    r"나눌|선보일|준비|앞둔|앞두고|열릴|열리는|열리기|전에|전날|직전|까지|연습|맞이|할\s?때\s?쓸)"
)
# 이미 열린 뜻('대회에서 본'·'잔치 때'·'대회 날'·'대회장 안으로'·'잔치가 끝난'·'대회에 냈'). '대회
# 날짜'·'대회장 앞 골목'(곳 이름)은 뺌
EVENT_PAST_AFTER = re.compile(
    r"(?:장\s?(?:안|에서|으로|에\s?(?:들어|간|갔))"
    r"|\s?(?:에서|때|날(?!짜)|이\s?끝|가\s?끝|이\s?열린|가\s?열린|이\s?열렸|가\s?열렸|을\s?마|를\s?마"
    r"|에\s?(?:나갔|냈|낸|가져갔|가져간|다녀|갔|가서|와서|왔)))"
)
# 행사 이름이 달라도(시작 '별 보기 모임' ↔ 미션 '별빛 캠핑') 끝났다고 쓰면 이미 열린 것(앞으로의
# 행사가 있는 테마만)
EVENT_DONE = re.compile(
    rf"[가-힣]*{EVENT_NOUN}(?:을|를|이|가)?\s?"
    r"(?:마친|마치고|마쳤|끝난|끝나고|끝났|끝낸|다녀온|다녀와)"
)
EVENT_FIELDS = ("clue", "missionMaterial")


def future_events(theme: Theme) -> list[str]:
    """시작 이야기(모델 몫)가 앞으로 열린다고 한 행사 이름(#782 설계 v10). '토요일·주말·다음 주·
    내일 + 행사', '행사 + 직전·앞둔'. 예: '토요일 마을 떡 대회' → '마을 떡 대회', '별 보기 모임
    직전' → '별 보기 모임'."""
    intro = intro_story(theme)
    found = [m.group(1) for p in (EVENT_FUTURE_MARK, EVENT_BEFORE_MARK) for m in p.finditer(intro)]
    # '다음 주 학교 발표회를 앞둔'이 두 꼴에 다 걸려 '주 학교 발표회'가 함께 나오면 짧은 쪽만
    return [e for e in dict.fromkeys(found) if not any(o != e and o in e for o in found)]


def event_keys(theme: Theme) -> list[str]:
    """뒤 글에서 찾을 행사 낱말(행사 이름 끝의 대회·모임 등). 비밀 재료는 토요일 잔치·대회를 늘
    더함(종류 규칙이 정한 앞일)."""
    keys = [k for e in future_events(theme) for k in re.findall(EVENT_NOUN, e.split()[-1])]
    if story_type(theme).code == "SECRET_INGREDIENT":
        keys += SECRET_EVENTS
    return list(dict.fromkeys(keys))


def event_later_hits(theme: Theme, text: str | None) -> list[str]:
    """글이 아직 열리지 않은 행사를 이미 열린 것처럼 쓴 곳(행사 낱말과 뒤 몇 글자). 없으면 []."""
    text = str(text or "")
    keys = event_keys(theme)
    if not keys or not text:
        return []
    hits = []
    for key in keys:
        for m in re.finditer(key, text):
            after = text[m.end() : m.end() + 12]
            # '캠핑장'은 곳 이름(행사가 열렸다는 뜻이 아님)
            if key == "캠핑" and after.startswith("장"):
                continue
            if not EVENT_FUTURE_AFTER.match(after) and EVENT_PAST_AFTER.match(after):
                hits.append(text[m.start() : m.end() + 6].strip())
    # 같은 행사 낱말은 위에서 봤으므로 다른 행사 낱말의 '마친·끝난'만 더함
    hits += [
        m.group(0) for m in EVENT_DONE.finditer(text) if not any(k in m.group(0) for k in keys)
    ]
    return list(dict.fromkeys(hits))


def event_later_problems(theme: Theme) -> list[str]:
    """단서·지문이 아직 안 열린 행사를 이미 열린 것처럼 쓰면(EVENT_LATER, 그 칸만 고쳐 씀)."""
    events = future_events(theme) or list(event_keys(theme))
    bad = []
    for d in theme.get("days") or []:
        for key in EVENT_FIELDS:
            if hits := event_later_hits(theme, d.get(key)):
                bad.append(
                    f"EVENT_LATER {d['day']} {key}에 아직 열리지 않은 행사({'·'.join(events)})를 "
                    f"이미 열린 것처럼 씀({hits}) — 시작 이야기에서 앞으로 열릴 일이라 끝 이야기 "
                    "전에는 '~에 낼·나갈·가져갈·준비·앞둔'처럼 앞일로만(만들 때·준비할 때·나를 때 "
                    "본 것으로)"
                )
    return bad


def story_self_problems(theme: Theme) -> list[str]:
    """사건 단서에 첫 등장인물(사건을 겪은 아이) 자신의 일이 나오면(STORY_SELF, 그 단서만).
    아이가 이미 아는 일이라 단서가 아님(#782 설계 v7, 5차 snd4 "윤슬이 잠시 귀 기울이는 모습")."""
    name = first_speaker(theme)
    return [
        f"STORY_SELF {d['day']} clue에 아이 자신('{name}')의 일(아이가 이미 아는 일 — 찾는 대상이 "
        "지나간 길·한 일·남긴 것으로)"
        for d in theme.get("days") or []
        if is_story(d.get("condition") or {}) and self_named(theme, str(d.get("clue") or ""))
    ]


# #782 설계 v10(2.1): 아이(첫 등장인물)가 이미 아는 것을 단서로 쓰지 않음. 소리 탐정은 아이가 소리를
# 직접 듣거나 소리에 깨지 않고(INTRO_HEARD), 출처 찾기 물건은 아이가 줍거나 받아 들지 않음
# (INTRO_FOUND) — 직접 듣거나 쥐면 소리 특징·묻은 것 단서를 이미 앎(4~7차 치명). 시작 이야기·오늘 온
# 까닭(칸 고쳐 쓰기)과 대화의 첫 등장인물 줄(그 요일 대화 다시)을 같이 봄(설계 v10 5절)
HEAR_ACT = re.compile(r"들었|듣고|깼|깨어|잠에서")
HEAR_PASSIVE = re.compile(r"들려(?!\s?주|\s?준|\s?줬|\s?줄)|들리")
FOUND_ACT = re.compile(r"주웠|주워|주운|발견해|찾아서 들|받아 들")
# 전해 들은 꼴('할머니께 전해 들었'·'이야기를 들었'·'말을 듣고'), 못 들음, 잠자리에 들었(잠)
KNOWN_BEFORE_OK = re.compile(
    r"(?:전해|이야기를?|얘기를?|말을?|소식을?|에게서?|한테서?|께|못|안|잠자리에|잠이|자리에|손에)\s?$"
)
# 남의 말을 옮긴 꼴('들었다고'·'들렸대'·'주웠다는'), 다른 사람을 가리키는 꼴('주운 사람')
KNOWN_AFTER_OK = re.compile(
    r"^(?:다고|다는|대|단|더라|\s?(?:사람|분|아저씨|아주머니|선생님|직원|이웃))"
)
FIRST_PERSON = frozenset({"내가", "나는", "나도", "난", "제가", "저는", "저도"})
SUBJECT_TOKEN = re.compile(r"[가-힣]+(?:가|는|은|도|께서)")
# 주어가 아닌 '~에는·~에서도·~고는'(때·곳 말에 붙은 는·도)
KNOWN_NOT_SUBJECT = re.compile(r"(?:에|서|로|까지|부터|고|면)(?:는|도)$")
SENTENCE_SPLIT = re.compile(r"(?<=[.?!])\s+|\n")


def _known_subject(theme: Theme, before: str, first_person: bool) -> str | None:
    """그 말 앞(같은 문장)에서 가장 가까운 주어가 아이면 'child', 다른 사람·것이면 'other',
    없으면 None. 아이는 첫 등장인물 이름(+이)+가·는·은·도, 아이가 하는 말이면 '내가·나는'도."""
    name = first_speaker(theme)
    for tok in reversed(before.split()):
        tok = tok.strip(",.!?'\"…")
        if len(name) >= 2 and re.fullmatch(rf"{re.escape(name)}(?:이)?(?:가|는|은|도|이)", tok):
            return "child"
        if first_person and tok in FIRST_PERSON:
            return "child"
        if len(tok) >= 2 and SUBJECT_TOKEN.fullmatch(tok) and not KNOWN_NOT_SUBJECT.search(tok):
            return "other"
    return None


def child_known(theme: Theme, text: str | None, first_person: bool) -> list[tuple[str, str]]:
    """아이가 소리를 직접 듣거나(INTRO_HEARD, 소리 탐정) 대상을 줍거나 받아 든(INTRO_FOUND, 출처
    찾기 물건) 말 [(사유 코드, 걸린 말)]. first_person: 아이가 하는 말(오늘 온 까닭·대화 줄)이라
    주어가 없으면 아이로 봄. 시작 이야기(서술)는 아이 이름이 주어일 때만(듣기는 '소리가 들려'처럼
    소리가 주어라 그 문장에 아이 이름이 있으면). 전해 들은 꼴·남의 말을 옮긴 꼴은 됨."""
    t = story_type(theme)
    kinds: list[tuple[str, re.Pattern[str], re.Pattern[str] | None]] = []
    if t.code == "SOUND":
        kinds.append(("INTRO_HEARD", HEAR_ACT, HEAR_PASSIVE))
    if t.code == "ORIGIN" and theme_branch(theme) != "동물":
        kinds.append(("INTRO_FOUND", FOUND_ACT, None))
    name = first_speaker(theme)
    named = (
        re.compile(rf"(?<![가-힣]){re.escape(name)}(?:이)?(?:가|는|은|도|이|에게|한테)?(?![가-힣])")
        if len(name) >= 2
        else None
    )
    out = []
    for sentence in SENTENCE_SPLIT.split(str(text or "")):
        for code, act, passive in kinds:
            for pattern, is_passive in ((act, False), (passive, True)):
                for m in pattern.finditer(sentence) if pattern else ():
                    before, after = sentence[: m.start()], sentence[m.end() :]
                    if KNOWN_BEFORE_OK.search(before) or KNOWN_AFTER_OK.match(after):
                        continue
                    if is_passive:
                        child = first_person or bool(named and named.search(before))
                    else:
                        who = _known_subject(theme, before, first_person)
                        child = who == "child" or (who is None and first_person)
                    if child:
                        out.append((code, m.group(0)))
    return list(dict.fromkeys(out))


def child_known_why(theme: Theme, code: str) -> str:
    name = first_speaker(theme)
    if code == "INTRO_HEARD":
        return (
            f"아이('{name}')가 소리를 직접 들음 — 아이는 소리를 듣지 않았고 이웃·가족에게 전해 "
            "들은 것으로(직접 들으면 소리 특징을 이미 알아 단서가 필요 없음)"
        )
    return (
        f"아이('{name}')가 대상을 직접 줍거나 받아 듦 — 다른 사람(관리실 직원·선생님)이 주워 "
        "맡겼고 아이는 이야기로만 앎(손에 쥐거나 살펴본 적 없음)"
    )


def child_known_problems(theme: Theme) -> list[str]:
    """시작 이야기·오늘 온 까닭에서 아이가 이미 아는 것(INTRO_HEARD·INTRO_FOUND, 그 칸 고쳐 씀)."""
    bad = [
        f"{code} intro에 '{word}' {child_known_why(theme, code)}"
        for code, word in child_known(theme, intro_story(theme), False)
    ]
    for d in theme.get("days") or []:
        bad += [
            f"{code} {d['day']} dayStep에 '{word}' {child_known_why(theme, code)}"
            for code, word in child_known(theme, d.get("dayStep"), True)
        ]
    return bad


# #782 설계 v10(2.4): 시간 탐정은 그 일을 한 사람이 등장인물이 아니고 끝 이야기에서 처음 나옴. 끝
# 이야기가 첫 등장인물이 아닌 등장인물을 찾아가·만나·물어 확인하면 그 사람이 처음부터 곁에 있던 셈
# (줄거리 다시 — 인물 구성이 틀려 칸 하나로 못 고침)
WHEN_MEET = re.compile(r"만나|만났|찾아가|찾아갔|에게\s?물|한테\s?물|께\s?물|확인")


def when_doer_problems(theme: Theme) -> list[str]:
    if story_type(theme).code != "WHEN":
        return []
    story = str(theme.get("outroStory", theme.get("outro")) or "")
    others = [str(c.get("name") or "").strip() for c in (theme.get("characters") or [])[1:]]
    bad = []
    for sentence in SENTENCE_SPLIT.split(story):
        if not WHEN_MEET.search(sentence):
            continue
        for name in others:
            # 함께 간 사람('지호와 민아는 ~를 찾아가')이 아니라 찾아가거나 물은 상대일 때만
            if len(name) >= 2 and re.search(
                rf"(?<![가-힣]){re.escape(name)}(?:이)?(?:를|을|에게|한테|께|네)", sentence
            ):
                bad.append(
                    f"WHEN_DOER outro에서 등장인물 '{name}'을(를) 찾아가 확인함(그 일을 한 사람은 "
                    "등장인물이 아니라 끝 이야기에서 처음 나오는 사람 — 등장인물이 한 일이면 "
                    "처음부터 물어보면 끝남)"
                )
    return list(dict.fromkeys(bad))


# #782 설계 v10(2.1): 사건 단서가 시작 이야기에서 아이가 이미 본 모습을 되풀이함(6차 new4). 낱말
# 겹침이라 오탐이 있을 수 있어 check_theme에는 아직 넣지 않음 — 저장 결과로 통과 테마 오탐을 먼저
# 재고 적을 때만 넣음(설계 v10 2.1 '넣는 조건')
INTRO_SEEN_MIN = 2
SEEN_JOSA = re.compile(
    r"(?:에서|에게|한테|처럼|까지|부터|으로|이랑|이나|이가|이는|이도|은|는|이|가|을|를|도|의|와|과"
    r"|로|에|만|랑)$"
)
SEEN_STOP = frozenset(
    {"그때", "내가", "제가", "우리", "정말", "조금", "아까", "모습", "사진", "영상", "녹음", "메모"}
    | {"일지", "기록", "소리", "있었", "있어", "봤어", "보였", "같아", "처럼", "그리고", "그래서"}
)


def _seen_words(theme: Theme, text: str | None) -> dict[str, str]:
    """낱말 앞 두 글자 → 낱말(조사 뗌, 두 글자 이상, 대상 낱말·아이 이름·흔한 말 뺌)."""
    skip = {*target_words(theme), first_speaker(theme)}
    out: dict[str, str] = {}
    for tok in re.findall(r"[가-힣]{2,}", str(text or "")):
        word = SEEN_JOSA.sub("", tok) if len(SEEN_JOSA.sub("", tok)) >= 2 else tok
        if word in skip or word[:2] in SEEN_STOP or any(word.startswith(s) for s in skip if s):
            continue
        out.setdefault(word[:2], word)
    return out


def intro_seen_clue(theme: Theme, day: str) -> list[str]:
    """사건 단서(STORY) 날 단서가 시작 이야기와 겹치는 내용 낱말(INTRO_SEEN_MIN개 이상일 때만,
    아니면 []). 낱말은 앞 두 글자로 견줌('흩어진'·'흩어져')."""
    d = theme_day(theme, day)
    if not is_story(d.get("condition") or {}):
        return []
    clue = _seen_words(theme, d.get("clue"))
    intro = _seen_words(theme, intro_story(theme))
    shared = [clue[k] for k in clue if k in intro]
    return shared if len(shared) >= INTRO_SEEN_MIN else []


def finalize_texts(theme: Theme) -> Theme:
    """코드가 맞추는 글: 시작 이야기 끝 규칙 문장, 종료 이야기 앞 다섯 단서 정리.

    줄거리·칸 고쳐 쓰기 뒤마다 부른다. 단서 앞에 그때 시각·'그때'를 붙이던 것(add_clue_time, #535
    7차·#782)은 뺐다(#782 테마 짜임, 사용자 결정 2026-11-19: 단서를 발견 장면 대사처럼 쓰고 앞
    시각을
    빼기로 함, 실측 시각·'그때'로 시작하는 단서 58/180).
    """
    return compose_outro(compose_intro(fill_day_steps(normalize_clue_source(theme))))


def plan_slot(theme: Theme, day: str) -> dict[str, str | None] | None:
    """줄거리에 붙은 그날 배정(plan_theme이 evidencePlan으로 넣음). 없으면 None(배정 검사 안 함)."""
    return (theme.get("evidencePlan") or {}).get(day)


def evidence_plan_problems(day: dict, slot: dict[str, str | None]) -> list[str]:
    """배정과 다른 증거(CLUE_EVIDENCE). 종류가 다르면 그날 단서·증거 발견 줄·수사 연결 문장을 모두
    새 종류로 고쳐 써야 하고(셋 다 그 증거를 말함), 기록 매체 낱말이 없으면 단서·증거 발견 줄만."""
    name = day["day"]
    kind, want = (day.get("evidence") or {}).get("kind"), slot.get("kind")
    if kind != want:
        why = (
            f"증거 종류가 배정과 다름(배정 {EVIDENCE_KO.get(str(want), want)} {want}, 지금 {kind})"
        )
        return [f"CLUE_EVIDENCE {name} {k} {why}" for k in ("clue", "discovery", "missionHook")]
    medium = slot.get("medium")
    if not medium:
        return []
    words = MEDIUM_WORDS.get(medium, (medium,))
    return [
        f"CLUE_EVIDENCE {name} {k} 기록 매체가 배정과 다름(배정 매체 '{medium}' 낱말을 씀)"
        for k in ("clue", "discovery")
        if not any(w in (day.get(k) or "") for w in words)
    ]


def apply_evidence_plan(theme: Theme) -> Theme:
    """evidence.kind를 배정대로 바꾼다(fix_theme이 칸 고쳐 쓰기 전에, 증거 생긴 때는 그대로)."""
    for d in theme.get("days") or []:
        if (slot := plan_slot(theme, d.get("day") or "")) and slot.get("kind"):
            d["evidence"] = {**(d.get("evidence") or {}), "kind": slot["kind"]}
    return theme


def fix_targets(bad: list[str]) -> dict[str, list[str]]:
    """사유가 모두 칸 하나만 고치면 되는 것이면 {칸 경로: [사유]}, 하나라도 아니면 빈 사전."""
    targets: dict[str, list[str]] = {}
    for reason in bad:
        path = None
        for pattern in FIX_REASON:
            if m := pattern.match(reason):
                path = ".".join(m.groups())
                break
        cut_fix = reason.startswith(("CUT_ACTION ", "CUT_TARGET ")) and CUT_FIX_PATH.match(
            path or ""
        )
        if path is None or not (FIX_PATH.match(path) or cut_fix):
            return {}
        targets.setdefault(path, []).append(reason)
    return targets


def _cut_or_day(theme: Theme, path: str) -> tuple[dict, str]:
    head, _, key = path.partition(".")
    if not key:
        # 종료 이야기를 고쳐 쓸 때는 LLM 몫(마무리 장면)만 고친다. 정리는 코드가 붙임. 시작 이야기도
        # 규칙 문장을 코드가 붙이는 종류면 모델 몫만(#634 ④)
        if head == "outro" and "outroStory" in theme:
            return theme, "outroStory"
        if head == "intro" and "introStory" in theme:
            return theme, "introStory"
        return theme, head
    if m := re.fullmatch(r"(introCuts|outroCuts)(\d)", head):
        return theme[m.group(1)][int(m.group(2)) - 1], key
    return theme_day(theme, head), key


def text_at(theme: Theme, path: str) -> str:
    where, key = _cut_or_day(theme, path)
    return str(where.get(key) or "")


def set_text_at(theme: Theme, path: str, text: str) -> None:
    where, key = _cut_or_day(theme, path)
    where[key] = text
    if key == "outroStory":
        compose_outro(theme)
    if key == "introStory":
        compose_intro(theme)


def text_max(path: str, theme: Theme | None = None) -> int:
    key = path.rpartition(".")[2]
    if key == "caption":
        if theme is not None and (m := re.match(r"(introCuts|outroCuts)", path)):
            return cut_layout.CAPTION_MAX.get(len(theme.get(m.group(1)) or []), CAPTION_MAX)
        return CAPTION_MAX
    if key in ("scene", "action"):
        return CUT_TEXT_MAX
    if path == "outro" and theme is not None and "outroStory" in theme:
        return OUTRO_STORY_MAX
    head = path.partition(".")[0]
    if theme is not None and key == "clue" and head in DAYS:
        return day_text_max(theme_day(theme, head), key, theme)
    return TEXT_MAX[key]


def mungchi_clauses(text: str, names: list[str] | tuple[str, ...] = ()) -> list[str]:
    """콘티 문장에서 뭉치가 주어인 마디. 뭉치가 나오는 컷에만 쓴다.

    '…고 '·'…며 '·'…가운데 '·'…동안 '·쉼표로 마디를 나눈다. '뭉치와 민지가'·'모두'처럼 함께 하는
    주어도 뭉치 마디이고 '뭉치를'·'뭉치 곁에서'는 아니다. 다른 사람이 주어(…이·…가, 마디 첫 낱말
    …는·…들은, 인물 이름·'…님' 뒤 은·는)인 마디는 빼고, 주어가 없는 마디는 앞 마디의 주어를
    잇는다(첫 마디는 뭉치).

    #779(대표 5종 콘티 2026-11-19): 받침 있는 이름 뒤 '은'('예린은 염소를 안고')을 다른 사람 주어로
    못 봐 엔딩 컷(찾은 염소를 안은 채 뭉치에게 고마워함)이 뭉치 손 동작으로 걸렸음. 받침 뒤 '은'을
    모두 주어로 보면 '작은 상자'의 '작은'도 걸려 진짜 뭉치 동작을 놓치므로 인물 이름과 '…님'만.
    """
    out: list[str] = []
    mungchi = True
    people = "|".join(re.escape(n) for n in names if n and n != "뭉치")
    other = re.compile(
        rf"(?:^|\s)(?:{people})(?:은|는)\s|^\S+님(?:은|는)\s" if people else r"^\S+님(?:은|는)\s"
    )
    for part in re.split(r"(?<=[고며]) |(?<=가운데) |(?<=동안) |[,.] ", text):
        if re.search(r"뭉치(?:가|는|도|와|과|랑|하고)(?:\s|$)", part) or re.match(
            r"(?:모두|다 ?같이|다 ?함께|함께)", part
        ):
            mungchi = True
        elif (
            re.match(r"\S+(?:는|들은|도)\s", part)
            or other.search(part)
            or any(
                not w.endswith(NOT_SUBJECT)
                for w in re.findall(r"(?:^|(?<=\s))(\S+(?:이|가))(?=\s)", part)
            )
        ):
            mungchi = False
        if mungchi:
            out.append(part)
    return out


def cut_action_problems(
    text: str,
    has_mungchi: bool = True,
    may_run: bool = False,
    names: list[str] | tuple[str, ...] = (),
) -> list[str]:
    """뭉치가 손·팔다리를 쓰거나 뛰는 동작(뭉치가 나오는 컷만), 화면 쪽으로 다가오거나 나가는 동작.

    may_run(출동 컷)이면 뭉치의 달리기 낱말(MUNGCHI_RUN_WORDS)은 걸지 않는다(#779).
    """
    clauses = mungchi_clauses(text, names) if has_mungchi else []
    words = [w for w in MUNGCHI_HAND_WORDS if not (may_run and w in MUNGCHI_RUN_WORDS)]
    hands = [w for w in words if any(w in c for c in clauses)]
    near = [w for w in APPROACH_WORDS if w in text]
    plain = text
    for neg in AIR_HAND_NOT:
        plain = plain.replace(neg, "")
    air = [w for w in AIR_HAND_WORDS if w in plain]
    out = []
    if hands:
        out.append(f"뭉치가 손·팔다리를 쓰는 동작({', '.join(hands)}), 손짓은 사람만")
    if air:  # 사람·뭉치 모두(#779 공중 손짓 없음)
        out.append(f"공중 손짓({', '.join(air)})은 사람도 쓰지 않음(폴짝 뛰거나 웃는 것으로)")
    if near:
        out.append(f"화면 쪽으로 다가오거나 화면 밖으로 나가는 동작({', '.join(near)})")
    return out


def feature_table(theme: Theme) -> tuple[dict[str, dict[str, str]], list[str]]:
    """{특징 이름: {후보: 값}}과 표 형식 문제."""
    cands = theme.get("candidates") or []
    feats = theme.get("features") or []
    table: dict[str, dict[str, str]] = {}
    bad: list[str] = []
    if not FEATURES[0] <= len(feats) <= FEATURES[1]:
        bad.append(f"FEATURES 특징 {FEATURES[0]}~{FEATURES[1]}개(지금 {len(feats)}개)")
    for f in feats:
        name = (f.get("name") or "").strip()
        if not name:
            bad.append("FEATURES 이름 없는 특징")
            continue
        if name in table:
            bad.append(f"FEATURES 특징 이름 중복 {name}")
            continue
        vals = f.get("values") or []
        named = [v.get("candidate") for v in vals]
        if sorted(named) != sorted(cands) or any(not (v.get("value") or "").strip() for v in vals):
            bad.append(f"FEATURES {name}: 후보마다 값 하나씩 필요(지금 {named})")
            continue
        table[name] = {v["candidate"]: v["value"].strip() for v in vals}
    return table, bad


def fill_rules_out(theme: Theme) -> Theme:
    """요일별 rulesOut을 특징 표와 조건으로 채운다(LLM은 쓰지 않음, 실측 repo-beach5-1).

    RULE은 허용 값 밖 후보 전부(이미 빠진 후보 포함, 후보 순서), HINT는 빈 배열. 표·조건이
    틀린 날은 빈 배열로 두고 사유는 check_logic이 낸다.
    """
    table, _ = feature_table(theme)
    cands = theme.get("candidates") or []
    days = []
    for d in theme.get("days") or []:
        cond = d.get("condition") or {}
        vals = table.get(cond.get("feature")) or {}
        allowed = set(cond.get("allowed") or [])
        rule = cond.get("kind") == "RULE" and bool(vals)
        days.append({**d, "rulesOut": [c for c in cands if rule and vals[c] not in allowed]})
    return {**theme, "days": days}


def check_logic(theme: Theme, cands: list[str], answer: str, days: list[dict]) -> list[str]:
    """특징 표로 정답 논리를 계산해 확인한다(검토 모델에 맡기지 않음)."""
    table, bad = feature_table(theme)
    if bad or answer not in cands:
        return bad
    remaining, first_out = list(cands), {}
    seen_clues: set[tuple[str, frozenset[str]]] = set()
    for i, d in enumerate(days):
        day, cond = d["day"], d.get("condition") or {}
        if is_story(cond):  # 사건 단서: 아무 후보도 빼지 않고 후보 이름·특징 값을 말하지 않음
            hits = story_value_hits(theme, table, d.get("clue"))
            # #782 설계 v8: 탈것 사건 단서의 '바퀴'(바퀴 자국은 자전거·킥보드만 남김)
            if story_type(theme).code == "VEHICLE" and "바퀴" in str(d.get("clue") or ""):
                hits = [*hits, "바퀴"]
            if hits:
                bad.append(
                    f"STORY_VALUE {day} clue 사건 단서에 후보 이름·특징 값 {hits}(후보를 가르지 "
                    "않는 사건 이야기로)"
                )
            continue
        vals = table.get(cond.get("feature"))
        allowed = set(cond.get("allowed") or [])
        if vals is None:
            bad.append(f"CONDITION {day} 표에 없는 특징 {cond.get('feature')}")
            continue
        if not allowed or not allowed <= set(vals.values()):
            bad.append(
                f"CONDITION {day} allowed {sorted(allowed)}는 표의 값 {sorted(set(vals.values()))} "
                "안에서"
            )
            continue
        # #782 설계 v3: 단서 꼴은 값 하나(그대로 말함)나 빠지는 값 1~2개(부정으로 말함)만. 그 밖은
        # 'A나 B나 C'로 늘어놓을 수밖에 없어 조건을 바꾼다(repair_logic이 이 꼴을 고르지 않음).
        # 저장 테마 58개 216날에는 0번
        out_vals = set(vals.values()) - allowed
        # 빠지는 값이 없는 꼴(특징 값 전부)은 CLUE_EMPTY·RULE 빼는 후보 없음 검사와
        # repair_hints가 맡음
        if len(allowed) >= 2 and len(out_vals) > NEG_MAX_EXCLUDED:
            bad.append(
                f"CONDITION {day} 단서 조건은 값 하나이거나 빠지는 값 1~{NEG_MAX_EXCLUDED}개(지금 "
                f"허용 {sorted(allowed)}·빠짐 {sorted(out_vals)} — 직접 본 사람이 'A나 B'로 말하지 "
                "않게)"
            )
        clue = compact(d.get("clue"))
        missing = [a for a in sorted(allowed) if not value_in_text(a, d.get("clue"))]
        outside = [
            v
            for v in sorted(set(vals.values()) - allowed)
            if compact(v) in clue and not any(compact(v) in compact(a) for a in allowed)
        ]
        if negative_form(d):  # 빠지는 값을 부정으로 말함('나무는 아니었어') — 허용 값은 안 씀
            # #782 설계 v8: 부정문 안에 허용 값이 섞이면 무엇이 빠지는지 흐려짐(코드 틈)
            mixed = [
                a
                for a in sorted(allowed)
                if value_in_text(a, d.get("clue"))
                and not any(compact(a) in compact(e) for e in cond["excluded"])
            ]
            if mixed:
                bad.append(
                    f"CLUE_TEXT {day} clue 빠지는 값을 부정으로 말하면서 허용 값 {mixed} "
                    "낱말도 씀(빠지는 값만 '…는 아니었어')"
                )
            missing, outside = [], []
        elif cond.get("excluded"):  # #782 설계 v3: 허용 값이 둘 이상이면 늘어놓지 않고 부정으로
            bad.append(
                f"CLUE_TEXT {day} clue 빠지는 값 {cond['excluded']}을 '없었다·않았다'처럼 본 것 "
                "없이 씀 — 본 것·들은 것이 그 값이 아니었다고('내가 본 바닥은 나무는 "
                "아니었어', 직접 본 사람은 하나만 봄)"
                if ABSENT_FORM.search(str(d.get("clue") or ""))
                else f"CLUE_TEXT {day} clue 허용 값을 '나'로 늘어놓지 말고 빠지는 값 "
                f"{cond['excluded']}을 부정으로 씀('…는 아니었어', 직접 본 사람은 하나만 봄)"
            )
            missing, outside = [], []
        if missing:  # 문장이 조건보다 좁으면 표보다 일찍 답이 정해짐(시험 lab3-beach5-1)
            bad.append(
                f"CLUE_TEXT {day} clue 단서 문장에 허용 값 {missing} 낱말이 없음(허용 값 "
                f"{sorted(allowed)}을 그대로 씀)"
            )
        if outside:
            bad.append(f"CLUE_TEXT {day} clue 단서 문장에 허용 밖 값 {outside} 낱말이 있음")
        fit = [c for c in cands if vals[c] in allowed]
        if vals[answer] not in allowed:
            bad.append(f"LOGIC {day} 단서가 정답을 뺌(정답 값 {vals[answer]})")
        if cond.get("kind") == "RULE":
            expect = set(cands) - set(fit)  # = fill_rules_out이 채우는 rulesOut
            if not expect:
                bad.append(f"LOGIC {day} RULE인데 빠지는 후보가 없음")
            # learning 결정적 단서 = rulesOut이 비지 않은 마지막 요일(#438)이라 새로 빼는 날만 RULE
            if expect and not [c for c in remaining if c not in fit]:
                bad.append(
                    f"LOGIC {day} RULE인데 남은 후보를 빼지 않음(이미 빠진 후보만 빼는 단서는 HINT)"
                )
            for c in expect - {answer}:
                first_out.setdefault(c, i)
        elif cond.get("kind") == "HINT":
            live = [c for c in remaining if vals[c] in allowed]
            hidden = [c for c in remaining if vals[c] not in allowed]
            if hidden:  # 남은 후보를 빼면 사실상 RULE(시험 lab3-inventor-6: 화요일에 답이 정해짐)
                bad.append(f"LOGIC {day} HINT인데 남은 후보 {hidden}를 빼는 내용(RULE이어야 함)")
            if i < LAST_ELIMINATION_MIN and len(live) < 2:
                bad.append(
                    f"LOGIC {day} 월~목 힌트가 남은 후보 중 {live}만 가리킴(2개 이상이어야 함)"
                )
            # #782: 허용 값이 그 특징 값 전부면 '마른 땅이나 젖은 땅'처럼 아무것도 알려 주지 않음
            # (좁힐 수 있는 것은 narrow_hints가 먼저 좁히고, 남은 후보 값이 곧 전부면 여기서 걸림)
            if set(vals.values()) <= allowed:
                bad.append(
                    f"CLUE_EMPTY {day} 힌트 단서 허용 값 {sorted(allowed)}이 특징 "
                    f"'{cond.get('feature')}' 값 전부라 알려 주는 것이 없음(이미 빠진 후보와 값이 "
                    "갈리는 특징이나 RULE로)"
                )
        else:
            bad.append(f"CONDITION {day} kind는 RULE·HINT·STORY")
        # #782 테마 짜임: 앞 요일과 같은 단서는 아무것도 새로 알려 주지 않음(repair_hints가 먼저
        # 다른 특징으로 바꾸고, 못 바꾼 것만 여기서 걸림)
        if clue_key(cond) in seen_clues:
            bad.append(
                f"CLUE_REPEAT {day} 앞 요일과 같은 단서(특징 '{cond.get('feature')}', 허용 값 "
                f"{sorted(allowed)}) — 다른 특징이나 새 값으로"
            )
        seen_clues.add(clue_key(cond))
        remaining = [c for c in remaining if not (cond.get("kind") == "RULE" and c not in fit)]
    wrong = [c for c in cands if c != answer]
    never = [c for c in wrong if c not in first_out]
    if never:
        bad.append(f"LOGIC 어떤 RULE 단서로도 빠지지 않는 틀린 후보 {never}")
    elif wrong and max(first_out[c] for c in wrong) < LAST_ELIMINATION_MIN:
        last = DAYS[max(first_out[c] for c in wrong)]
        bad.append(f"LOGIC 마지막 틀린 후보가 {last}에 빠짐(금요일이어야 함)")
    return bad


# 정답 논리 수리에서 한 번에 바꿀 수 있는 요일 수 상한(기준안). 넘으면 지금처럼 줄거리를 다시 만든다
LOGIC_FIX_MAX_DAYS = 3


def _logic_only(theme: Theme, days: list[dict]) -> list[str]:
    """정답 논리(LOGIC)·조건 형식(CONDITION) 사유만. 단서 문장(CLUE_TEXT)은 조건을 바꾼 뒤
    고쳐 씀."""
    cands, answer = theme.get("candidates") or [], theme.get("answer") or ""
    return [
        r for r in check_logic(theme, cands, answer, days) if r.startswith(("LOGIC", "CONDITION"))
    ]


def repair_logic(theme: Theme) -> list[str]:
    """특징 표·특징은 그대로 두고 요일 단서 조건(RULE/HINT·허용 값)만 가장 적게 바꿔 정답 논리를
    맞춘다(#535 6차: LOGIC이 나면 줄거리 전체를 다시 만들던 것을 그 부분만 고침). 판정은 check_logic
    그대로 쓴다. 바꾼 요일을 돌려주고 theme의 condition·rulesOut을 고친다(단서 문장은 부르는 쪽이
    고쳐 씀). 못 맞추면 빈 목록(지금처럼 다시 생성).

    1단계: 정답을 빼는 요일은 그 요일 허용 값에 정답 값을 더한다(여러 날이어도 한 번에, #535 8차:
    월~목 네 날이 모두 정답을 빼는 표가 3일 상한에 걸려 다시 생성). 2단계: 남은 논리 사유는
    LOGIC_FIX_MAX_DAYS 안에서 가장 적게 바꾸는 조합을 찾는다.
    """
    table, bad = feature_table(theme)
    days = theme.get("days") or []
    answer = theme.get("answer") or ""
    if bad or answer not in (theme.get("candidates") or []) or not _logic_only(theme, days):
        return []
    if any(
        not is_story(d.get("condition") or {})
        and table.get((d.get("condition") or {}).get("feature")) is None
        for d in days
    ):
        return []
    base = [dict(d) for d in days]
    first: list[int] = []
    for i, d in enumerate(base):
        cond = d.get("condition") or {}
        if is_story(cond):
            continue
        keep = table[cond.get("feature")][answer]
        if keep not in (cond.get("allowed") or []):
            d["condition"] = {**cond, "allowed": sorted({*(cond.get("allowed") or []), keep})}
            first.append(i)
    if first:
        if not _logic_only(theme, base):
            return _apply_logic_fix(theme, days, base, first)
        if found := _search_logic_fix(theme, table, base):
            trial, idx = found
            return _apply_logic_fix(theme, days, trial, sorted({*first, *idx}))
    # 1단계로 못 맞추면 지금까지처럼 원래 조건에서 가장 적게 바꾸는 조합
    if found := _search_logic_fix(theme, table, days):
        trial, idx = found
        return _apply_logic_fix(theme, days, trial, list(idx))
    return []


def _search_logic_fix(
    theme: Theme, table: dict, days: list[dict]
) -> tuple[list[dict], tuple[int, ...]] | None:
    """요일 LOGIC_FIX_MAX_DAYS개 이하의 조건만 바꿔 정답 논리가 맞는 가장 작은 조합."""
    answer = theme.get("answer") or ""
    # 없는 값은 허용 값으로 더하지 않음(#634 ④ CLUE_ABSENT를 수리가 새로 만들지 않게)
    facts = story_type(theme).facts
    absent = facts.absent if facts is not None else frozenset()
    options: list[list[dict]] = []
    for d in days:
        cond = d.get("condition") or {}
        if is_story(cond):  # 사건 단서 날은 바꾸지 않음(특징이 없음)
            options.append([])
            continue
        vals = table[cond.get("feature")]
        keep = vals[answer]
        others = sorted(set(vals.values()) - {keep} - absent)
        sets = [
            sorted({keep, *combo})
            for r in range(len(others) + 1)
            for combo in itertools.combinations(others, r)
        ]
        now = set(cond.get("allowed") or [])
        opts = [{**cond, "kind": k, "allowed": a} for a in sets for k in ("RULE", "HINT")]
        opts = [o for o in opts if not (o["kind"] == cond.get("kind") and set(o["allowed"]) == now)]
        # 후보를 빼지 않는 날로 바꿀 때는 사건 단서도 후보(#782 테마 짜임)
        opts.append({"kind": STORY, "feature": "", "allowed": []})
        opts.sort(key=lambda o: (o["kind"] != cond.get("kind"), len(set(o["allowed"]) ^ now)))
        options.append(opts)
    for k in range(1, LOGIC_FIX_MAX_DAYS + 1):
        for idx in itertools.combinations(range(len(days)), k):
            for picks in itertools.product(*(options[i] for i in idx)):
                trial = [dict(d) for d in days]
                for i, cond in zip(idx, picks, strict=True):
                    trial[i]["condition"] = cond
                if not _logic_only(theme, trial):
                    return trial, idx
    return None


def repair_hints(theme: Theme) -> list[str]:
    """정보 없는 힌트 단서(허용 값이 그 특징 값 전부)를 코드가 고친다(#782). 바꾼 요일을 돌려준다.

    힌트는 남은 후보를 빼지 않으므로 허용 값에 그때 남은 후보 값이 모두 있어야 하는데, 그것이 곧
    특징 값 전부면 '마른 땅이나 젖은 땅'처럼 아무것도 알려 주지 않는다(#765 실측 줄거리 120건 중
    27건). 1) 이미 빠진 후보의 값까지 넣었으면 남은 후보 값으로 좁히고, 2) 남은 후보 값이 곧
    전부면 그날 증거 종류에 맞으면서(kind_fits) 남은 후보가 값을 다 채우지 않는 다른 특징으로
    바꾼다(같은 120건에서 27건 중 21건이 이것으로 풀림). 단서 문장은 부르는 쪽이 고쳐 쓰고, 둘 다
    안 되는 날은 사건 단서로 바꾼다(#782 테마 짜임, 전에는 그대로 두어 CLUE_EMPTY로 다시 생성).

    앞 요일과 같은 단서(같은 특징·같은 허용 값)인 힌트도 아직 그 값으로 쓰지 않은 다른 특징으로,
    없으면 사건 단서로 바꾼다(#782 테마 짜임, 사용자 결정 2026-11-19: 화요일 단서가 월요일과
    똑같았음, 저장된 실측 develop 37테마 중 11개·#782 36테마 중 14개, 다른 특징으로 바꿀 수 있는
    것은 29개 중 8개뿐 — 후보 4개·단서 5일이라 빼지 않는 날에 새로 알려 줄 특징이 없을 때가 많음).
    """
    table, bad = feature_table(theme)
    if bad:
        return []
    kind = story_type(theme)
    remaining, changed = list(theme.get("candidates") or []), []
    seen: set[tuple[str, frozenset[str]]] = set()
    for d in theme.get("days") or []:
        cond = d.get("condition") or {}
        vals = table.get(str(cond.get("feature") or ""))
        allowed = list(cond.get("allowed") or [])
        if vals is not None and cond.get("kind") == "HINT" and set(vals.values()) <= set(allowed):
            live = list(dict.fromkeys(vals[c] for c in remaining if c in vals))
            if set(live) < set(vals.values()):  # 1) 빠진 후보 값만 덜어 내면 됨
                d["condition"] = {**cond, "allowed": [a for a in allowed if a in live]}
                changed.append(d["day"])
            elif other := _informative_feature(table, remaining, kind, d, seen):
                feature, values = other
                d["condition"] = {**cond, "feature": feature, "allowed": values}
                changed.append(d["day"])
            else:  # 새로 알려 줄 특징이 없으면 사건 단서(#782 테마 짜임)
                d["condition"] = {"kind": STORY, "feature": "", "allowed": []}
                changed.append(d["day"])
        cond = d.get("condition") or {}
        if cond.get("kind") == "HINT" and clue_key(cond) in seen:
            other = _informative_feature(table, remaining, kind, d, seen)
            feature, values = other or ("", [])
            d["condition"] = (
                {**cond, "feature": feature, "allowed": values}
                if other
                else {"kind": STORY, "feature": "", "allowed": []}
            )
            if d["day"] not in changed:
                changed.append(d["day"])
        cond = d.get("condition") or {}
        seen.add(clue_key(cond))
        vals = table.get(str(cond.get("feature") or ""))
        if vals is not None and cond.get("kind") == "RULE":
            remaining = [c for c in remaining if vals.get(c) in set(cond.get("allowed") or [])]
    return changed


def clue_key(cond: dict) -> tuple[str, frozenset[str]]:
    """단서 조건의 (특징, 허용 값) — 같은 단서인지 비교(#782 CLUE_REPEAT)."""
    return str(cond.get("feature") or ""), frozenset(a for a in cond.get("allowed") or [] if a)


def _informative_feature(
    table: dict[str, dict[str, str]],
    remaining: list[str],
    kind: StoryType,
    day: dict,
    used: set[tuple[str, frozenset[str]]] | None = None,
) -> tuple[str, list[str]] | None:
    """그날 힌트로 쓸 수 있는 특징(남은 후보 값이 그 특징 값 일부뿐)과 허용 값. 값이 적게 남는
    특징(더 많이 알려 줌), 같으면 표 순서를 고른다. used(앞 요일 단서)와 같은 단서는 고르지
    않는다."""
    evidence = (day.get("evidence") or {}).get("kind")
    found = []
    for i, (feature, vals) in enumerate(table.items()):
        live = list(dict.fromkeys(vals[c] for c in remaining if c in vals))
        if (feature, frozenset(live)) in (used or set()):
            continue
        if live and set(live) < set(vals.values()) and kind_fits(kind, feature, evidence):
            found.append((len(live), i, feature, live))
    return (min(found)[2], min(found)[3]) if found else None


def _apply_logic_fix(
    theme: Theme, days: list[dict], fixed: list[dict], idx: list[int]
) -> list[str]:
    theme["days"] = fixed
    theme["days"] = fill_rules_out(theme)["days"]
    return [days[i]["day"] for i in idx]


def _subject(word: str) -> str:
    """'소리방이'·'바람방이'처럼 받침에 맞는 주격 조사."""
    last = word[-1:] if word else ""
    if "가" <= last <= "힣":
        return word + ("이" if (ord(last) - 0xAC00) % 28 else "가")
    return word + "이(가)"


def _join_days(days: list[str]) -> str:
    """['화', '금'] → '화요일과 금요일', ['화', '수', '금'] → '화요일, 수요일과 금요일'."""
    names = [f"{d}요일" for d in days]
    if len(names) == 1:
        return names[0]
    last = names[-1]
    return f"{', '.join(names[:-1])}{'과' if (ord(names[-2][-1]) - 0xAC00) % 28 else '와'} {last}"


def outro_recap(theme: Theme) -> str:
    """종료 이야기 앞에 붙이는 다섯 단서 정리.

    특징 표·조건으로 계산한 rulesOut 그대로라 표와 어긋날 수 없다. 허용 값은 쓰지 않는다(값 여럿인
    단서를 한 값으로 부르던 실패). 같은 틀이 다섯 번 되풀이되면 딱딱해서(사용자 2026-11-16) 세
    문장으로 잇는다: 후보가 빠진 날을 차례로 한 문장('월요일 단서로 A가 빠지고, 수요일엔 B,
    목요일엔 C가 빠졌어.'), 빠지지 않은 날을 한 문장('화요일과 금요일 단서는 남은 후보를 가르지는
    못했지만 정답과 딱 맞았어.' — 정답은 모든 조건을 만족하므로 늘 참), 끝에 '그래서 정답만 남았어.'
    """
    # 말투는 마무리 장면 끝에 맞춤: '…요.'면 '빠졌어요', '…다.'면 '빠졌다', 그 밖은 '빠졌어'
    # (실측 2026-11-16: 정리는 '빠졌어'인데 마무리 장면은 '찾았다'로 끝나 섞임)
    story = str(theme.get("outroStory") or "").strip()
    ending = (
        "요" if re.search(r"요[.!?]?$", story) else "다" if re.search(r"다[.!?]?$", story) else ""
    )

    def end(verb: str) -> str:  # verb: '빠졌어'·'맞았어'·'남았어'
        return verb[:-1] + "다" if ending == "다" else verb + ending

    remaining = list(theme.get("candidates") or [])
    outs: list[tuple[str, list[str]]] = []
    hints: list[str] = []
    stories: list[str] = []  # 사건 단서 날(#782 테마 짜임)
    for d in fill_rules_out(theme).get("days") or []:
        out = [c for c in d.get("rulesOut") or [] if c in remaining]
        remaining = [c for c in remaining if c not in out]
        if out:
            outs.append((DAY_KO[d["day"]], out))
        elif is_story(d.get("condition") or {}):
            stories.append(DAY_KO[d["day"]])
        else:
            hints.append(DAY_KO[d["day"]])
    parts = []
    if outs:
        clauses = [
            f"{day}요일 단서로 {_subject('·'.join(cs))}"
            if i == 0
            else f"{day}요일엔 {_subject('·'.join(cs)) if i == len(outs) - 1 else '·'.join(cs)}"
            for i, (day, cs) in enumerate(outs)
        ]
        if len(clauses) == 1:
            parts.append(f"{clauses[0]} {end('빠졌어')}.")
        else:
            first = f"{clauses[0]} 빠지고"
            middle = [*clauses[1:-1]]
            parts.append(", ".join([first, *middle, clauses[-1]]) + f" {end('빠졌어')}.")
    if hints:
        parts.append(
            f"{_join_days(hints)} 단서는 남은 후보를 가르지는 못했지만 정답과 딱 {end('맞았어')}."
        )
    if stories:
        parts.append(f"{_join_days(stories)} 단서는 사건이 어떻게 벌어졌는지 {end('알려 줬어')}.")
    answer = theme.get("answer") or ""
    if answer:
        parts.append(f"그래서 {answer}만 {end('남았어')}.")
    return " ".join(parts)


def compose_outro(theme: Theme) -> Theme:
    """종료 이야기 = 코드 정리 + LLM 마무리 장면.

    outroStory가 없으면(사람이 쓴 테마 등) 그대로 둔다.
    """
    if "outroStory" in theme:
        story = str(theme.get("outroStory") or "").strip()
        theme["outro"] = f"{outro_recap(theme)} {story}".strip()
    return theme


def elimination_summary(theme: Theme) -> str:
    """요일마다 그 단서로 새로 빠지는 후보와 마지막 남은 정답(종료 이야기 정리를 표와 맞출 때)."""
    remaining, parts = list(theme.get("candidates") or []), []
    for d in fill_rules_out(theme).get("days") or []:
        out = [c for c in d.get("rulesOut") or [] if c in remaining]
        remaining = [c for c in remaining if c not in out]
        parts.append(
            f"{DAY_KO[d['day']]}요일 {'·'.join(out) + ' 빠짐' if out else '빠지는 후보 없음'}"
        )
    return ", ".join(parts) + f" → 남은 정답 {theme.get('answer')}"


def clear_off_captions(theme: Theme) -> None:
    """자막 없는 컷의 caption을 비운다(#779 6컷 틀 B안: 자막은 중요한 순간 컷에만, 다시 생성 없이
    코드가 비움). 예전 4컷은 모든 컷이 자막 컷이라 그대로."""
    for scene, key in (("INTRO", "introCuts"), ("OUTRO", "outroCuts")):
        cuts = theme.get(key) or []
        specs = cut_layout.layout(len(cuts))[scene]
        for i, cut in enumerate(cuts, 1):
            if i <= len(specs) and not specs[i - 1].caption:
                cut["caption"] = ""


THANKS = re.compile(r"고마|고맙|감사")  # 종료 6컷 감사 말(#779 CUT_THANKS)


def caption_speaker(text: str) -> str | None:
    """'이름: 대사' 꼴 자막의 이름(꼴이 아니면 None)."""
    m = re.match(r"^\s*([^:：\s][^:：]{0,14}?)\s*[:：]\s*\S", text)
    return m.group(1).strip() if m else None


def caption_problems(theme: Theme, scene: str, i: int) -> list[str]:
    """자막 있는 컷의 자막 꼴(#779 사용자 결정 2026-11-19): 비지 않음, 글자 상한, 6컷은 '이름: 대사'
    이고 말하는 사람이 그 컷에 보임(뭉치 혼자 컷은 뭉치, 사람 컷은 그 컷 scene·action에 나오는
    인물, 함께 컷은 뭉치나 인물). 시작 1컷은 이름 없는 장면 소개. 자막 없는 컷은 보지 않음."""
    key = "introCuts" if scene == "INTRO" else "outroCuts"
    n = len(theme.get(key) or [])
    cut = theme[key][i - 1]
    spec = cut_layout.spec(scene, i, n)
    text = str(cut.get("caption") or "").strip()
    if not spec.caption:
        return []
    if not text:
        return [f"REQUIRED {key}{i}.caption"]
    bad = []
    limit = cut_layout.CAPTION_MAX.get(n, CAPTION_MAX)
    if len(text) > limit:
        bad.append(f"LENGTH {key}{i}.caption {len(text)}자 > {limit}")
    if n == 4 or spec.narrator:  # 예전 4컷(내레이터 자막)·시작 1컷 장면 소개
        return bad
    name = caption_speaker(text)
    people = [str(c.get("name") or "") for c in theme.get("characters") or [] if c.get("name")]
    matched = [p for p in people if name and (p == name or name in p or p in name)]
    where = f"{cut.get('scene') or ''} {cut.get('action') or ''}"
    if name is None:
        bad.append(f"CUT_SPEAKER {key}{i}.caption '이름: 대사' 꼴이 아님")
    elif spec.mungchi_alone and name != "뭉치":
        bad.append(f"CUT_SPEAKER {key}{i}.caption 뭉치 혼자 나오는 컷이라 말하는 사람은 '뭉치'")
    elif spec.who in ("PEOPLE", "OBJECT") and not matched:
        bad.append(
            f"CUT_SPEAKER {key}{i}.caption 사람만 나오는 컷이라 말하는 사람은 그 컷에 보이는 인물"
            f"({', '.join(people)}) 중 한 명('{name}' 아님)"
        )
    elif spec.who == "GROUP" and name != "뭉치" and not matched:
        bad.append(
            f"CUT_SPEAKER {key}{i}.caption 말하는 사람은 뭉치나 그 컷에 보이는 인물"
            f"({', '.join(people)}) 중 한 명('{name}' 아님)"
        )
    elif matched and not any(p in where or name in where for p in matched):
        bad.append(f"CUT_SPEAKER {key}{i}.caption '{name}'이(가) 그 컷 scene·action에 나오지 않음")
    answer = str(theme.get("answer") or "").strip()
    if (scene, i) == ("OUTRO", 1) and answer and not mentions_value(answer, text):
        bad.append(f"CUT_ANSWER {key}{i}.caption 뭉치가 정답({answer})을 말해야 함")
    if (scene, i) == ("OUTRO", 6) and (
        name == "뭉치" or not THANKS.search(text) or "뭉치" not in text
    ):
        bad.append(
            f"CUT_THANKS {key}{i}.caption 그 컷에 보이는 인물이 뭉치에게 고마워하는 말"
            "(예: '아린: 고마워, 뭉치!')"
        )
    return bad


def check_cuts(theme: Theme) -> list[str]:
    """시작·종료 영상 콘티: 정확히 6컷(#779), 칸 비지 않음, 자막 꼴·길이, 뭉치 표정.

    누가 나오는지는 컷 틀(cuts.LAYOUTS): 뭉치가 나오지 않는 컷(사람만·사건 물건)은 mungchiMood가
    none, 뭉치가 나오는 컷은 none이 아니다. 뭉치 혼자 달리는 컷만 달리기 낱말을 허용한다. 그림에
    나오면 안 되는 대상·후보 이름은 CUT_TARGET(#765).
    """
    bad = []
    for scene, key in (("INTRO", "introCuts"), ("OUTRO", "outroCuts")):
        cuts = theme.get(key) or []
        if len(cuts) != CUTS:
            bad.append(f"CUTS {key} {CUTS}컷 필요(지금 {len(cuts)}컷)")
            continue
        names = [str(c.get("name") or "") for c in theme.get("characters") or []]
        for i, cut in enumerate(cuts, 1):
            spec = cut_layout.spec(scene, i, CUTS)
            for k in ("scene", "action"):
                if not str(cut.get(k) or "").strip():
                    bad.append(f"REQUIRED {key}{i}.{k}")
            bad += caption_problems(theme, scene, i)
            may_run = spec.who == "RUN"  # 뭉치 혼자 달리는 컷(#779)
            for k in ("scene", "action"):
                for problem in cut_action_problems(
                    str(cut.get(k) or ""), spec.has_mungchi, may_run, names
                ):
                    bad.append(f"CUT_ACTION {key}{i}.{k} {problem}")
            mood = cut.get("mungchiMood")
            if mood not in MUNGCHI_MOODS:
                bad.append(f"CUT_MOOD {key}{i} mungchiMood는 {list(MUNGCHI_MOODS)} 중 하나")
            elif spec.has_mungchi and mood == "none":
                bad.append(f"CUT_MOOD {key}{i} 뭉치가 나오는 컷이라 none이 아님")
            elif not spec.has_mungchi and mood != "none":
                bad.append(f"CUT_MOOD {key}{i} 뭉치가 나오지 않는 컷이라 none")
    return bad + cut_target_problems(theme)


# #782 설계 v3(사용자 결정 2026-11-21): 어디서 왔을까 '동물' 갈래는 동물이 아이 곁에 있어 동물
# 자체의 특징(목줄·털·묻은 것)은 아이가 이미 안다. 온 곳의 특징(대문·창문·길)만 단서로(줄거리 다시)
ANIMAL_SELF_FEATURE = re.compile(r"목줄|털|몸|꼬리|발톱|발바닥|묻은|붙은|냄새|밴")


def known_feature_problems(theme: Theme) -> list[str]:
    if story_type(theme).code != "ORIGIN" or theme_branch(theme) != "동물":
        return []
    table, _ = feature_table(theme)
    return [
        f"FEATURE_KNOWN 특징 '{name}'은 아이 곁에 있는 동물 자체라 아이가 이미 앎(온 곳의 "
        "특징 — 대문·창문·길·바닥 등 — 으로)"
        for name in table
        if ANIMAL_SELF_FEATURE.search(name)
    ]


# #782 설계 v12(사용자 "치명결함은 왜 그대로 남기는거야"): 9차 치명 결함 종류마다 검사. 모두 저장
# 결과 7·8·9차(테마 100개)에서 잡은 것이 실제 결함이고 잘못 잡은 것 0. 각각 한 건씩으로만
# 확인해 같은 종류의 다른 말투는 글 검토 몫
# 소리 탐정 오늘 온 까닭에 들려준 사람(9차 snd5 시작 이야기 '할머니' ↔ 화요일 '이웃에게 들어')
SOUND_TELLER = re.compile(
    r"[가-힣]+(?:에게서|에게|한테서|한테|께)(?=[^.!?]*(?:전해|이야기|얘기|들었|들어|듣고|들은))"
)
# 자기 기록을 남의 말로(9차 way6b '내 일지엔 … 아니래!')
OWN_RECORD = re.compile(r"(?:내|제)\s?(?:일지|기록|메모|공책|영상|사진|수첩)")
HEARSAY_END = re.compile(r"(?:대|래)[!.?]*$")
# 사건 단서가 다른 요일 특징을 미리(9차 auto5b 수 '출입문 쪽으로' ↔ 금 '출입문과 거리'). 사건
# 단서에 흔히 나오는 흔적 낱말은 뺌(저장 결과의 '발자국이 이어졌어'·'바닥을 따라' 등 오탐)
STORY_TRACE_WORDS = {"자국", "발자국", "발굽", "모습", "곁에", "바닥"}
FEATURE_SPLIT = re.compile(r"[\s·]+|(?<=[가-힣])(?:과|와|의)(?=\s|$)")
# 오늘 온 까닭이 앞 요일 기록 내용을 댐(9차 new4 금 '일지에 나온 포장방 문턱' ↔ 목 일지 '뒷문')
STEP_RECORD_REF = re.compile(
    r"(?:일지|영상|메모|기록|사진|쪽지|수첩)(?:에|에서|엔|속)\s?"
    r"(?:나온|적힌|찍힌|본|담긴|나왔던)\s?([가-힣]+)"
)
# 오늘 온 까닭의 '어제 X'가 어제 단서·장면에 없음(11차 way3b 수요일 '어제 포장 끈이 날아간 쪽',
# 화요일에 포장 끈 없음 — 저장 결과 7~11차 200개 테마에서 이 1건만, 잘못 잡은 것 0). '어제 들은
# 걸'처럼 무엇을 했는지만 말하면 봄 밖
STEP_YESTERDAY = re.compile(r"어제\s?([가-힣]+)\s?([가-힣]+)?")
YESTERDAY_FIELDS = ("clue", "dayStep", "place", "helper", "sceneNote", "missionMaterial")
YESTERDAY_OK = {"들은", "본", "만난", "들었", "알게"}
# 비밀 재료 찾기 행사 이름(11차 hand5 시작 '잔치' ↔ 단서 '대회에 낼 떡' — 저장 결과 200개 테마에서
# 5건 모두 실제로 섞인 것. '장터'·'모임'·'행사'는 다른 뜻으로도 써 뺌)
EVENT_NAME = re.compile(r"대회|잔치|축제|발표회|시식회|공연")
# 선물 상자가 배달됐는데 등장인물이 들고 들어옴(9차 hand4 '이모는 리본 상자를 안고 복도를 지나왔어')
GIFT_IN = r"[은는이가]?\s?(?:\S+\s){0,3}?(?:안고|들고)\s?(?:\S+\s){0,2}?\S*(?:지나|왔|와|들어|걸어)"


def v12_problems(theme: Theme) -> list[str]:
    """#782 설계 v12 치명 결함 종류 검사(모두 그 칸 고쳐 쓰기).

    - SOUND_TELLER: 소리 탐정 오늘 온 까닭에 누구에게 들었는지(시작 이야기에서만 말함)
    - RECORD_HEARSAY: 자기 기록 단서를 '~래·~대'로
    - STORY_FEATURE: 사건(STORY) 단서에 다른 요일 특징 이름 낱말(시작 이야기·대상에 이미 있는
      낱말과 흔적 낱말은 뺌)
    - DAY_STEP_MADE: 오늘 온 까닭이 '일지에 나온 X'인데 X가 앞 요일 단서에 없음
    - GIFT_CARRY: 선물 시작 이야기가 배달인데 단서에 등장인물이 상자를 들고 옴
    - DAY_STEP_MADE: 오늘 온 까닭의 '어제 X'가 어제 단서·장면에 없음
    - EVENT_NAME: 비밀 재료 찾기에서 시작 이야기와 다른 행사 이름(잔치 ↔ 대회)
    - SOUND_SEEN: 소리 특징 단서(기록 날 빼고)를 '본'·'눈으로'로 씀"""
    days = theme.get("days") or []
    code = story_type(theme).code
    base = "".join(str(theme.get(k) or "") for k in ("intro", "target", "bigQuestion"))
    features = [str(x.get("name") or "") for x in theme.get("features") or []]
    names = [str(c.get("name") or "") for c in theme.get("characters") or [] if c.get("name")]
    bad = []
    for i, d in enumerate(days):
        day, clue, step = d.get("day"), str(d.get("clue") or ""), str(d.get("dayStep") or "")
        if code == "SOUND" and (m := SOUND_TELLER.search(step)):
            bad.append(
                f"SOUND_TELLER {day} dayStep에 '{m.group(0)}' — 누구에게 들었는지는 시작 이야기"
                "에서만 말함(오늘 온 까닭에 다시 대면 시작 이야기와 다른 사람이 됨)"
            )
        # #782 설계 v12: 소리 특징 단서를 '본'으로 씀(12차 snd4 '내가 직접 본 소리 난 곳은' — 약속은
        # 들은 소리라 글 검토가 어긋남으로 잡고, 대화를 다시 만들어도 고쳐지지 않아 실패)
        feature_now = str((d.get("condition") or {}).get("feature") or "")
        if (
            "소리" in feature_now
            and feature_now in features  # 표에 없는 특징은 CONDITION이 봄
            and (d.get("evidence") or {}).get("kind") != "RECORD"
            and CLUE_SEEN.search(clue)
        ):
            bad.append(
                f"SOUND_SEEN {day} clue 소리 특징인데 본 것으로 씀('본'·'눈으로') — 들은 것으로"
                "('내가 들은 소리는 ~')"
            )
        if OWN_RECORD.search(clue) and HEARSAY_END.search(clue.strip()):
            bad.append(
                f"RECORD_HEARSAY {day} clue 자기 기록인데 '~래·~대'로 남의 말처럼 씀(적혀 "
                "있어·찍혀 있어처럼)"
            )
        if (d.get("condition") or {}).get("kind") == "STORY":
            own = str((d.get("condition") or {}).get("feature") or "")
            hits = sorted(
                {
                    t
                    for f in features
                    if f != own
                    for t in FEATURE_SPLIT.split(f)
                    if len(t) >= 2 and t in clue and t not in base and t not in STORY_TRACE_WORDS
                }
            )
            if hits:
                bad.append(
                    f"STORY_FEATURE {day} clue 사건 단서에 다른 요일 특징 낱말 {hits}(사건이 "
                    "어떻게 벌어졌는지만, 다른 날 단서를 미리 가리키지 않음)"
                )
        if i and (m := STEP_RECORD_REF.search(step)):
            before = compact(" ".join(str(x.get("clue") or "") for x in days[:i]))
            if m.group(1)[:2] not in before:
                bad.append(
                    f"DAY_STEP_MADE {day} dayStep에 앞 요일 기록에 없는 것('{m.group(0)}') — "
                    "기록을 대면 그 기록 단서에 있는 것만"
                )
        if (
            code == "GIFT"
            and re.search(r"배달|택배", str(theme.get("intro") or ""))
            and any(re.search(re.escape(n) + GIFT_IN, clue) for n in names)
        ):
            bad.append(
                f"GIFT_CARRY {day} clue 선물 상자는 배달돼 왔는데 등장인물이 들고 왔다고 씀(사건 "
                "단서는 보내기 전 — 싸거나 배달원에게 건넬 때 — 본 것)"
            )
        if i and (m := STEP_YESTERDAY.search(step)):
            prev = days[i - 1]
            pool = compact(" ".join(str(prev.get(k) or "") for k in YESTERDAY_FIELDS))
            word = next((w for w in m.groups() if w and len(w) >= 2), "")
            if word and word not in YESTERDAY_OK and word[:2] not in pool:
                bad.append(
                    f"DAY_STEP_MADE {day} dayStep에 어제 없던 일('{m.group(0)}') — '어제 ~'는 어제 "
                    "단서·장면에 있던 일만"
                )
        if code == "SECRET_INGREDIENT" and (
            named := EVENT_NAME.findall(str(theme.get("intro") or ""))
        ):
            for k in ("clue", "dayStep", "missionMaterial"):
                other = sorted(
                    {e for e in EVENT_NAME.findall(str(d.get(k) or "")) if e not in named}
                )
                if other:
                    bad.append(
                        f"EVENT_NAME {day} {k}에 시작 이야기의 '{named[0]}'"
                        f"{josa(named[0], '과', '와')} 다른 행사 이름 {other}(다른 음식이 됨, "
                        f"'{named[0]}'{josa(named[0], '으로', '로')})"
                    )
    return bad


def check_theme(theme: Theme, grade: int, standard_codes: set[str] | None = None) -> list[str]:
    """check_theme 노드의 코드 검사. 빈 목록이면 통과."""
    mark_excluded(theme)  # #782 부정형 단서: 빠지는 값을 늘 최신 표·조건으로
    bad = known_feature_problems(theme)
    for k in (
        "title",
        "world",
        "styleNote",
        "outfit",
        "intro",
        "outro",
        "bigQuestion",
        "target",
        "answer",
    ):
        if not str(theme.get(k) or "").strip():
            bad.append(f"REQUIRED {k}")
    # 동물 주인공 가족(#634 ③)의 사건 물건·일(미션 소재), 정답 모습(종료 그림, ③·⑤
    # needs_answer_look)
    required = ["incident"] if is_animal(theme) else []
    if story_type(theme).needs_answer_look:
        required.append("answerLook")
    if len(theme.get("introCuts") or []) == cut_layout.NEW_CUTS:  # #779 6컷 컷 장소
        required += list(cut_layout.PLACE_KEY.values())
    bad += [f"REQUIRED {k}" for k in required if not str(theme.get(k) or "").strip()]
    chars = theme.get("characters") or []
    if not CHARACTERS[0] <= len(chars) <= CHARACTERS[1] or any(
        not (c.get("name") or "").strip() or not (c.get("look") or "").strip() for c in chars
    ):
        bad.append(f"CHARACTERS 등장인물 {CHARACTERS[0]}~{CHARACTERS[1]}명(이름·모습)")
    if any("뭉치" in (c.get("name") or "") for c in chars):
        bad.append("CHARACTERS 주인공 뭉치는 등장인물에 넣지 않음(뭉치 모습은 고정)")
    for k in ("title", "bigQuestion", "intro", "outro"):
        # 시작 이야기는 모델 몫만 센다(코드가 붙이는 규칙 문장은 상한 밖, #634 ④ — learning 상한
        # 2000자 안)
        text = intro_story(theme) if k == "intro" else str(theme.get(k) or "")
        if len(text) > TEXT_MAX[k]:
            bad.append(f"LENGTH {k} {len(text)}자 > {TEXT_MAX[k]}")
    if "outroStory" in theme:  # 마무리 장면(LLM 몫)만 보는 검사. 정리는 코드가 붙임(#535 7차)
        story = str(theme.get("outroStory") or "")
        if len(story) > OUTRO_STORY_MAX:
            bad.append(f"LENGTH outro {len(story)}자 > {OUTRO_STORY_MAX}")
        if m := WEEKDAY_WORDS.search(story):
            bad.append(
                f"OUTRO_RECAP outro 마무리 장면에 요일 정리('{m.group()}'), "
                "다섯 단서 정리는 코드가 앞에 "
                "붙이므로 쓰지 않음"
            )
        if others := outro_other_candidates(theme):
            bad.append(
                f"OUTRO_ANSWER outro 마무리 장면에 정답이 아닌 후보 {others}(정답 "
                f"{theme.get('answer')}과 어긋남 — 정답 그대로 씀)"
            )
    cands, answer = theme.get("candidates") or [], theme.get("answer") or ""
    if len(cands) != CANDIDATES[grade] or len(set(cands)) != len(cands):
        bad.append(f"CANDIDATES 서로 다른 후보 {CANDIDATES[grade]}개 필요(지금 {cands})")
    if answer not in cands:
        bad.append("ANSWER 정답이 후보 안에 없음")
    if any(not CANDIDATE_CHARS[0] <= len(compact(c)) <= CANDIDATE_CHARS[1] for c in cands):
        bad.append(f"CANDIDATES 후보는 {CANDIDATE_CHARS[0]}~{CANDIDATE_CHARS[1]}자")
    if any(COLOR.search(c) for c in cands):
        bad.append("CANDIDATES 후보 이름에 색 낱말(색으로 빼면 이름과 모순)")
    if story_type(theme).code == "TREASURE":
        bad += hide_spot_problems(theme)
    bad += clue_proof_problems(theme)
    bad += clue_absent_problems(theme)  # #634 ④ 없는 값 단서(다시 생성)
    bad += place_problems(theme)  # #634 ④ 여객선은 물가에서만(다시 생성)
    bad += time_word_problems(theme)  # #634 ④ 시간 탐정 엔딩 전 시각(칸 고쳐 쓰기)
    bad += intro_story_problems(theme)  # #782 설계 v4 시작 이야기의 때·밤·맡긴 곳
    bad += day_step_problems(theme)  # #782 설계 v7 오늘 온 까닭(지어냄·자기 이름)
    # #782 설계 v6: 맡겨 둔 대상의 흔적·맡은 사람, 아이가 본 발자국. v7: 시작 이야기 시각,
    # 비밀 재료의 아직 안 열린 잔치, 사건 단서의 아이 자신
    bad += kept_trace_problems(theme) + seen_trace_problems(theme) + intro_clock_problems(theme)
    bad += event_later_problems(theme) + story_self_problems(theme)
    # #782 설계 v10: 아이가 이미 아는 것(시작 이야기·오늘 온 까닭, 칸 고쳐 쓰기), 시간 탐정의 그
    # 일을 한 사람(줄거리 다시). 사건 단서의 시작 이야기 모습(intro_seen_clue)은 오탐을 재기 전이라
    # 뺌
    bad += child_known_problems(theme) + when_doer_problems(theme)
    bad += v12_problems(theme)  # #782 설계 v12: 9차 치명 결함 종류(칸 고쳐 쓰기)
    if (table := story_type(theme).facts) is not None:  # 사실표 종류(동물·선물·재료, #634)
        bad += fact_table_problems(theme)
        # target은 미션·대화·그림 모델에 그대로 넘어가 정답 유출 검사 밖이라 후보 이름·정답만의
        # 표 값이 없어야 함(설계 17.8.5·17.8.13)
        if named := candidate_names(theme, theme.get("target")) + answer_fact_hits(
            theme, theme.get("target")
        ):
            bad.append(
                f"TARGET_NAMES target에 후보 {table.name} 이름 {named}(정답을 드러내지 않는 말로)"
            )
        for path, text in candidate_name_fields(theme):
            if named := candidate_names(theme, text):
                bad.append(f"CANDIDATE_NAME {path}에 후보 {table.name} 이름 {named}(엔딩 전 글)")
            # #782 설계 v13: 수사 날 지문 증언에는 그날 단서 내용이 들어감(그 값은 뺌)
            said_ok = testimony_ok(theme, path)
            if hits := [v for v in answer_fact_hits(theme, text) if v not in said_ok]:
                which = "후보를 가르는" if story_type(theme).strict_facts else "정답만의"
                bad.append(f"ANSWER_FACT {path}에 {which} {table.name} 값 {hits}(엔딩 전 글)")
    days = theme.get("days") or []
    if tuple(d.get("day") for d in days) != DAYS:
        return bad + [f"DAYS 요일은 {list(DAYS)} 순서(지금 {[d.get('day') for d in days]})"]
    for d in days:
        if d.get("thinkingType") != DAY_TYPE[d["day"]]:
            bad.append(f"DAYS {d['day']} 유형은 {DAY_TYPE[d['day']]}")
        for k in DAY_TEXTS:
            v = d.get(k) or ""
            if not v.strip():
                bad.append(f"REQUIRED {d['day']}.{k}")
            elif len(v) > day_text_max(d, k, theme):
                bad.append(f"LENGTH {d['day']}.{k} {len(v)}자 > {day_text_max(d, k, theme)}")
        # #782 설계 v10: 국어 부탁 날은 아이 답의 쓰임(helperUse)이 있어야 함(칸 고쳐 쓰기로
        # 써 넣음)
        use = str(d.get("helperUse") or "")
        if helper_use_day(theme, d) and not use.strip():
            bad.append(f"REQUIRED {d['day']}.helperUse")
        elif len(use) > TEXT_MAX["helperUse"]:
            bad.append(f"LENGTH {d['day']}.helperUse {len(use)}자 > {TEXT_MAX['helperUse']}")
        # 단서는 그날 미션을 마친 뒤 보여 주므로 증거 발견 줄은 단서 결론을 말하지 않는다. 수사 연결
        # 문장은 그날 배울 개념을 말하는 자리라 개념 낱말이 단서 값과 같을 수밖에 없어
        # (특징을 성취기준
        # 내용에서 고름, 실측 repo-fair4-3) 코드로 막지 않고 글 검토(정답 암시)가 본다
        slot = plan_slot(theme, d["day"])
        planned = evidence_plan_problems(d, slot) if slot else []
        bad += planned
        clue_planned = any(r.startswith(f"CLUE_EVIDENCE {d['day']} clue ") for r in planned)
        if not clue_planned and clue_evidence_mismatch(d):  # 같은 칸 사유를 두 번 내지 않음
            bad.append(
                f"CLUE_EVIDENCE {d['day']} clue 단서 문장의 "
                "증거와 evidence 종류가 다름(사진·영상·녹음·기록·"
                "일지·메모를 말하면 RECORD, RECORD면 그 기록을 말함)"
            )
        elif not clue_planned and sighting_names_trace(theme, d):
            bad.append(
                f"CLUE_EVIDENCE {d['day']} clue 목격 날 단서가 대상에 남은 흔적을 말함(그 "
                "길·가게에서 "
                "대상을 나르거나 든 사람을 본 목격으로 씀)"
            )
        for problem in clue_wording_problems(d):
            bad.append(f"CLUE_WORDING {d['day']} clue {problem}")
        for problem in clue_source_problems(theme, d):
            bad.append(f"CLUE_SOURCE {d['day']} clue {problem}")
        # 흔적 단서는 누구의 흔적인지 밝힌다(#535 6차: "흔적이 대상의 것인지 드러나지 않음").
        # 칸 고쳐 쓰기 대상
        trace = (d.get("evidence") or {}).get("kind") == "TRACE"
        owner_all = story_type(theme).owner_all  # 출처 찾기·길: 모든 단서(마지막 확인)
        # #782 설계 v8: 사건 단서 날은 온 사람 낱말만(아래). 탈것 '바퀴'를 넣으면 바퀴 자국이
        # 있었다는 뜻이 되어 후보를 가름(3·5차 글 검토 CLUE_LOGIC 7·ANSWER_HINT 4)
        story_person = is_story(d.get("condition") or {}) and bool(clue_person(theme))
        if (
            (trace or owner_all)
            and not story_person
            and target_words(theme)
            and not names_target(theme, d.get("clue"))
        ):
            bad.append(
                f"CLUE_OWNER {d['day']} clue {'' if owner_all else '흔적 '}단서에 찾는 대상 낱말"
                f"({'·'.join(target_words(theme))})이 "
                "없음(누구의 흔적인지 밝힘)"
            )
        # #634 ④ 탈것 찾기: 모든 단서는 온 사람이 탄 탈것의 증거임을 밝힘(작은 실측: '따르릉 소리가
        # 났다'만 써서 글 검토 CLUE_LOGIC "그 소리가 할머니의 탈것에서 났다는 연결이 없음")
        person = clue_person(theme)
        if person and person not in compact(d.get("clue")):
            why = (
                f"'{person}' 낱말이 없음(그 소리의 증거임을 밝힘)"
                if story_type(theme).clue_word
                else f"온 사람('{person}')이 없음(그 사람이 탄 탈것의 증거임을 밝힘)"
            )
            bad.append(f"CLUE_OWNER {d['day']} clue 단서에 {why}")
        # 부탁 날 증거 발견 줄은 그날 단서가 나오는 곳이고 문제 전에 학생에게 보이지 않는
        # 내부 메모라 보지 않는다(#782 실측 r782-ways-rd3~rd6: 글 검토 ANSWER_HINT 10번 중 8번이 이
        # 날들의 증거 발견 줄을 지적해 줄거리를 다시 만들고 마감에 걸림)
        if mission_way(d) == INVESTIGATE and (early := early_values(d, d.get("discovery"))):
            bad.append(f"CLUE_EARLY {d['day']} discovery에 그날 단서 결론(허용 값 {early})")
        # 장면 메모가 증거가 남은 자리의 특징 값을 말하면 대화·그림이 문제 전에 단서를 알려 줌
        # (실측 2026-11-15·16 글 검토 ANSWER_HINT: '흙길의 발자국'). 칸 고쳐 쓰기로 고침(#535)
        if early := early_values(d, d.get("sceneNote")):
            bad.append(f"CLUE_EARLY {d['day']} sceneNote에 그날 단서 결론(허용 값 {early})")
        # 미션 지문이 될 증거 내용(#782)도 문제 전에 학생이 읽어 단서 결론·후보 이름을 막음.
        # #782 설계 v13: 수사 날 지문은 그때 직접 본 사람의 증언이고 그날 단서 내용이 들어 있어야
        # 함(단서는 따져서 확실해진 그 내용). v11처럼 막으면 단서가 지문에 없는 사실을 말해 글 검토
        # CLUE_LOGIC → 줄거리부터 다시(10~13차 느린·실패 테마). 증거 발견 줄·할 일은 그대로 막음
        if testimony_day(d):
            says = clue_says(d)
            if (
                says
                and not is_story(d.get("condition") or {})
                # 들어 있어야 하는 검사라 활용형(젖음→젖어)도 봄(value_in_text, 단서 문장과
                # 같은 잣대)
                and not any(value_in_text(v, d.get("missionMaterial")) for v in says)
            ):
                bad.append(
                    f"TESTIMONY_MISSING {d['day']} missionMaterial 수사 날 증언에 그날 단서 내용"
                    f"(값 {says}, 단서와 같은 꼴)이 없음 — 그때 직접 본 사람의 말에 넣음(단서는 "
                    "따져서 확실해진 그 증언 내용)"
                )
        elif early := early_values(d, d.get("missionMaterial")):
            bad.append(f"CLUE_EARLY {d['day']} missionMaterial에 그날 단서 결론(허용 값 {early})")
        # 오늘 온 까닭(#782 테마 짜임 기준안): 대화 모델 재료라 문제 전에 학생이 읽는 글. 그날·앞
        # 요일 단서 결과를 말하지 않는다(사용자 결정 2026-11-19 "어제 한 일만 잇기": 문제는 순서
        # 없이 풀 수 있어 앞 요일 단서를 아직 못 얻은 학생이 있음). 비면 위 DAY_TEXTS 검사가
        # REQUIRED
        if early := early_values(d, d.get("dayStep")):
            bad.append(f"CLUE_EARLY {d['day']} dayStep에 그날 단서 결론(허용 값 {early})")
        if prev := prev_values(theme, d["day"], d.get("dayStep")):
            bad.append(f"PREV_CLUE {d['day']} dayStep에 앞 요일 단서 결과(허용 값 {prev})")
        # 수사 연결 문장(대화 모델 재료). 전에는 대화 마지막 줄로 그대로 나가 줄거리 검사에서도
        # 봤고(사용자 결정 2026-11-19 웹 '오늘 장면' 대비), 이제 대화 재료로 남아도 같은 까닭으로
        # 봄. #535에서는 '<증거>를 풀려면 <배울 것>이 필요해' 형식이라 배울 개념에 값 낱말이 나와
        # 보지 않았지만, C안은 단서 특징 값과 무관한 증거의 한 부분을 가리킨다
        if early := early_values(d, d.get("missionHook")):
            bad.append(f"CLUE_EARLY {d['day']} missionHook에 그날 단서 결론(허용 값 {early})")
        if acts := act_names(d.get("missionHook")):
            bad.append(
                f"ACT_NAME {d['day']} missionHook에 학생이 글로 할 수 없는 활동 이름"
                f"({'·'.join(acts)}). 그 생각 부분(정리·요약·비교·판단·계산)으로 청한다"
            )
        if acts := act_orders(d.get("missionMaterial")):  # #782 설계 v7 지문 속 시키는 말
            bad.append(
                f"ACT_NAME {d['day']} missionMaterial에 학생이 글로 할 수 없는 활동을 시키는 "
                f"말({'·'.join(acts)}). 지문은 이야기 속 글이라 시키지 않고 자료만 둔다"
            )
        for k in ("discovery", "missionHook", "missionMaterial"):
            named = [c for c in cands if c != answer and compact(c) in compact(d.get(k))]
            if named:
                bad.append(f"ANSWER_LEAK {d['day']}.{k}에 후보 이름 {named}")
        bad += way_problems(d)  # #782 미션 방식 흐름
        # #782 설계 v9: 수학 날 지문·할 일이 그 학년이 아직 배우지 않은 셈을 시키면 미션을 몇 번
        # 다시 만들어도 같은 셈(6차 snd3b '남은 1/4통에 2/4통을 더 채움')
        if any("수" in c for c in frame_of(theme, d["day"]).get("codes") or []):
            for k in ("missionMaterial", "missionHook"):
                if ahead := math_ahead([str(d.get(k) or "")], grade):
                    bad.append(
                        f"GRADE_MATH {d['day']} {k}에 초{grade}에서 아직 배우지 않은 수학 개념"
                        f"({'·'.join(ahead)}) — 그 학년이 배운 셈으로 풀리는 자료·부탁으로"
                    )
    bad += helper_problems(theme)  # #782 미션 방식: 요일마다 다른 그날 사람
    if day1_time(theme, str(theme_day(theme, "MON").get("dayStep") or "")):
        bad.append(
            "DAY1_TIME MON dayStep에 '어제'(첫날은 시작 이야기의 사건에서 이어짐, 시작 이야기에 "
            "없는 때를 지어내지 않음)"
        )
    bad += check_logic(theme, cands, answer, days)
    values = [
        v.get("value", "") for f in theme.get("features") or [] for v in f.get("values") or []
    ]
    if any("π" in str(x) for x in [*values, *(d.get("clue") or "" for d in days)]):
        bad.append("GRADE_MATH 특징 표·단서에 π 기호(초등에서 쓰지 않음, 3.14로 계산한 값으로)")
    bad += check_cuts(theme)
    types = [d.get("clueType") for d in days]
    if any(x not in CLUE_TYPES for x in types) or len(set(types)) != len(types):
        bad.append(f"CLUE_TYPE 다섯 단서는 서로 다른 종류(지금 {types})")
    if answer:  # 정답 이름은 종료 이야기에만
        key = compact(answer)
        fields = [
            (k, intro_story(theme) if k == "intro" else theme.get(k))
            for k in ("title", "world", "intro", "bigQuestion", "styleNote", "outfit")
        ]
        fields += [(f"{d['day']}.{k}", d.get(k)) for d in days for k in DAY_TEXTS]
        fields += [
            (f"characters.{c.get('name')}", (c.get("name") or "") + (c.get("look") or ""))
            for c in chars
        ]
        # 시작 영상 콘티도 정답 전(종료 콘티는 정답을 보여 줌)
        fields += [
            (f"introCuts{i + 1}.{k}", c.get(k))
            for i, c in enumerate(theme.get("introCuts") or [])
            for k in ("scene", "action", "caption")
        ]
        bad += [f"ANSWER_LEAK {name}에 정답 이름" for name, text in fields if key in compact(text)]
    dumped = json.dumps(theme, ensure_ascii=False)
    if hit := UNSAFE.findall(dumped):
        bad.append(f"UNSAFE {sorted(set(hit))}")
    if FOREIGN.search(dumped):
        bad.append("LANGUAGE 한국어 밖 글자(가나·한자)")
    for f in theme.get("features") or []:
        code = f.get("standardCode")
        if code and standard_codes is not None and code not in standard_codes:
            bad.append(
                f"FEATURE_SOURCE {f.get('name')}의 standardCode {code}는 이번 주 성취기준이 아님"
            )
    for d in days:
        ev = d.get("evidence") or {}
        if ev.get("kind") not in EVIDENCE_KINDS:
            bad.append(f"EVIDENCE {d['day']} 증거 종류는 {list(EVIDENCE_KINDS)} 중 하나")
        if not (ev.get("when") or "").strip():
            bad.append(f"EVIDENCE {d['day']} 증거가 생긴 때(when) 필요")
    return bad


# 학년별로 아직 배우지 않은 수학 개념(기준안, 2022 개정 교육과정 학년 배치: 소수 두 자리·다각형·각도
# 4학년, 넓이·약수와 배수·분수의 곱셈·평균 5학년, 분수의 나눗셈·비와 비율·원주율·겉넓이와 부피
# 6학년, π 기호는 중학교). 테마 수학 미션(목요일)이 성취기준보다 앞선 개념을 써 글 검토
# GRADE_VOCAB로 다시 만들던 것을 미션 단계에서 코드가 잡음(#535 9차: 분수 나눗셈
# 확인식·비율·겉넓이·π, 사용자 2026-11-16)
MATH_AHEAD: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("소수 둘째 자리", re.compile(r"\d+\.\d{2,}"), 4),
    # #782 설계 v9: 6차 초3 '5/7-2/7'·'1/4통+2/4통'을 글 검토가 GRADE_VOCAB로 잡음(실패 2건). 분모가
    # 같은 분수의 크기 비교는 초3이라 셈 기호·'분수의 덧셈'만 봄
    (
        "분수의 덧셈·뺄셈",
        re.compile(r"\d+/\d+\s*[가-힣A-Za-z]{0,3}\s*[+\-−]\s*\d+/\d+|분수의\s?(?:덧셈|뺄셈)"),
        4,
    ),
    ("다각형", re.compile(r"다각형"), 4),
    ("각도", re.compile(r"(?<![가-힣])각도|\d+\s?°(?!\s?C)"), 4),  # '생각도'·온도 °C는 뺌
    ("넓이", re.compile(r"(?<![가-힣])넓이"), 5),  # '겉넓이'는 아래 6학년
    ("약수·배수", re.compile(r"약수|배수"), 5),
    ("분수의 곱셈", re.compile(r"\d+/\d+\s*[×x]\s*\d|\d\s*[×x]\s*\d+/\d+"), 5),
    ("평균", re.compile(r"평균"), 5),
    ("분수의 나눗셈", re.compile(r"\d+/\d+\s*÷|÷\s*\d+/\d+"), 6),
    ("비율·백분율", re.compile(r"비율|백분율|\d\s?%"), 6),
    ("원주율", re.compile(r"원주율"), 6),
    ("겉넓이·부피", re.compile(r"겉넓이|부피|㎤|cm³"), 6),
    ("π 기호", re.compile(r"π"), 7),
)


def math_ahead(texts: list[str], grade: int) -> list[str]:
    """그 학년에서 아직 배우지 않은 수학 개념 이름(MATH_AHEAD)."""
    joined = "\n".join(texts)
    return [
        name for name, pattern, learned in MATH_AHEAD if grade < learned and pattern.search(joined)
    ]


def check_mission(
    theme: Theme,
    request: MissionDraftRequest,
    draft: Draft,
    grade: int,
    question_max: dict[int, int],
    overlap: int,
) -> list[str]:
    """테마 미션 검사: 기존 미션 초안 ai 검사 + 학년별 생각 열기 개수 + 테마 정답 유출 + 언어.

    수사 연결 문장은 질문이 아니라 문제 앞 대화 마지막 말로 나간다(질문에 넣으면 증거 내용을 살피게
    돼 자료 부족·길이 초과로 막혔음, 실측 repo-beach5-3·museum6-3, 사용자 결정 2026-11-11. #782
    테마 짜임부터 대화 모델이 풀어 씀)."""
    bad = [
        f"{f.check} {f.reason}" for f in mission_checks.check(draft, request, question_max, overlap)
    ]
    if "LEAK ANSWER_KEY" in bad and not material_number_leak(theme, request, draft):
        bad = [r for r in bad if r != "LEAK ANSWER_KEY"]  # #782 설계 v8 지문의 수·분수 오탐
    hints = len([h for h in draft.hints if h.strip()])
    if hints != HINTS[grade]:
        bad.append(f"HINT_COUNT 생각 열기 질문 {hints}개(초{grade}는 {HINTS[grade]}개)")
    key = compact(theme["answer"])
    texts = [
        draft.question,
        draft.guide or "",
        *draft.hints,
        draft.example_answer or "",
        *[c.label for c in draft.choices or []],
    ]
    if key and any(key in compact(x) for x in texts):
        bad.append(
            "THEME_ANSWER_LEAK 문제·안내·생각 열기 질문·예시 "
            f"답에 테마 정답 낱말 '{theme['answer']}'"
            "(장소 후보 이름은 쓰지 않음)"
        )
    if any(FOREIGN.search(x) for x in [*texts, draft.title]):
        bad.append("LANGUAGE 한국어 밖 글자(가나·한자)")
    # 동물 주인공 가족(#634 ③): 미션이 후보 동물을 말하면 정해진 단서보다 먼저 근거가 샘(설계 17.8.5
    # 남은 위험, 프롬프트로 먼저 막고 새면 그 미션만 다시)
    joined = "\n".join([draft.title, *texts])
    # #782 설계 v13: 수사 날은 지문 증언에 그날 단서 내용이 들어가고 예시 답이 그 증언을 따지므로
    # 그날 단서 값은 정답 값으로 막지 않음(후보 이름은 그대로 막음)
    mday = {v: k for k, v in DAY_TYPE.items()}.get(request.thinking_type)
    said_ok = testimony_ok(theme, f"{mday}.missionMaterial") if mday else []
    if story_type(theme).hide_candidates and (
        named := candidate_names(theme, joined)
        + [v for v in answer_fact_hits(theme, joined) if v not in said_ok]
    ):
        name = story_type(theme).facts.name  # type: ignore[union-attr]
        bad.append(
            f"CANDIDATE_NAME 문제·안내·생각 열기 질문·예시 답에 후보 {name} 이름·정답 값 {named}"
        )
    # #782 설계 v10(2.3): 문제·예시 답이 아직 안 열린 행사를 이미 열린 것처럼 씀(7차 auto4b 금
    # '별빛 캠핑을 마친 네 마음' — 시작은 '별 보기 모임 직전'). 그 미션만 다시
    # 월요일은 시작 이야기가 전날 밤 일이면 됨(DAY1_NIGHT)
    intro_night = DAY1_NIGHT.search(str(theme.get("introStory") or theme.get("intro") or ""))
    if (m := INCIDENT_AGO.search(f"{draft.question}\n{draft.example_answer or ''}")) and not (
        mday == "MON" and intro_night
    ):
        bad.append(
            f"INCIDENT_TIME 문제·예시 답이 사건 때를 '{m.group(0)}'처럼 오늘 기준 지난 때로 씀 — "
            "사건은 월요일 전 일이라 '그날 밤·그때'로"
        )
    if hits := event_later_hits(theme, "\n".join([draft.question, draft.example_answer or ""])):
        bad.append(
            f"EVENT_LATER 문제·예시 답이 아직 열리지 않은 행사를 이미 열린 것처럼 씀({hits}) — "
            "시작 이야기에서 앞으로 열릴 일이라 '~에 낼·준비·앞둔'처럼 앞일로만"
        )
    # #782 설계 v3: 국어 부탁 날은 아이 답이 돕는 사람의 일에 쓰이는 곳을 질문에 밝힌다(2차
    # 측정 억지
    # 30일 중 9일 "답이 그 일에 안 쓰임")
    # #782 설계 v10: 쓰임 낱말은 모델이 쓴 helperUse에서 뽑음(정해 둔 목록 아님), 예전 저장본은
    # dayFrames 쓰임 낱말(day_use)
    day = {v: k for k, v in DAY_TYPE.items()}.get(request.thinking_type)
    use, words = day_use(theme, day) if day else ("", [])
    if (
        words
        and mission_way(theme_day(theme, day)) == ASK
        and not any(w in draft.question for w in words)
    ):
        bad.append(
            f"USE_MISSING 문제 글에 아이 답의 쓰임이 없음(돕는 사람이 '{use}'라고 한 뜻을 "
            f"question에 씀, 낱말 {'·'.join(words)} 중 하나)"
        )
    if acts := mission_act_names(theme, request, draft):
        bad.append(
            f"ACT_NAME 제목·문제·안내·생각 열기 질문에 학생이 글로 할 수 없는 활동 이름"
            f"({'·'.join(acts)}). 글로 대신하는 날은 그 활동 이름으로 시키지 않고 생각 부분만 "
            "이야기 안의 목적으로 시킨다(예: '발표 글을 써 봐' 대신 '본 모습을 두 문장으로 정리해 "
            "○○에게 알려 줘', '그래프로 나타내' 대신 '눈금 한 칸을 얼마로 할지 정하고 해석해')"
        )
    if any("수" in st.code for st in request.standards):  # 수학 미션만(성취기준 코드 4수·6수)
        final = draft.answer_key.final_answer if draft.answer_key else None
        if ahead := math_ahead([*texts, final or ""], grade):
            bad.append(
                f"GRADE_MATH 초{grade}에서 아직 배우지 않은 수학 개념({'·'.join(ahead)}). "
                "그 학년이 배운 수·연산으로 문제·예시 답·확인 방법을 씀"
            )
    limit, n = EXAMPLE_SENTENCES[grade], sentence_count(draft.example_answer)
    # #782 설계 v8: 줄이 셋 이상인 예시 답(시·면담 대화)은 줄마다 한 문장으로 세져 6턴 면담·6행
    # 시가 늘 걸림 — 문장 수로 보지 않음
    lines = [x for x in (draft.example_answer or "").splitlines() if x.strip()]
    if request.input_type in EXAMPLE_LONG_TYPES and n > limit and len(lines) < 3:
        bad.append(
            f"EXAMPLE_LONG 예시 답 {n}문장(초{grade}는 {limit}문장까지). 그 학년 아이가 쓸 만한 "
            "쉬운 말로 짧게, 채점 요소는 모두 담음"
        )
    return bad + material_problems(theme, request, draft)


def sentence_count(text: str | None) -> int:
    """문장 수(마침표·물음표·느낌표·줄바꿈으로 나눔, 두 글자 미만 조각은 셈에서 뺌)."""
    return sum(1 for x in SENTENCE.findall(text or "") if len(x.strip(" .?!")) >= 2)


# 미션 지문(#782): 문제 글에 그대로 들어갔는지 보는 정규화(공백·문장부호·따옴표 무시)와 기준
MATERIAL_COVER = (
    0.85  # 지문 글자 중 문제 글과 맞는 비율이 이보다 낮으면 지문을 쓰지 않은 것(기준안)
)
MATERIAL_NUMBER = re.compile(r"\d+(?:\.\d+)?(?:/\d+)?")


def _bare(text: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", text or "")


def _covered(part: str, whole: str) -> float:
    """part(정규화) 글자 중 whole(정규화)과 맞는 부분의 비율."""
    a, b = _bare(part), _bare(whole)
    if not a:
        return 1.0
    blocks = difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
    return sum(m.size for m in blocks if m.size >= 3) / len(a)


def material_numbers(text: str | None) -> list[str]:
    """지문에 나온 수(분수·소수 포함). 수학 미션의 최종 답이 되면 문제 글에 답이 보임(LEAK)."""
    return list(dict.fromkeys(MATERIAL_NUMBER.findall(text or "")))


SENTENCE = re.compile(r"[^.?!\n]+[.?!]?")


def day_material(theme: Theme, request: MissionDraftRequest) -> str:
    """미션 요청 생각 유형의 요일 지문(missionMaterial). 예전 저장본·요일 밖은 빈 글."""
    day = next((d for d, t in DAY_TYPE.items() if t == request.thinking_type), None)
    return str(theme_day(theme, day).get("missionMaterial") or "") if day else ""


def without_material(question: str, material: str) -> str:
    """문제 글에서 지문 문장(8자 이상)을 지운다. 시키는 끝으로 맺은 지문 문장은 남김(#782 설계
    v7 — 학생에게 시키는 말)."""
    for sentence in SENTENCE.findall(material):
        if len(sentence.strip()) >= 8 and not act_orders(sentence):
            question = question.replace(sentence.strip(), " ")
    return question


def material_number_leak(theme: Theme, request: MissionDraftRequest, draft: Draft) -> bool:
    """숫자 답 LEAK ANSWER_KEY가 실제 유출인지(#782 설계 v8). 지문 문장을 뺀 문제 글·안내·생각 열기
    질문에서 분수·소수를 한 덩어리로 다시 본다(3·4·5차 LEAK 20번 중 17번이 지문의 수, 8번은
    분수 '2/3'의 2를 답 2로 본 오탐). 글 답(고르기 이름 등)이면 늘 유출로 둔다."""
    final = (draft.answer_key.final_answer or "") if draft.answer_key else ""
    tokens = MATERIAL_NUMBER.findall(final)
    if not tokens or re.sub(r"[\d.,/\s]", "", final):
        return True
    texts = [without_material(draft.question, day_material(theme, request)), draft.guide or ""]
    texts += list(draft.hints)
    return any(t in MATERIAL_NUMBER.findall(x) for x in texts for t in tokens)


def mission_act_names(theme: Theme, request: MissionDraftRequest, draft: Draft) -> list[str]:
    """제목·문제·안내·생각 열기 질문이 학생에게 할 수 없는 활동을 그 이름으로 시키는지(ACT_NAME).

    문제 글에 그대로 들어간 그날 지문(missionMaterial)은 이야기 속 사실이라 뺀다(예: 지문의 '발표할
    그림 자료'는 시키는 말이 아님). 지문 문장이 문제 글에 그대로 있을 때만 지운다.
    """
    question = without_material(draft.question, day_material(theme, request))
    texts = [draft.title, question, draft.guide or "", *draft.hints]
    return list(dict.fromkeys(a for t in texts for a in act_names(t)))


def material_problems(theme: Theme, request: MissionDraftRequest, draft: Draft) -> list[str]:
    """줄거리가 정한 그날 미션 지문(missionMaterial, #782)을 미션이 그대로 썼는지(그 요일만 다시).

    지문을 쓰지 않으면 다시 사건과 무관한 글로 빠진다. 수학은 지문의 수가 그대로 최종 답이면
    문제 글에 답이 보여 LEAK이 되풀이돼 따로 알린다(실측 40건 LEAK 2 → 0). 지문 밖 글을 덧붙인
    것은 코드로 막지 않는다: 막아 봤더니 미션 생성기가 다시 만들어도 같은 위반을 되풀이해 초안 5건이
    통째로 실패하고(통과 37 → 27/40) 증거 비율도 오르지 않아, 지금처럼 미션 검토 STORY_LINK
    경고로 관리자에게 보인다. 예전 저장본(지문 없음)은 보지 않는다.
    """
    day = next((d for d, t in DAY_TYPE.items() if t == request.thinking_type), None)
    material = str(theme_day(theme, day).get("missionMaterial") or "") if day else ""
    if not material.strip():
        return []
    bad = []
    # #782 설계 v8: 지문 끝 부탁·쓰임 문장은 미션이 자기 말로 옮겨도 됨(REQUEST_END)
    core = (
        " ".join(
            x
            for x in SENTENCE.findall(material)
            if not REQUEST_END.search(x) and not ORDER_END.search(x)
        ).strip()
        or material
    )
    if _covered(core, draft.question) < MATERIAL_COVER:
        bad.append(
            "MATERIAL_MISSING 문제 글에 줄거리가 정한 오늘 지문이 그대로 없음(지문을 question 안에 "
            "낱말을 바꾸지 않고 넣고 그 지문으로 활동)"
        )
    final = (draft.answer_key.final_answer or "") if draft.answer_key else ""
    hit = [n for n in material_numbers(final) if n in material_numbers(material)]
    if hit:
        bad.append(
            f"MATERIAL_ANSWER 최종 답의 수 {hit}가 지문에 이미 있음(지문의 수로 계산해 새로 나오는 "
            "값을 최종 답으로)"
        )
    # #782 설계 v12: 수사 날 문제가 누가 본 일을 설명해 준다고 하고 그 말(단서 값)을 보여 주지 않음
    # (9차 new3 '가게 주인이 그때 본 일을 설명하고' — 저장 결과 수사 날 16개 중 1, 잘못 잡은 것 0)
    d = theme_day(theme, day) if day else {}
    if mission_way(d) == INVESTIGATE and TESTIMONY_SAID.search(
        without_material(draft.question, material)
    ):
        cond = d.get("condition") or {}
        values = [*(cond.get("allowed") or []), *(cond.get("excluded") or [])]
        if not any(compact(v) in compact(draft.question) for v in values):
            bad.append(
                "MISSION_TESTIMONY 문제가 누가 본 일을 설명해 준다고 하고 그 말을 보여 주지 않음"
                "(미덥지 않은 자료만 따지게 하고, 믿을 만한 증언은 미션 뒤 단서로 — '설명하고'를 "
                "쓰지 않음)"
            )
    return bad


TESTIMONY_SAID = re.compile(
    r"(?:본|들은)\s?(?:일|것|걸|모습|이야기)[을를]?\s?(?:설명|말해|알려|들려)"
)


def hook_problems(theme: Theme, day: str, hook: str, draft: Draft, overlap: int) -> list[str]:
    """미션 뒤 고쳐 쓴 수사 연결 문장이 그날 문제의 답·예시 답·단서 결론을 미리 말하는지(#535 닫기).

    수사 연결 문장은 줄거리 검사만 거치고 대화 재료로만 쓰이는데(#782 테마 짜임 전에는 대화 끝 줄로
    그대로 나가 대화 유출 검사에서 빠졌음), 미션을 본
    뒤 고쳐 쓰면 문제의 답을 담을 수 있다(실측 2026-11-15 닫기 3차: 고를 자료 '기억 메모'를 미리
    지정해 글 검토 ANSWER_HINT). 걸리면 고쳐 쓰기를 버리고 원래 문장을 둔다.
    """
    d = theme_day(theme, day)
    bad = []
    if early := early_values(d, hook):
        bad.append(f"CLUE_EARLY 그날 단서 결론(허용 값 {early})")
    if acts := act_names(hook):
        bad.append(f"ACT_NAME 학생이 글로 할 수 없는 활동 이름({'·'.join(acts)})")
    # #782 미션 방식: 줄거리 단계에서 맞춘 흐름이 고쳐 쓰기로 깨지지 않게(부탁 날 할 일에 흔적·
    # 자국을 쓰지 않음, 돕는 사람 자신의 생각을 묻지 않음)
    new = {**d, "missionHook": hook}
    bad += [r.split(" ")[0] for r in way_problems(new) if " missionHook" in r]
    answers, numeric = mission_checks.answer_texts(draft)
    seen = [draft.question, d.get("discovery") or ""]  # 학생이 이미 보는 글과 겹침은 유출 아님
    bad += [
        f"LEAK {r}"
        for r in find_text_leaks(
            hook, answers, draft.forbidden_terms, draft.example_answer, overlap, seen
        )
    ]
    if numeric and any(mission_checks.has_number(hook, n) for n in numeric):
        bad.append("LEAK ANSWER_KEY")
    key = compact(theme.get("answer"))
    if key and key in compact(hook):
        bad.append("THEME_ANSWER_LEAK")
    if story_type(theme).hide_candidates and (
        candidate_names(theme, hook) or answer_fact_hits(theme, hook)
    ):
        bad.append("CANDIDATE_NAME")
    return bad


def full_speakers(theme: Theme, generated: dict, day: str | None = None) -> dict:
    """대화 화자를 줄여 쓴 등장인물 이름을 원래 이름으로 바꾼다(#535 닫기 3차).

    '캠핑장 관리인'을 '관리인'처럼 띄어 쓴 이름의 뒷부분만 쓰면 SPEAKER로 대화를 다시 만들었다
    (실측 2026-11-15 닫기 2차 글 20건 2번). 뒷부분이 등장인물 한 명에게만 맞고 찾는 대상이 아닐
    때만 바꾼다(그 밖은 그대로 두어 SPEAKER·TARGET_SPEAKS 검사가 본다). day를 주면 그날 돕는
    사람('떡집 사장님'→'사장님')도 같이 본다(#782 테마 짜임).
    """
    names = [c["name"] for c in theme.get("characters") or []]
    if day is not None and (helper := str(theme_day(theme, day).get("helper") or "").strip()):
        names.append(helper)

    def full(speaker: str | None) -> str | None:
        s = (speaker or "").strip()
        if not s or s == "뭉치" or s in names or is_target(theme, s):
            return speaker
        matches = [n for n in names if n.endswith(" " + s)]
        return matches[0] if len(matches) == 1 else speaker

    out = dict(generated)
    out["lines"] = [{**x, "speaker": full(x.get("speaker"))} for x in generated.get("lines") or []]
    return out


def dialogue_lines(generated: dict) -> list[dict[str, str]]:
    """대화 모델이 쓴 줄 그대로(#782 테마 짜임: 전에는 끝에 증거 발견 줄·수사 연결 문장을 붙였음).

    단서는 학생이 그날 미션을 마친 뒤 learning이 보여 주므로 대화에 넣지 않고, 그날·앞 요일 단서
    결과도 말하지 않는다(CLUE_EARLY·PREV_CLUE, 아직 못 얻은 단서를 흘리므로 사용자 결정 2026-11-11·
    2026-11-19).
    """
    return [{"speaker": x["speaker"], "text": x["text"]} for x in generated.get("lines") or []]


def is_target(theme: Theme, speaker: str | None) -> bool:
    """화자가 찾는 대상인지(이름 일부만 써도 같은 대상: '강아지 보리'와 '보리').

    뭉치·등장인물은 대상이 아니다. 대상 이름에 주인 이름이 들어가면('지우의 책갈피') 주인 '지우'를
    대상으로 잘못 보던 오탐을 막음(실측 repo-auto3-1, 2026-11-11: 대화가 TARGET_SPEAKS로 빠짐).
    """
    s, target = compact(speaker), compact(theme.get("target"))
    if s in {"뭉치"} | {compact(c.get("name")) for c in theme.get("characters") or []}:
        return False
    # 그날 돕는 사람도 대상이 아님(#782 테마 짜임, '보리 할머니'처럼 대상 이름이 들어가도)
    if s in {compact(d.get("helper")) for d in theme.get("days") or [] if d.get("helper")}:
        return False
    return len(s) >= 2 and bool(target) and (s in target or target in s)


def check_dialogue(
    theme: Theme, day: str, generated: dict, draft: Draft, grade: int, overlap: int
) -> list[str]:
    bad = []
    d = theme_day(theme, day)
    discovery, hook = d["discovery"], d["missionHook"]
    lines = dialogue_lines(generated)
    lo, hi = DIALOGUE_LINES[grade]
    if not lo <= len(lines) <= hi:
        bad.append(f"LINE_COUNT {len(lines)}줄(초{grade}는 {lo}~{hi}줄)")
    speakers = {"뭉치"} | {c["name"] for c in theme["characters"]}
    if helper := str(d.get("helper") or "").strip():  # 그날 돕는 사람(#782 테마 짜임)
        speakers.add(helper)
    if early := sorted({v for x in lines for v in early_values(d, x.get("text"))}):
        bad.append(f"CLUE_EARLY {day} 대화 줄이 그날 단서 결론(허용 값 {early})을 미리 말함")
    if prev := sorted({v for x in lines for v in prev_values(theme, day, x.get("text"))}):
        bad.append(f"PREV_CLUE {day} 대화 줄이 앞 요일 단서 결과(허용 값 {prev})를 말함")
    if any(SPEAKER_PREFIX.match(x["text"]) for x in lines):
        bad.append("SPEAKER_IN_TEXT 말 앞에 '이름:'이 붙음")
    if any(FOREIGN.search(x["text"]) for x in lines):
        bad.append("LANGUAGE 한국어 밖 글자(가나·한자)")
    if any(len(x["text"]) > LINE_MAX for x in lines):
        bad.append(f"LINE_LENGTH 한 줄 {LINE_MAX}자 초과")
    # #782 설계 v8: 대화가 글로 할 수 없는 활동을 시킴('그래프로 정리해 줘' — 글 검토 STANDARD_FIT)
    if acts := sorted({a for x in lines for a in act_orders(x["text"])}):
        bad.append(f"ACT_NAME 대화 줄이 글로 할 수 없는 활동을 시킴({'·'.join(acts)})")
    if any(x["speaker"] not in speakers for x in lines):
        bad.append(f"SPEAKER 화자는 {sorted(speakers)}만")
    # 마지막 줄은 뭉치가 오늘 문제로 잇는 말(#782 테마 짜임). 웹이 답변 화면 '오늘의 문제' 첫 줄에
    # "뭉치 · {마지막 줄}"로 한 번 더 보여 줌(#807 오늘 장면, 08 세션 2026-11-19)
    if lines and lines[-1]["speaker"] != "뭉치":
        bad.append("LAST_SPEAKER 마지막 줄은 뭉치가 오늘 문제로 잇는 말")
    if day == "MON" and day1_time(theme, " ".join(x["text"] for x in lines)):
        bad.append("DAY1_TIME 첫날 대화에 '어제'(시작 이야기의 사건 직후, 어제 한 일이 없음)")
    # #782 미션 방식: 부탁 날 보답 약속이 사건과 상관없으면(실측 '인사말 만들 때 살펴볼 점') 그날
    # 다시
    # #782 설계 v10: 예시 문장을 주면 한 주가 같은 약속이 되어(7차 같은 문장 53번) 뜻만 말하고,
    # 약속 감각이 그날 단서와 맞는지도 봄(promise_sense)
    if ask_promise_missing(d, lines):
        bad.append(
            f"ASK_PROMISE {day} 부탁 날 {d.get('helper')}이(가) 도와주면 그때 "
            f"{promise_meaning(theme, d)} 알려 주겠다는 약속이 없음(조건은 오늘 일로 자기 말로)"
        )
    elif why := ask_promise_mismatch(theme, d, lines):
        bad.append(
            f"ASK_PROMISE {day} 약속이 그날 단서와 어긋남({why}): 도와주면 그때 "
            f"{promise_meaning(theme, d)} 알려 주겠다는 뜻으로(언제·어디서 봤는지는 말하지 않음)"
        )
    if any(is_target(theme, x["speaker"]) for x in lines):
        bad.append("TARGET_SPEAKS 찾는 대상이 종료 이야기 전에 말함")
    # #782 설계 v10 5절: 첫 등장인물의 대화 줄도 아이가 이미 아는 것을 말하지 않음(그 요일 대화
    # 다시). 첫 줄(오늘 온 까닭)은 걸리면 코드 문장으로 붙음(first_line_problems)
    me = first_speaker(theme)
    mine = [x.get("text") for x in lines if x.get("speaker") == me]
    for code, word in dict.fromkeys(hit for t in mine for hit in child_known(theme, t, True)):
        bad.append(f"{code} {day} 대화에서 {me}의 말 '{word}' {child_known_why(theme, code)}")
    if any(
        len(x["speaker"]) >= 2
        and re.match(re.escape(x["speaker"]) + r"(는|은|가|이|도|의)", x["text"])
        for x in lines
    ):
        bad.append("SELF_NAME 말하는 사람이 자기 이름을 3인칭으로 부름")
    answers, numeric = mission_checks.answer_texts(draft)
    key = compact(theme["answer"])
    # #782 테마 짜임부터 대화 전체를 모델이 쓰므로 모든 줄을 본다
    for x in lines:
        text = x.get("text") or ""
        # 질문은 학생이 이미 보는 글이고 증거 발견 줄·수사 연결 문장은 대화가 풀어 쓰는 재료라 예시
        # 답과 겹쳐도 유출로 보지 않음
        for reason in find_text_leaks(
            text,
            answers,
            draft.forbidden_terms,
            draft.example_answer,
            overlap,
            [draft.question, discovery, hook],
        ):
            bad.append(f"LEAK {reason}")
        if numeric and any(mission_checks.has_number(text, n) for n in numeric):
            bad.append("LEAK ANSWER_KEY")
        if key and key in compact(text):
            bad.append(f"THEME_ANSWER_LEAK 대화에 테마 정답 낱말 '{theme['answer']}'")
    if story_type(theme).hide_candidates:  # #634: 후보는 엔딩 전 대화에 말하지도 나오지도 않음
        said = "\n".join(f"{x.get('speaker') or ''} {x.get('text') or ''}" for x in lines)
        if named := candidate_names(theme, said) + answer_fact_hits(theme, said):
            name = story_type(theme).facts.name  # type: ignore[union-attr]
            bad.append(f"CANDIDATE_NAME 대화 줄에 후보 {name} 이름 {named}")
    return list(dict.fromkeys(bad))


def check_review(generated: dict, ids: tuple[str, ...]) -> tuple[list[dict], list[dict], list[str]]:
    """(FAIL 항목, WARN 항목, 형식 문제). 판정은 항목으로 한다."""
    items = generated.get("items") or []
    got = [x.get("id") for x in items]
    shape = (
        []
        if sorted(got) == sorted(ids)
        else [f"REVIEW_SHAPE 항목은 {list(ids)} 한 번씩(지금 {got})"]
    )
    return (
        [x for x in items if x.get("verdict") == "FAIL"],
        [x for x in items if x.get("verdict") == "WARN"],
        shape,
    )


def public_theme(theme: Theme) -> dict:
    """응답 Theme에 넣는 칸만.

    후보 특징 표는 이름·후보별 값만(standardCode 빼고), 요일은 그날 단서가 쓰는 특징 이름
    clueFeature를 더함(#647). 증거 배정·단서 조건·증거·증거 발견 줄·수사 연결 문장·콘티는 내부 칸.
    """
    keep = (
        "title",
        "world",
        "characters",
        "styleNote",
        "outfit",
        "intro",
        "outro",
        "bigQuestion",
        "candidates",
        "answer",
    )
    day_keep = ("day", "thinkingType", "place", "sceneNote", "clue", "rulesOut")
    return {
        **{k: theme[k] for k in keep},
        "days": [
            {
                **{k: d[k] for k in day_keep},
                "clueFeature": (d.get("condition") or {}).get("feature") or None,
            }
            for d in theme["days"]
        ],
        "features": [
            {
                "name": f["name"],
                "values": [{"candidate": v["candidate"], "value": v["value"]} for v in f["values"]],
            }
            for f in theme.get("features") or []
        ]
        or None,
    }


# --- 그림·영상·움직임 (#437 그림 단계) ------------------------------------------------
IMAGE_REVIEW_IDS = ("MUNGCHI", "ANSWER_HINT", "TEXT", "SAFETY", "SCENE_FIT")
MISSION_IMAGE_REVIEW_IDS = (*IMAGE_REVIEW_IDS, "MISSION_FIT")
FLOW_IMAGE_REVIEW_IDS = (*IMAGE_REVIEW_IDS, "FLOW")  # 앞 컷을 잇는 컷 그림(#779 B안)


def image_review_ids(
    base: tuple[str, ...], person: bool, follow: bool, frame: bool = False
) -> tuple[str, ...]:
    """그림 검토 항목: 기본 + 인물 기준 그림이 있으면 PEOPLE + 앞 컷을 이으면 FLOW + 구도 틀의
    검토 핵심이 있으면 FRAME(#779)."""
    return (
        *base,
        *(["PEOPLE"] if person else []),
        *(["FLOW"] if follow else []),
        *(["FRAME"] if frame else []),
    )


VIDEO_REVIEW_IDS = ("MORPH", "ANSWER_HINT", "TEXT", "SAFETY", "CONTINUITY")

# 움직임 상한(기준안, ai.md 17.1 움직임 행)
ZOOM = (1.0, 1.4)
CAMERA_SECONDS = (8.0, 20.0)
TRANSITION_SECONDS = (0.3, 1.2)
EFFECT_LAYERS = 2
EFFECT_COUNT = (1, 20)
EFFECT_SIZE = (1.0, 6.0)
EFFECT_SPEED = (2.0, 20.0)
EFFECT_OPACITY = (0.2, 0.8)
SPEAKER_ZOOM = 1.2  # 화자 초점 확대(새로 정한 값, 생성 모델은 위치만 정함)
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def dialogue_speakers(theme: Theme, lines: list[dict] | None) -> list[str]:
    """움직임 speakers에 넣을 그 요일 대화 화자(나온 순서, 찾는 대상 제외)."""
    names = [x.get("speaker") or "" for x in lines or []]
    return [s for s in dict.fromkeys(names) if s.strip() and not is_target(theme, s)]


# 살펴보기(요일 장면 그림 속 누를 물건, 사용자 결정 2026-11-11). 개수·글자 수는 기준안
SPOTS = (2, 3)
SPOT_LABEL_MAX = 10
SPOT_LINE_MAX = 30
SPOT_MIN_GAP = 8.0  # 살펴보기 위치끼리 최소 거리(그림 %, 기준안). 손가락으로 따로 누를 수 있게


def spot_leaks(draft: Draft, text: str, overlap: int) -> bool:
    """살펴보기 글이 미션 답·금지어·예시 답을 말하는지(대화와 같은 검사, 점검 C20)."""
    answers, numeric = mission_checks.answer_texts(draft)
    if find_text_leaks(
        text, answers, draft.forbidden_terms, draft.example_answer, overlap, [draft.question]
    ):
        return True
    return bool(numeric and any(mission_checks.has_number(text, n) for n in numeric))


def spots(
    generated: list[dict],
    theme: Theme,
    day: str | None,
    draft: Draft | None = None,
    overlap: int = 12,
) -> tuple[list[dict], list[str]]:
    """생성 모델의 살펴보기 물건 → 응답 spots와 맞춘 사유(warnings MOTION).

    요일 장면만. 이름·한마디가 비거나 길면, 이름·한마디가 그날 단서 결론(허용 값)을 미리 말하거나
    이름·한마디에 후보·정답 이름이 있으면 그 물건을 뺀다(살펴보기는 미션 전이라 단서는 아직
    보여 주지 않음). 증거 물건은 정확히 1개(여럿이면 첫 번째만 증거), 남은 물건이 2개 미만이거나
    증거 물건이 없으면 그 장면 spots를 비운다. 다시 생성하지 않는다(움직임과 같은 처리).
    """
    if day is None:
        return [], (["MOTION_SPOT 시작·종료 장면은 살펴보기 없음"] if generated else [])
    notes: list[str] = []
    d = theme_day(theme, day)
    names = [compact(c) for c in theme.get("candidates") or []]
    kept: list[dict] = []
    for i, s in enumerate(generated):
        label, line = str(s.get("label") or "").strip(), str(s.get("line") or "").strip()
        why = None
        if not label or not line:
            why = "이름·한마디 비어 있음"
        elif len(label) > SPOT_LABEL_MAX or len(line) > SPOT_LINE_MAX:
            why = f"이름 {SPOT_LABEL_MAX}자·한마디 {SPOT_LINE_MAX}자 초과"
        # #782 오늘 장면 대비: 물건 이름(label)도 그림 위에 보여 함께 본다(사용자 결정 2026-11-19)
        elif early_values(d, f"{label} {line}"):
            why = "이름·한마디가 그날 단서 결론을 미리 말함(CLUE_EARLY)"
        elif any(n and n in compact(label + line) for n in names):
            why = "후보·정답 이름(ANSWER_LEAK)"
        elif draft is not None and spot_leaks(draft, label + " " + line, overlap):
            why = "미션 답·금지어(LEAK)"
        if why:
            notes.append(f"MOTION_SPOT spots{i} {why}이라 뺌")
            continue
        x, y = float(s.get("x", 50)), float(s.get("y", 50))
        fx, fy = min(max(x, 0.0), 100.0), min(max(y, 0.0), 100.0)
        if (fx, fy) != (x, y):
            notes.append(f"MOTION_RANGE spots{i} 좌표 ({x}, {y})→({fx}, {fy})")
        kept.append(
            {"x": fx, "y": fy, "label": label, "line": line, "evidence": bool(s.get("evidence"))}
        )
    # 가까운 위치(SPOT_MIN_GAP 안)는 하나만 남김. 증거를 먼저 남긴다
    # (실측: 휴대전화 한 물건의 부분을 겹쳐 고름)
    spaced: list[dict] = []
    for k in sorted(kept, key=lambda k: not k["evidence"]):
        if any(
            ((k["x"] - o["x"]) ** 2 + (k["y"] - o["y"]) ** 2) ** 0.5 < SPOT_MIN_GAP for o in spaced
        ):
            notes.append(f"MOTION_SPOT {k['label']} 다른 살펴보기와 너무 가까워 뺌")
            continue
        spaced.append(k)
    kept = [k for k in kept if any(k is o for o in spaced)]
    evidence = [k for k in kept if k["evidence"]]
    if not evidence:
        if kept:
            notes.append("MOTION_SPOT 증거 물건이 없어 살펴보기를 비움")
        return [], notes
    if len(evidence) > 1:
        notes.append("MOTION_SPOT 증거 물건이 여럿이라 첫 번째만 증거")
        for k in evidence[1:]:
            k["evidence"] = False
    if len(kept) > SPOTS[1]:
        notes.append(f"MOTION_SPOT {SPOTS[1]}개까지(나머지 뺌)")
        kept = [evidence[0]] + [k for k in kept if k is not evidence[0]][: SPOTS[1] - 1]
    if len(kept) < SPOTS[0]:
        return [], [*notes, f"MOTION_SPOT 물건이 {SPOTS[0]}개 미만이라 살펴보기를 비움"]
    return kept, notes


def motion(
    generated: dict,
    speakers: list[str],
    captions: list[dict],
    spot_list: list[dict] | None = None,
) -> tuple[dict, list[str]]:
    """생성 모델의 움직임 값 → ThemeMotion 모양과 맞춘 항목 사유(warnings MOTION).

    상한 밖 숫자는 상한으로 맞추고, 색이 #RRGGBB가 아니면 그 효과를 빼고, 화자가 아닌 이름은
    뺀다. 다시 생성하지 않는다(정해진 처리, ai.md 17.1).
    """
    notes: list[str] = []

    def fit(name: str, value: float, bounds: tuple[float, float]) -> float:
        lo, hi = bounds
        out = min(max(value, lo), hi)
        if out != value:
            notes.append(f"MOTION_RANGE {name} {value}→{out}")
        return out

    def point(name: str, p: dict, zoom: float | None = None) -> dict:
        if zoom is None:
            zoom = fit(f"{name}.zoom", float(p.get("zoom", 1)), ZOOM)
        return {
            "x": fit(f"{name}.x", float(p.get("x", 50)), (0.0, 100.0)),
            "y": fit(f"{name}.y", float(p.get("y", 50)), (0.0, 100.0)),
            "zoom": zoom,
        }

    out_speakers: dict[str, dict] = {}
    for s in generated.get("speakers") or []:
        name = s.get("name") or ""
        if name not in speakers:
            notes.append(f"MOTION_SPEAKER 대화 화자가 아닌 {name!r}를 뺌")
            continue
        out_speakers[name] = point(f"speakers.{name}", s, SPEAKER_ZOOM)
    effects = []
    for i, e in enumerate(generated.get("effects") or []):
        if i >= EFFECT_LAYERS:
            notes.append(f"MOTION_EFFECT 효과는 {EFFECT_LAYERS}층까지(나머지 뺌)")
            break
        if not HEX_COLOR.match(str(e.get("color") or "")):
            notes.append(f"MOTION_EFFECT effects{i}.color {e.get('color')!r}가 #RRGGBB가 아니라 뺌")
            continue
        direction = int(e.get("direction", 0))
        if not 0 <= direction <= 359:
            notes.append(f"MOTION_RANGE effects{i}.direction {direction}→{direction % 360}")
            direction %= 360
        effects.append(
            {
                "shape": e["shape"],
                "color": e["color"],
                "count": int(fit(f"effects{i}.count", int(e.get("count", 1)), EFFECT_COUNT)),
                "size": fit(f"effects{i}.size", float(e.get("size", 1)), EFFECT_SIZE),
                "direction": direction,
                "speed": fit(f"effects{i}.speed", float(e.get("speed", 2)), EFFECT_SPEED),
                "opacity": fit(f"effects{i}.opacity", float(e.get("opacity", 0.5)), EFFECT_OPACITY),
            }
        )
    result = {
        "version": 1,
        "transition": {
            "kind": generated["transition"],
            "seconds": fit(
                "transition.seconds", float(generated["transitionSeconds"]), TRANSITION_SECONDS
            ),
        },
        "camera": {
            "from": point("camera.from", generated["cameraFrom"]),
            "to": point("camera.to", generated["cameraTo"]),
            "seconds": fit("camera.seconds", float(generated["cameraSeconds"]), CAMERA_SECONDS),
        },
        "speakers": out_speakers,
        "effects": effects,
        "captions": [
            {"start": c["start"], "end": c["end"], "text": c["text"][:CAPTION_MAX]}
            for c in captions
        ],
        "spots": spot_list or [],
    }
    return result, notes
