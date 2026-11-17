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

import itertools
import json
import random
import re
from typing import Any

from app.followup.leak_guard import find_text_leaks
from app.mission_draft import checks as mission_checks
from app.mission_draft.models import Draft, MissionDraftRequest
from app.theme_draft.families import StoryType, is_animal, story_type

DAYS = ("MON", "TUE", "WED", "THU", "FRI")
DAY_KO = dict(zip(DAYS, ("월", "화", "수", "목", "금"), strict=True))
# 요일 배치 기준안(에픽 #436 확인 필요). learning이 다시 검사
DAY_TYPE = {"MON": "ANALYZE", "TUE": "EVALUATE", "WED": "CREATE", "THU": "SOLVE", "FRI": "REFLECT"}

# 학년별 기준안(#437 본문)
CANDIDATES = {3: 4, 4: 4, 5: 4, 6: 4}  # 모든 학년 4개(사용자 결정 2026-11-10)
HINTS = {3: 3, 4: 2, 5: 1, 6: 1}
DIALOGUE_LINES = {3: (3, 4), 4: (3, 4), 5: (2, 3), 6: (2, 3)}  # 끝 두 줄(증거 발견·수사 연결) 포함
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
# 단서가 그때(evidence.when의 시각)를 말하지 않으면 코드가 앞에 "오후 3시, "를 붙인다(#535 7차 글
# 검토 CLUE_LOGIC "흔적·기록이 오후 3시의 것인지 드러나지 않음". 검사로 고쳐 쓰게 하면 7차 줄거리
# 단서 172개 중 133개가 걸려 시간이 크게 늘어 코드가 붙임). 붙인 만큼 글자 수 상한도 늘림
CLUE_TIME = re.compile(
    r"(?:(오전|오후|아침|낮|저녁|밤|새벽)\s?)?(\d{1,2})\s?시(?:\s?(\d{1,2})\s?분|\s?(반))?"
)
LAST_ELIMINATION_MIN = DAYS.index("THU")  # 마지막 틀린 후보는 목요일 이후(수요일까지 2개 이상 남음)
# 글자 수 상한(기준안, 학년 공통). 단서는 한 줄 글로 보여 주고(learning이 그날 미션 완료 뒤)
# 증거 발견 줄은 대화 한 줄로 그대로 나가 LINE_MAX와 같음
TEXT_MAX = {
    "title": 20,
    "incident": 60,  # #634 ③ 내부 칸(기준안)
    "answerLook": 60,
    "bigQuestion": 40,
    "intro": 200,
    "outro": 300,
    "place": 20,
    "sceneNote": 150,
    "clue": LINE_MAX,
    "discovery": LINE_MAX,
    "missionHook": LINE_MAX,  # 대화 한 줄로 나감(증거 발견 줄 다음, 뭉치)
}
DAY_TEXTS = ("place", "sceneNote", "clue", "discovery", "missionHook")
CUTS = 4  # 시작·종료 영상 콘티 컷 수(4·6·8·6초, theme_video_cut_seconds, 사용자 결정 2026-11-11)
CAPTION_MAX = 30  # 컷 문구(움직임 captions로 웹이 띄움) 글자 상한(기준안)
MUNGCHI_MOODS = ("none", "smile", "surprised", "determined")
# 콘티 scene·action을 칸 하나만 고쳐 쓸 때 알려 주는 글자 상한(기준안, 길이 검사는 하지 않음)
CUT_TEXT_MAX = 80
# 뭉치는 팔이 없어(아래쪽 작은 손만) 손·팔다리를 쓰는 동작을 영상으로 만들면 팔·다리가 새로 생긴다.
# 실측 2026-11-11(auto4·auto5b·auto4d 뭉치 컷 12개 중 9개가 짚기·손 들기·건네기·가리키기·모으기,
# 그런 컷과 뛰는 컷에서 영상 검토 CONTINUITY·MORPH 실패). 낱말은 다른 뜻과 겹치지 않는 꼴만 둔다
# (손전등·놓인·모은 단서 같은 말은 걸리지 않게). '모으·모아·모은다'는 '다섯 흔적을 모아'·
# '단서를 모아 보자'처럼 손 동작이 아닌 말에 걸려 뺌(#535 7차: 종료 1컷 CUT_ACTION 5번, 초4
# auto4가 이 사유로 다시 생성하다 마감 실패). 손으로 모으는 말은 '손을·두 손'으로 잡힘
MUNGCHI_HAND_WORDS = tuple(
    (
        "손을|손으로|손가락|두 손|한 손|양손|손뼉|박수|만세|팔을|양팔|"
        "가리키며|가리키고|가리킨다|가리켜|짚는|짚고|짚어|짚으|건네|건넨|안아|안고|안는|껴안|"
        "놓는|놓고|놓아|내려놓|들어 올|들어올|집어|줍|쥐고|쥔다|뛰|점프|달리|달려|달린|"
        # #634 동물 주인공: 뭉치가 동물을 붙잡는 꼴(붙잡는 건 중립 인물)
        "잡아|잡고|잡는|붙잡"
    ).split("|")
)
# …이·…가로 끝나도 주어가 아닌 낱말(콘티 마디의 주어를 가를 때)
NOT_SUBJECT = tuple("같이 많이 높이 깊이 길이 가까이 바닷가 물가 강가 길가 냇가 창가".split())
# 화면 쪽으로 다가오거나 화면 밖으로 나가면 확대돼 몸이 잘리거나 인물이 사라진다(비교 시험
# 2026-11-11: "화면 쪽으로 다가온다" 컷에서 빠른 모델이 확대해 뭉치 발이 잘림)
APPROACH_WORDS = tuple("다가오|다가온|달려오|달려온|걸어오|걸어온|화면 밖|밖으로|들어간".split("|"))
# 시작 콘티 1 평소 모습·2 사건에는 뭉치가 없고 3 출동·4 현장 도착에는 나옴(사용자 결정 2026-11-11)
INTRO_MUNGCHI = (False, False, True, True)
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
REVIEW_IDS = ("CLUE_LOGIC", "ANSWER_HINT", "GRADE_VOCAB", "STANDARD_FIT", "SAFETY")
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


def early_values(day: dict, text: str | None) -> list[str]:
    """그날 condition 허용 값 중 text가 미리 말하는 값."""
    allowed = (day.get("condition") or {}).get("allowed") or []
    return [a for a in allowed if mentions_value(a, text)]


def theme_day(theme: Theme, day: str) -> dict:
    return next(d for d in theme["days"] if d["day"] == day)


# 칸 하나만 고쳐 쓰면 되는 줄거리 검사 사유(fix_theme). 이야기 틀·정답 논리·표에 닿지 않는 글 칸만
FIX_PATH = re.compile(
    r"^(?:title|bigQuestion|intro|outro|incident|answerLook"
    r"|(?:MON|TUE|WED|THU|FRI)\.(?:place|sceneNote|clue|discovery|missionHook)"
    r"|(?:introCuts|outroCuts)[1-4]\.caption)$"
)
# 콘티 scene·action은 뭉치 동작 검사(CUT_ACTION)일 때만 그 칸을 고쳐 쓴다(정답 유출은 다시 생성)
CUT_FIX_PATH = re.compile(r"^(?:introCuts|outroCuts)[1-4]\.(?:scene|action)$")
FIX_REASON = (
    re.compile(r"^LENGTH (\S+) \d+자 > \d+$"),
    re.compile(r"^CUT_ACTION ((?:introCuts|outroCuts)[1-4])\.(scene|action) "),
    re.compile(r"^CLUE_EARLY (MON|TUE|WED|THU|FRI) (discovery|sceneNote)에 "),
    re.compile(r"^ANSWER_LEAK (\S+?)에 "),
    re.compile(r"^CANDIDATE_NAME (\S+?)에 "),  # #634 엔딩 전 글의 후보 이름(사실표 종류)
    re.compile(r"^ANSWER_FACT (\S+?)에 "),  # #634 ② 엔딩 전 글의 정답만의 표 값
    re.compile(r"^CLUE_WORDING (MON|TUE|WED|THU|FRI) (clue) "),
    re.compile(r"^CLUE_OWNER (MON|TUE|WED|THU|FRI) (clue) "),
    # 단서 문장의 허용 값 낱말이 빠지거나 허용 밖 값이 들어가면 그 단서만 고쳐 씀(#535 7차: 흔적
    # 단서에 대상 낱말을 넣으며 값 낱말이 빠져 CLUE_TEXT 0.5 → 2.0, 줄거리 전체를 다시 만들며
    # 되풀이됨)
    re.compile(r"^CLUE_TEXT (MON|TUE|WED|THU|FRI) (clue) "),
    re.compile(r"^OUTRO_RECAP (outro) "),
    re.compile(r"^HIDE_SPOT (MON|TUE|WED|THU|FRI) (sceneNote|discovery|clue|missionHook) "),
    re.compile(r"^CLUE_PROOF (MON|TUE|WED|THU|FRI) (clue) "),
    re.compile(r"^TIME_WORD (\S+?)에 "),  # #634 ④ 시간 탐정 엔딩 전 글의 시각
    # #634 ③: 사건(incident)·정답 동물 모습(answerLook)이 비면 그 칸만 써 넣음(판정 실측 3건이
    # 이 사유로 줄거리를 다시 만듦)
    re.compile(r"^REQUIRED (incident|answerLook)$"),
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
    if kind is None or not kind.no_trace:
        return plan
    return {
        day: ({"kind": "SIGHTING", "medium": None} if slot.get("kind") == "TRACE" else dict(slot))
        for day, slot in plan.items()
    }


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


def kind_fits(kind: StoryType, feature: str | None, evidence: str | None) -> bool:
    """그날 특징을 그 증거 종류로 알 수 있는지. 사실표 특징은 표의 kinds, 그 밖은 흔적만 본다
    (TRACE면 traceable, 목격·기록은 어떤 특징이든 됨 — #535부터의 규칙 그대로)."""
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
    """탈것 찾기의 온 사람('삼촌이 타고 온 탈것' → '삼촌', 공백 뺀 꼴). 다른 종류·형식 밖은 None."""
    if story_type(theme).code != "VEHICLE":
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


def time_word_problems(theme: Theme) -> list[str]:
    """시각을 붙이지 않는 종류의 엔딩 전 글·단서에 시각(TIME_WORD, 칸 고쳐 쓰기)."""
    if story_type(theme).clue_time:
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


def answer_fact_hits(theme: Theme, text: str | None) -> list[str]:
    return [v for v in answer_facts(theme) if compact(v) in compact(text)]


# 보물 쪽지(#634 ①): 숨긴 곳은 끝까지 모르는 답인데 엔딩 전 글이 '숨긴 자리에서 흔적을 찾았다'처럼
# 이미 아는 듯이 써서 글 검토 CLUE_LOGIC(1차 판정 2회 8번 중 7번이 보물 쪽지)
HIDE_SPOT = re.compile(r"숨(?:긴|겨 ?둔|겨 ?놓은) ?(?:자리|곳|장소|위치)")


# 산 가게 단서는 그 가게에서 '샀다'는 근거가 있어야 함(#634 ② 작은 실측 1~3차: "가게에 간·나온
# 모습만으로는 거기서 샀다는 근거가 없음"이 되풀이, 프롬프트로 좁혀도 남아 코드 검사로)
BUY_WORDS = re.compile(r"샀|사는|사 가|사 오|사러|사서|계산|영수증|스티커|구입|주문")
PROOF_FEATURES = ("산 가게",)


def clue_proof_problems(theme: Theme) -> list[str]:
    """산 가게 단서에 산 근거 말이 없으면(CLUE_PROOF, 칸 고쳐 쓰기)."""
    if story_type(theme).facts is None:
        return []
    bad = []
    for d in theme.get("days") or []:
        cond = d.get("condition") or {}
        if cond.get("feature") in PROOF_FEATURES and not BUY_WORDS.search(str(d.get("clue") or "")):
            bad.append(
                f"CLUE_PROOF {d['day']} clue 산 가게 단서에 그 가게에서 산 근거(샀다·계산·영수증·"
                "스티커)가 없음(가게에 간·나온 모습만으로는 근거가 안 됨)"
            )
    return bad


def hide_spot_problems(theme: Theme) -> list[str]:
    """보물 쪽지 엔딩 전 글에 '숨긴 자리·숨긴 곳'(HIDE_SPOT, 칸 고쳐 쓰기)."""
    bad = []
    for d in theme.get("days") or []:
        for k in ("sceneNote", "discovery", "clue", "missionHook"):
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


def candidate_name_fields(theme: Theme) -> list[tuple[str, str]]:
    """동물 주인공 가족에서 엔딩 전에 보이는 글 칸 [(경로, 글)](종료 이야기·종료 콘티·단서 빼고).

    단서는 학생이 그날 미션을 마친 뒤 보고 후보 목록과 함께 나오므로 뺀다(설계 17.8.5).
    """
    fields = [
        (k, intro_story(theme) if k == "intro" else str(theme.get(k) or ""))
        for k in ("title", "world", "intro", "bigQuestion", "styleNote", "outfit", "incident")
    ]
    fields += [
        (f"{d['day']}.{k}", str(d.get(k) or ""))
        for d in theme.get("days") or []
        for k in ("place", "sceneNote", "discovery", "missionHook")
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


def day_text_max(day: dict, key: str, with_time: bool = True) -> int:
    """요일 글 칸 상한. 흔적 날 단서는 대상 낱말을 넣으므로 TRACE_CLUE_MAX(기준안).

    단서 앞에 그때 시각("오후 3시, ")이 있으면 그만큼 더(코드가 붙이는 몫, add_clue_time).
    """
    base = TEXT_MAX[key]
    if key == "clue" and (day.get("evidence") or {}).get("kind") == "TRACE":
        base = TRACE_CLUE_MAX
    # 시각을 붙이지 않는 종류(#634 시간 탐정)는 시각 몫을 더하지 않음(단서에 시각이 있으면
    # TIME_WORD가
    # 따로 걸림)
    if (
        key == "clue"
        and with_time
        and (t := clue_time(day))
        and _has_time(t, str(day.get("clue") or ""))
    ):
        base += len(t) + 2
    return base


def clue_time(day: dict) -> str | None:
    """그날 증거가 생긴 때(evidence.when)의 시각 글('오후 3시'·'10시 반'). 시각이 없으면 None."""
    m = CLUE_TIME.search(str((day.get("evidence") or {}).get("when") or ""))
    if not m:
        return None
    part, hour, minute, half = m.groups()
    text = f"{part + ' ' if part else ''}{hour}시"
    return text + (f" {minute}분" if minute else " 반" if half else "")


def _has_time(time_text: str, clue: str) -> bool:
    """단서가 그 시각(숫자+시)을 이미 말하는지."""
    hour = CLUE_TIME.search(time_text).group(2)  # type: ignore[union-attr]
    return re.search(rf"(?<!\d){hour}\s?시", clue) is not None


def add_clue_time(theme: Theme) -> Theme:
    """단서가 그때를 말하지 않으면 앞에 시각을 붙인다.

    그 시각 숫자나 '그때'가 이미 있으면 그대로 둔다. 시간 탐정(#634 ④)은 그때가 곧 정답이라 붙이지
    않는다(families.clue_time).
    """
    if not story_type(theme).clue_time:
        return theme
    for d in theme.get("days") or []:
        t, clue = clue_time(d), str(d.get("clue") or "").strip()
        if not t or not clue or "그때" in clue:
            continue
        if _has_time(t, clue):
            continue
        d["clue"] = f"{t}, {clue}"
    return theme


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


def finalize_texts(theme: Theme) -> Theme:
    """코드가 맞추는 글: 단서 앞 그때 시각, 시작 이야기 끝 규칙 문장, 종료 이야기 앞 다섯 단서 정리.

    줄거리·칸 고쳐 쓰기 뒤마다 부른다.
    """
    return compose_outro(compose_intro(add_clue_time(theme)))


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
        cut_fix = reason.startswith("CUT_ACTION ") and CUT_FIX_PATH.match(path or "")
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
        return CAPTION_MAX
    if key in ("scene", "action"):
        return CUT_TEXT_MAX
    if path == "outro" and theme is not None and "outroStory" in theme:
        return OUTRO_STORY_MAX
    head = path.partition(".")[0]
    if theme is not None and key == "clue" and head in DAYS:
        return day_text_max(theme_day(theme, head), key, story_type(theme).clue_time)
    return TEXT_MAX[key]


def mungchi_clauses(text: str) -> list[str]:
    """콘티 문장에서 뭉치가 주어인 마디. 뭉치가 나오는 컷에만 쓴다.

    '…고 '·'…며 '·'…가운데 '·'…동안 '·쉼표로 마디를 나눈다. '뭉치와 민지가'·'모두'처럼 함께 하는
    주어도 뭉치 마디이고 '뭉치를'·'뭉치 곁에서'는 아니다. 다른 사람이 주어(…이·…가, 마디 첫 낱말
    …는·…들은)인 마디는 빼고, 주어가 없는 마디는 앞 마디의 주어를 잇는다(첫 마디는 뭉치).
    """
    out: list[str] = []
    mungchi = True
    for part in re.split(r"(?<=[고며]) |(?<=가운데) |(?<=동안) |[,.] ", text):
        if re.search(r"뭉치(?:가|는|도|와|과|랑|하고)(?:\s|$)", part) or re.match(
            r"(?:모두|다 ?같이|다 ?함께|함께)", part
        ):
            mungchi = True
        elif re.match(r"\S+(?:는|들은|도)\s", part) or any(
            not w.endswith(NOT_SUBJECT)
            for w in re.findall(r"(?:^|(?<=\s))(\S+(?:이|가))(?=\s)", part)
        ):
            mungchi = False
        if mungchi:
            out.append(part)
    return out


def cut_action_problems(text: str, has_mungchi: bool = True) -> list[str]:
    """뭉치가 손·팔다리를 쓰는 동작(뭉치가 나오는 컷만), 화면 쪽으로 다가오거나 나가는 동작."""
    clauses = mungchi_clauses(text) if has_mungchi else []
    hands = [w for w in MUNGCHI_HAND_WORDS if any(w in c for c in clauses)]
    near = [w for w in APPROACH_WORDS if w in text]
    out = []
    if hands:
        out.append(f"뭉치가 손·팔다리를 쓰는 동작({', '.join(hands)}), 손짓은 사람만")
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
    for i, d in enumerate(days):
        day, cond = d["day"], d.get("condition") or {}
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
        clue = compact(d.get("clue"))
        missing = [a for a in sorted(allowed) if not value_in_text(a, d.get("clue"))]
        outside = [
            v
            for v in sorted(set(vals.values()) - allowed)
            if compact(v) in clue and not any(compact(v) in compact(a) for a in allowed)
        ]
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
                    f"LOGIC {day} 월~수 힌트가 남은 후보 중 {live}만 가리킴(2개 이상이어야 함)"
                )
        else:
            bad.append(f"CONDITION {day} kind는 RULE이나 HINT")
        remaining = [c for c in remaining if not (cond.get("kind") == "RULE" and c not in fit)]
    wrong = [c for c in cands if c != answer]
    never = [c for c in wrong if c not in first_out]
    if never:
        bad.append(f"LOGIC 어떤 RULE 단서로도 빠지지 않는 틀린 후보 {never}")
    elif wrong and max(first_out[c] for c in wrong) < LAST_ELIMINATION_MIN:
        last = DAYS[max(first_out[c] for c in wrong)]
        bad.append(f"LOGIC 마지막 틀린 후보가 {last}에 빠짐(목요일 이후여야 함)")
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
    if any(table.get((d.get("condition") or {}).get("feature")) is None for d in days):
        return []
    base = [dict(d) for d in days]
    first: list[int] = []
    for i, d in enumerate(base):
        cond = d.get("condition") or {}
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
    for d in fill_rules_out(theme).get("days") or []:
        out = [c for c in d.get("rulesOut") or [] if c in remaining]
        remaining = [c for c in remaining if c not in out]
        if out:
            outs.append((DAY_KO[d["day"]], out))
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


def check_cuts(theme: Theme) -> list[str]:
    """시작·종료 영상 콘티: 정확히 4컷, 칸 비지 않음, 문구 길이, 뭉치 표정.

    시작 콘티 1·2(평소 모습·사건)는 뭉치가 나오지 않아 mungchiMood가 none이고, 3·4(출동·현장
    도착)는 뭉치가 나와 none이 아니다.
    """
    bad = []
    for key in ("introCuts", "outroCuts"):
        cuts = theme.get(key) or []
        if len(cuts) != CUTS:
            bad.append(f"CUTS {key} {CUTS}컷 필요(지금 {len(cuts)}컷)")
        for i, cut in enumerate(cuts, 1):
            for k in ("scene", "action", "caption"):
                if not str(cut.get(k) or "").strip():
                    bad.append(f"REQUIRED {key}{i}.{k}")
            if len(cut.get("caption") or "") > CAPTION_MAX:
                bad.append(
                    f"LENGTH {key}{i}.caption {len(cut.get('caption') or '')}자 > {CAPTION_MAX}"
                )
            has_mungchi = key == "outroCuts" or (i <= len(INTRO_MUNGCHI) and INTRO_MUNGCHI[i - 1])
            for k in ("scene", "action"):
                for problem in cut_action_problems(str(cut.get(k) or ""), has_mungchi):
                    bad.append(f"CUT_ACTION {key}{i}.{k} {problem}")
            mood = cut.get("mungchiMood")
            if mood not in MUNGCHI_MOODS:
                bad.append(f"CUT_MOOD {key}{i} mungchiMood는 {list(MUNGCHI_MOODS)} 중 하나")
            elif key == "outroCuts" and mood == "none":
                bad.append(f"CUT_MOOD {key}{i} 종료 콘티는 모두 뭉치가 나와 none이 아님")
            elif key == "introCuts" and i <= len(INTRO_MUNGCHI):
                if INTRO_MUNGCHI[i - 1] and mood == "none":
                    bad.append(f"CUT_MOOD {key}{i} 뭉치가 나오는 컷이라 none이 아님")
                elif not INTRO_MUNGCHI[i - 1] and mood != "none":
                    bad.append(f"CUT_MOOD {key}{i} 뭉치가 나오지 않는 컷이라 none")
    return bad


def check_theme(theme: Theme, grade: int, standard_codes: set[str] | None = None) -> list[str]:
    """check_theme 노드의 코드 검사. 빈 목록이면 통과."""
    bad = []
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
    animal = is_animal(theme)
    if (
        animal
    ):  # 동물 주인공 가족(#634 ③)의 내부 칸: 사건 물건·일(미션 소재), 정답 동물 모습(종료 그림)
        bad += [
            f"REQUIRED {k}"
            for k in ("incident", "answerLook")
            if not str(theme.get(k) or "").strip()
        ]
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
            if hits := answer_fact_hits(theme, text):
                bad.append(f"ANSWER_FACT {path}에 정답만의 {table.name} 값 {hits}(엔딩 전 글)")
    days = theme.get("days") or []
    if tuple(d.get("day") for d in days) != DAYS:
        return bad + [f"DAYS 요일은 {list(DAYS)} 순서(지금 {[d.get('day') for d in days]})"]
    with_time = story_type(theme).clue_time  # 단서 앞 시각 몫(#634 시간 탐정은 없음)
    for d in days:
        if d.get("thinkingType") != DAY_TYPE[d["day"]]:
            bad.append(f"DAYS {d['day']} 유형은 {DAY_TYPE[d['day']]}")
        for k in DAY_TEXTS:
            v = d.get(k) or ""
            if not v.strip():
                bad.append(f"REQUIRED {d['day']}.{k}")
            elif len(v) > day_text_max(d, k, with_time):
                bad.append(f"LENGTH {d['day']}.{k} {len(v)}자 > {day_text_max(d, k, with_time)}")
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
        for problem in clue_wording_problems(d):
            bad.append(f"CLUE_WORDING {d['day']} clue {problem}")
        # 흔적 단서는 누구의 흔적인지 밝힌다(#535 6차: "흔적이 대상의 것인지 드러나지 않음").
        # 칸 고쳐 쓰기 대상
        trace = (d.get("evidence") or {}).get("kind") == "TRACE"
        if trace and target_words(theme) and not names_target(theme, d.get("clue")):
            bad.append(
                f"CLUE_OWNER {d['day']} clue 흔적 단서에 찾는 대상 낱말"
                f"({'·'.join(target_words(theme))})이 "
                "없음(누구의 흔적인지 밝힘)"
            )
        # #634 ④ 탈것 찾기: 모든 단서는 온 사람이 탄 탈것의 증거임을 밝힘(작은 실측: '따르릉 소리가
        # 났다'만 써서 글 검토 CLUE_LOGIC "그 소리가 할머니의 탈것에서 났다는 연결이 없음")
        person = clue_person(theme)
        if person and person not in compact(d.get("clue")):
            bad.append(
                f"CLUE_OWNER {d['day']} clue 단서에 온 사람('{person}')이 없음(그 사람이 탄 "
                "탈것의 증거임을 밝힘)"
            )
        if early := early_values(d, d.get("discovery")):
            bad.append(f"CLUE_EARLY {d['day']} discovery에 그날 단서 결론(허용 값 {early})")
        # 장면 메모가 증거가 남은 자리의 특징 값을 말하면 대화·그림이 문제 전에 단서를 알려 줌
        # (실측 2026-11-15·16 글 검토 ANSWER_HINT: '흙길의 발자국'). 칸 고쳐 쓰기로 고침(#535)
        if early := early_values(d, d.get("sceneNote")):
            bad.append(f"CLUE_EARLY {d['day']} sceneNote에 그날 단서 결론(허용 값 {early})")
        for k in ("discovery", "missionHook"):
            named = [c for c in cands if c != answer and compact(c) in compact(d.get(k))]
            if named:
                bad.append(f"ANSWER_LEAK {d['day']}.{k}에 후보 이름 {named}")
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

    수사 연결 문장은 질문이 아니라 문제 앞 대화 마지막 줄로 나간다(질문에 넣으면 증거 내용을 살피게
    돼 자료 부족·길이 초과로 막혔음, 실측 repo-beach5-3·museum6-3, 사용자 결정 2026-11-11)."""
    bad = [
        f"{f.check} {f.reason}" for f in mission_checks.check(draft, request, question_max, overlap)
    ]
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
    if story_type(theme).hide_candidates and (
        named := candidate_names(theme, joined) + answer_fact_hits(theme, joined)
    ):
        name = story_type(theme).facts.name  # type: ignore[union-attr]
        bad.append(
            f"CANDIDATE_NAME 문제·안내·생각 열기 질문·예시 답에 후보 {name} 이름·정답 값 {named}"
        )
    if any("수" in st.code for st in request.standards):  # 수학 미션만(성취기준 코드 4수·6수)
        final = draft.answer_key.final_answer if draft.answer_key else None
        if ahead := math_ahead([*texts, final or ""], grade):
            bad.append(
                f"GRADE_MATH 초{grade}에서 아직 배우지 않은 수학 개념({'·'.join(ahead)}). "
                "그 학년이 배운 수·연산으로 문제·예시 답·확인 방법을 씀"
            )
    return bad


def hook_problems(theme: Theme, day: str, hook: str, draft: Draft, overlap: int) -> list[str]:
    """미션 뒤 고쳐 쓴 수사 연결 문장이 그날 문제의 답·예시 답·단서 결론을 미리 말하는지(#535 닫기).

    수사 연결 문장은 줄거리 검사만 거치고 대화 유출 검사(끝 두 줄 제외)에서 빠지는데, 미션을 본
    뒤 고쳐 쓰면 문제의 답을 담을 수 있다(실측 2026-11-15 닫기 3차: 고를 자료 '기억 메모'를 미리
    지정해 글 검토 ANSWER_HINT). 걸리면 고쳐 쓰기를 버리고 원래 문장을 둔다.
    """
    d = theme_day(theme, day)
    bad = []
    if early := early_values(d, hook):
        bad.append(f"CLUE_EARLY 그날 단서 결론(허용 값 {early})")
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


def full_speakers(theme: Theme, generated: dict) -> dict:
    """대화 화자를 줄여 쓴 등장인물 이름을 원래 이름으로 바꾼다(#535 닫기 3차).

    '캠핑장 관리인'을 '관리인'처럼 띄어 쓴 이름의 뒷부분만 쓰면 SPEAKER로 대화를 다시 만들었다
    (실측 2026-11-15 닫기 2차 글 20건 2번). 뒷부분이 등장인물 한 명에게만 맞고 찾는 대상이 아닐
    때만 바꾼다(그 밖은 그대로 두어 SPEAKER·TARGET_SPEAKS 검사가 본다).
    """
    names = [c["name"] for c in theme.get("characters") or []]

    def full(speaker: str | None) -> str | None:
        s = (speaker or "").strip()
        if not s or s == "뭉치" or s in names or is_target(theme, s):
            return speaker
        matches = [n for n in names if n.endswith(" " + s)]
        return matches[0] if len(matches) == 1 else speaker

    out = dict(generated)
    out["lines"] = [{**x, "speaker": full(x.get("speaker"))} for x in generated.get("lines") or []]
    if generated.get("discoverySpeaker"):
        out["discoverySpeaker"] = full(generated["discoverySpeaker"])
    return out


def discovery_speaker(generated: dict) -> str:
    """증거 발견 줄 화자. 비어 있으면 뭉치(기본)."""
    return (generated.get("discoverySpeaker") or "").strip() or "뭉치"


def dialogue_lines(generated: dict, discovery: str, hook: str) -> list[dict[str, str]]:
    """LLM 줄 + 그날 증거 발견 줄(discoverySpeaker, 기본 뭉치) + 수사 연결 문장(뭉치).

    단서는 학생이 그날 미션을 마친 뒤 learning이 보여 주므로 대화에 넣지 않고, 앞 요일 단서
    요약 줄도 두지 않는다(아직 못 얻은 단서를 흘리므로, 사용자 결정 2026-11-11). 수사 연결 문장은
    문제 바로 앞에서 왜 오늘 이것을 배우는지 잇는다.
    """
    return [{"speaker": x["speaker"], "text": x["text"]} for x in generated.get("lines") or []] + [
        {"speaker": discovery_speaker(generated), "text": discovery},
        {"speaker": "뭉치", "text": hook},
    ]


def is_target(theme: Theme, speaker: str | None) -> bool:
    """화자가 찾는 대상인지(이름 일부만 써도 같은 대상: '강아지 보리'와 '보리').

    뭉치·등장인물은 대상이 아니다. 대상 이름에 주인 이름이 들어가면('지우의 책갈피') 주인 '지우'를
    대상으로 잘못 보던 오탐을 막음(실측 repo-auto3-1, 2026-11-11: 대화가 TARGET_SPEAKS로 빠짐).
    """
    s, target = compact(speaker), compact(theme.get("target"))
    if s in {"뭉치"} | {compact(c.get("name")) for c in theme.get("characters") or []}:
        return False
    return len(s) >= 2 and bool(target) and (s in target or target in s)


def check_dialogue(
    theme: Theme, day: str, generated: dict, draft: Draft, grade: int, overlap: int
) -> list[str]:
    bad = []
    d = theme_day(theme, day)
    discovery, hook = d["discovery"], d["missionHook"]
    lines = dialogue_lines(generated, discovery, hook)
    llm_lines = generated.get("lines") or []
    lo, hi = DIALOGUE_LINES[grade]
    if not lo <= len(lines) <= hi:
        bad.append(f"LINE_COUNT {len(lines)}줄(초{grade}는 끝 두 줄 포함 {lo}~{hi}줄)")
    speakers = {"뭉치"} | {c["name"] for c in theme["characters"]}
    if discovery_speaker(generated) not in speakers:
        bad.append(f"DISCOVERY_SPEAKER 증거 발견 줄 화자는 {sorted(speakers)} 중 하나")
    if any(overlaps(x.get("text"), t, overlap) for x in llm_lines for t in (discovery, hook)):
        bad.append("DISCOVERY_REPEATED LLM 줄이 증거 발견 줄·수사 연결 문장을 미리 말함")
    if early := sorted({v for x in llm_lines for v in early_values(d, x.get("text"))}):
        bad.append(f"CLUE_EARLY {day} 대화 줄이 그날 단서 결론(허용 값 {early})을 미리 말함")
    if any(SPEAKER_PREFIX.match(x["text"]) for x in lines):
        bad.append("SPEAKER_IN_TEXT 말 앞에 '이름:'이 붙음")
    if any(FOREIGN.search(x["text"]) for x in lines):
        bad.append("LANGUAGE 한국어 밖 글자(가나·한자)")
    if any(len(x["text"]) > LINE_MAX for x in lines):
        bad.append(f"LINE_LENGTH 한 줄 {LINE_MAX}자 초과")
    if any(x["speaker"] not in speakers for x in lines):
        bad.append(f"SPEAKER 화자는 {sorted(speakers)}만")
    if any(is_target(theme, x["speaker"]) for x in lines):
        bad.append("TARGET_SPEAKS 찾는 대상이 종료 이야기 전에 말함")
    if any(
        len(x["speaker"]) >= 2
        and re.match(re.escape(x["speaker"]) + r"(는|은|가|이|도|의)", x["text"])
        for x in lines
    ):
        bad.append("SELF_NAME 말하는 사람이 자기 이름을 3인칭으로 부름")
    answers, numeric = mission_checks.answer_texts(draft)
    key = compact(theme["answer"])
    # 유출 검사는 LLM이 만든 줄만. 끝 두 줄은 줄거리 검사가 이미 봤고 대화를 다시 만들어도 바뀌지
    # 않음(점검 C10: 미션 금지어가 그 줄 낱말과 겹치면 모든 시도가 같은 이유로 실패)
    for x in llm_lines:
        text = x.get("text") or ""
        # 질문과 끝 두 줄은 학생이 이미 보는 글이라 예시 답과 겹쳐도 유출로 보지 않음
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
        said = "\n".join(f"{x.get('speaker') or ''} {x.get('text') or ''}" for x in llm_lines)
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

    요일 장면만. 이름·한마디가 비거나 길면, 한마디가 그날 단서 결론(허용 값)을 미리 말하거나
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
        elif early_values(d, line):
            why = "한마디가 그날 단서 결론을 미리 말함(CLUE_EARLY)"
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
