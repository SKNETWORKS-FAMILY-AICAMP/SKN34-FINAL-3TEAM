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

import json
import re
from typing import Any

from app.followup.leak_guard import find_text_leaks
from app.mission_draft import checks as mission_checks
from app.mission_draft.models import Draft, MissionDraftRequest

DAYS = ("MON", "TUE", "WED", "THU", "FRI")
DAY_KO = dict(zip(DAYS, ("월", "화", "수", "목", "금"), strict=True))
# 요일 배치 기준안(에픽 #436 확인 필요). learning이 다시 검사
DAY_TYPE = {"MON": "ANALYZE", "TUE": "EVALUATE", "WED": "CREATE", "THU": "SOLVE", "FRI": "REFLECT"}

# 학년별 기준안(#437 본문)
CANDIDATES = {3: 4, 4: 4, 5: 4, 6: 4}  # 모든 학년 4개(사용자 결정 2026-11-10)
HINTS = {3: 3, 4: 2, 5: 1, 6: 1}
DIALOGUE_LINES = {3: (3, 4), 4: (3, 4), 5: (2, 3), 6: (2, 3)}  # 끝 두 줄(증거 발견·수사 연결) 포함
LINE_MAX = 40
LAST_ELIMINATION_MIN = DAYS.index("THU")  # 마지막 틀린 후보는 목요일 이후(수요일까지 2개 이상 남음)
# 글자 수 상한(기준안, 학년 공통). 단서는 한 줄 글로 보여 주고(learning이 그날 미션 완료 뒤)
# 증거 발견 줄은 대화 한 줄로 그대로 나가 LINE_MAX와 같음
TEXT_MAX = {
    "title": 20,
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
# (손전등·놓인·모은 단서 같은 말은 걸리지 않게)
MUNGCHI_HAND_WORDS = tuple(
    (
        "손을|손으로|손가락|두 손|한 손|양손|손뼉|박수|만세|팔을|양팔|"
        "가리키며|가리키고|가리킨다|가리켜|짚는|짚고|짚어|짚으|건네|건넨|안아|안고|안는|껴안|모으|모아|모은다|"
        "놓는|놓고|놓아|내려놓|들어 올|들어올|집어|줍|쥐고|쥔다|뛰|점프|달리|달려|달린"
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
MISSION_REVIEW_IDS = ("EXAMPLE_COMPLETE", "STANDARD_FIT", "MATERIAL")

COLOR = re.compile(
    r"빨간|빨강|파란|파랑|노란|노랑|초록|하얀|하양|흰|검은|검정|까만|분홍|주황|보라|갈색|회색|푸른|붉은"
)
FOREIGN = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")  # 가나·한자(일본어로 샌 사례)
UNSAFE = re.compile(r"살인|납치|유괴|폭력|담배|흉기|피투성이|자살")  # 나머지는 검토 모델
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
    r"^(?:title|bigQuestion|intro|outro"
    r"|(?:MON|TUE|WED|THU|FRI)\.(?:place|sceneNote|clue|discovery|missionHook)"
    r"|(?:introCuts|outroCuts)[1-4]\.caption)$"
)
# 콘티 scene·action은 뭉치 동작 검사(CUT_ACTION)일 때만 그 칸을 고쳐 쓴다(정답 유출은 다시 생성)
CUT_FIX_PATH = re.compile(r"^(?:introCuts|outroCuts)[1-4]\.(?:scene|action)$")
FIX_REASON = (
    re.compile(r"^LENGTH (\S+) \d+자 > \d+$"),
    re.compile(r"^CUT_ACTION ((?:introCuts|outroCuts)[1-4])\.(scene|action) "),
    re.compile(r"^CLUE_EARLY (MON|TUE|WED|THU|FRI) (discovery)에 "),
    re.compile(r"^ANSWER_LEAK (\S+?)에 "),
    re.compile(r"^CLUE_WORDING (MON|TUE|WED|THU|FRI) (clue) "),
    # 증거 종류(evidence.kind)는 그대로 두고 단서 문장만 그 종류에 맞게 고쳐 씀(실측 2026-11-11:
    # 단서 글자 수 초과와 섞이면 줄거리 전체를 다시 만들어 상한까지 실패, 글 20건 1건·전체 실측 1건)
    re.compile(r"^CLUE_EVIDENCE (MON|TUE|WED|THU|FRI) (clue) "),
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
    return out


# 단서 문장이 기록(사진·영상·녹음 등)을 말하면 증거 종류는 RECORD, RECORD면 기록 낱말이 있어야 함
# (실측 2026-11-11: 사진을 근거로 한 단서에 evidence가 SIGHTING이라 글 검토 CLUE_LOGIC으로 실패)
RECORD_WORDS = ("사진", "영상", "녹음", "기록", "일지", "메모", "녹화", "동영상", "cctv", "CCTV")


def clue_evidence_mismatch(day: dict) -> bool:
    clue = day.get("clue") or ""
    kind = (day.get("evidence") or {}).get("kind")
    has_record = any(w in clue for w in RECORD_WORDS)
    return (has_record and kind != "RECORD") or (kind == "RECORD" and not has_record)


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


def text_max(path: str) -> int:
    key = path.rpartition(".")[2]
    if key == "caption":
        return CAPTION_MAX
    return CUT_TEXT_MAX if key in ("scene", "action") else TEXT_MAX[key]


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
            not w.endswith(NOT_SUBJECT) for w in re.findall(r"(?:^|\s)(\S+(?:이|가))\s", part)
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
                f"CLUE_TEXT {day} 단서 문장에 허용 값 {missing} 낱말이 없음(허용 값 "
                f"{sorted(allowed)}을 그대로 씀)"
            )
        if outside:
            bad.append(f"CLUE_TEXT {day} 단서 문장에 허용 밖 값 {outside} 낱말이 있음")
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
    chars = theme.get("characters") or []
    if not CHARACTERS[0] <= len(chars) <= CHARACTERS[1] or any(
        not (c.get("name") or "").strip() or not (c.get("look") or "").strip() for c in chars
    ):
        bad.append(f"CHARACTERS 등장인물 {CHARACTERS[0]}~{CHARACTERS[1]}명(이름·모습)")
    if any("뭉치" in (c.get("name") or "") for c in chars):
        bad.append("CHARACTERS 주인공 뭉치는 등장인물에 넣지 않음(뭉치 모습은 고정)")
    for k in ("title", "bigQuestion", "intro", "outro"):
        if len(theme.get(k) or "") > TEXT_MAX[k]:
            bad.append(f"LENGTH {k} {len(theme.get(k) or '')}자 > {TEXT_MAX[k]}")
    cands, answer = theme.get("candidates") or [], theme.get("answer") or ""
    if len(cands) != CANDIDATES[grade] or len(set(cands)) != len(cands):
        bad.append(f"CANDIDATES 서로 다른 후보 {CANDIDATES[grade]}개 필요(지금 {cands})")
    if answer not in cands:
        bad.append("ANSWER 정답이 후보 안에 없음")
    if any(not CANDIDATE_CHARS[0] <= len(compact(c)) <= CANDIDATE_CHARS[1] for c in cands):
        bad.append(f"CANDIDATES 후보는 {CANDIDATE_CHARS[0]}~{CANDIDATE_CHARS[1]}자")
    if any(COLOR.search(c) for c in cands):
        bad.append("CANDIDATES 후보 이름에 색 낱말(색으로 빼면 이름과 모순)")
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
            elif len(v) > TEXT_MAX[k]:
                bad.append(f"LENGTH {d['day']}.{k} {len(v)}자 > {TEXT_MAX[k]}")
        # 단서는 그날 미션을 마친 뒤 보여 주므로 증거 발견 줄은 단서 결론을 말하지 않는다. 수사 연결
        # 문장은 그날 배울 개념을 말하는 자리라 개념 낱말이 단서 값과 같을 수밖에 없어
        # (특징을 성취기준
        # 내용에서 고름, 실측 repo-fair4-3) 코드로 막지 않고 글 검토(정답 암시)가 본다
        if clue_evidence_mismatch(d):
            bad.append(
                f"CLUE_EVIDENCE {d['day']} clue 단서 문장의 "
                "증거와 evidence 종류가 다름(사진·영상·녹음·기록·"
                "일지·메모를 말하면 RECORD, RECORD면 그 기록을 말함)"
            )
        for problem in clue_wording_problems(d):
            bad.append(f"CLUE_WORDING {d['day']} clue {problem}")
        if early := early_values(d, d.get("discovery")):
            bad.append(f"CLUE_EARLY {d['day']} discovery에 그날 단서 결론(허용 값 {early})")
        for k in ("discovery", "missionHook"):
            named = [c for c in cands if c != answer and compact(c) in compact(d.get(k))]
            if named:
                bad.append(f"ANSWER_LEAK {d['day']}.{k}에 후보 이름 {named}")
    bad += check_logic(theme, cands, answer, days)
    bad += check_cuts(theme)
    types = [d.get("clueType") for d in days]
    if any(x not in CLUE_TYPES for x in types) or len(set(types)) != len(types):
        bad.append(f"CLUE_TYPE 다섯 단서는 서로 다른 종류(지금 {types})")
    if answer:  # 정답 이름은 종료 이야기에만
        key = compact(answer)
        fields = [
            (k, theme.get(k))
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
    return bad


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
    answers, numeric = mission_checks._answer_texts(draft)
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
        if numeric and any(mission_checks._has_number(text, n) for n in numeric):
            bad.append("LEAK ANSWER_KEY")
        if key and key in compact(text):
            bad.append(f"THEME_ANSWER_LEAK 대화에 테마 정답 낱말 '{theme['answer']}'")
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
    """응답 Theme에 넣는 칸만(정답 논리 검사용 내부 칸 제외)."""
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
        "days": [{k: d[k] for k in day_keep} for d in theme["days"]],
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
    answers, numeric = mission_checks._answer_texts(draft)
    if find_text_leaks(
        text, answers, draft.forbidden_terms, draft.example_answer, overlap, [draft.question]
    ):
        return True
    return bool(numeric and any(mission_checks._has_number(text, n) for n in numeric))


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
