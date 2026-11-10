"""주간 테마 초안 코드 검사 (class-diagram 5.5 ThemeChecks, #437).

정답 논리는 줄거리가 함께 만든 후보 특징 표(features)와 요일별 단서 조건(condition)으로
계산해 판정한다. LLM 추리 이야기 생성 연구처럼 논리 구조는 기계가 확인하고, 문장이 조건을
그대로 말하는지·자연스러운지는 검토 모델이 본다(ai.md 15절). 텍스트 시험(2026-11-10)에서
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
DIALOGUE_LINES = {3: (2, 3), 4: (2, 3), 5: (1, 2), 6: (1, 2)}  # 증거 발견 줄 포함
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
    "missionHook": 60,
}
DAY_TEXTS = ("place", "sceneNote", "clue", "discovery", "missionHook")
CUTS = 4  # 시작·종료 영상 콘티 컷 수(4·6·8·6초, theme_video_cut_seconds, 사용자 결정 2026-11-11)
CAPTION_MAX = 30  # 컷 문구(움직임 captions로 웹이 띄움) 글자 상한(기준안)
MUNGCHI_MOODS = ("none", "smile", "surprised", "determined")
# 시작 콘티 1 평소 모습·2 사건에는 뭉치가 없고 3 출동·4 현장 도착에는 나옴(사용자 결정 2026-11-11)
INTRO_MUNGCHI = (False, False, True, True)
HOOK_HEAD = 12  # 미션 질문이 missionHook으로 시작하는지 볼 때 겹칠 앞 글자 수(공백 제외)
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
            mood = cut.get("mungchiMood")
            if mood not in MUNGCHI_MOODS:
                bad.append(f"CUT_MOOD {key}{i} mungchiMood는 {list(MUNGCHI_MOODS)} 중 하나")
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
        # 단서는 그날 미션을 마친 뒤 보여 주므로 미션 전 글(증거 발견 줄·수사 연결 문장)은 단서
        # 결론·후보 이름을 말하지 않는다(정답 이름은 아래 ANSWER_LEAK에서 함께 봄)
        for k in ("discovery", "missionHook"):
            if early := early_values(d, d.get(k)):
                bad.append(f"CLUE_EARLY {d['day']} {k}에 그날 단서 결론(허용 값 {early})")
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
    """테마 미션 검사: 기존 미션 초안 ai 검사 + 학년별 생각 열기 개수 + 수사 연결 문장으로 시작
    + 테마 정답 유출 + 언어."""
    bad = [
        f"{f.check} {f.reason}" for f in mission_checks.check(draft, request, question_max, overlap)
    ]
    hints = len([h for h in draft.hints if h.strip()])
    if hints != HINTS[grade]:
        bad.append(f"HINT_COUNT 생각 열기 질문 {hints}개(초{grade}는 {HINTS[grade]}개)")
    # 질문은 그날 missionHook으로 시작한다(공백 무시 앞 HOOK_HEAD자가 질문 앞부분에 있으면 통과,
    # 앞에 따옴표 같은 몇 글자가 붙는 것은 허용)
    day = next(d for d in theme["days"] if d["thinkingType"] == request.thinking_type)
    hook = compact(day.get("missionHook"))[:HOOK_HEAD]
    if hook and not overlaps(hook, compact(draft.question)[: 2 * HOOK_HEAD], len(hook)):
        bad.append(
            f"HOOK_MISSING {day['day']} 질문이 수사 연결 문장(missionHook)으로 시작하지 않음"
        )
    key = compact(theme["answer"])
    texts = [
        draft.question,
        draft.guide or "",
        *draft.hints,
        draft.example_answer or "",
        *[c.label for c in draft.choices or []],
    ]
    if key and any(key in compact(x) for x in texts):
        bad.append("THEME_ANSWER_LEAK 문제·안내·생각 열기 질문·예시 답에 테마 정답")
    if any(FOREIGN.search(x) for x in [*texts, draft.title]):
        bad.append("LANGUAGE 한국어 밖 글자(가나·한자)")
    return bad


def discovery_speaker(generated: dict) -> str:
    """증거 발견 줄 화자. 비어 있으면 뭉치(기본)."""
    return (generated.get("discoverySpeaker") or "").strip() or "뭉치"


def dialogue_lines(generated: dict, discovery: str) -> list[dict[str, str]]:
    """LLM 줄 + 그날 증거 발견 줄 그대로(discoverySpeaker, 기본 뭉치).

    단서는 학생이 그날 미션을 마친 뒤 learning이 보여 주므로 대화에 넣지 않고, 앞 요일 단서
    요약 줄도 두지 않는다(아직 못 얻은 단서를 흘리므로, 사용자 결정 2026-11-11).
    """
    return [{"speaker": x["speaker"], "text": x["text"]} for x in generated.get("lines") or []] + [
        {"speaker": discovery_speaker(generated), "text": discovery}
    ]


def is_target(theme: Theme, speaker: str | None) -> bool:
    """화자가 찾는 대상인지(이름 일부만 써도 같은 대상: '강아지 보리'와 '보리')."""
    s, target = compact(speaker), compact(theme.get("target"))
    return len(s) >= 2 and bool(target) and (s in target or target in s)


def check_dialogue(
    theme: Theme, day: str, generated: dict, draft: Draft, grade: int, overlap: int
) -> list[str]:
    bad = []
    d = theme_day(theme, day)
    discovery = d["discovery"]
    lines = dialogue_lines(generated, discovery)
    llm_lines = generated.get("lines") or []
    lo, hi = DIALOGUE_LINES[grade]
    if not lo <= len(lines) <= hi:
        bad.append(f"LINE_COUNT {len(lines)}줄(초{grade}는 증거 발견 줄 포함 {lo}~{hi}줄)")
    speakers = {"뭉치"} | {c["name"] for c in theme["characters"]}
    if discovery_speaker(generated) not in speakers:
        bad.append(f"DISCOVERY_SPEAKER 증거 발견 줄 화자는 {sorted(speakers)} 중 하나")
    if any(overlaps(x.get("text"), discovery, overlap) for x in llm_lines):
        bad.append("DISCOVERY_REPEATED LLM 줄이 증거 발견 줄을 미리 말함")
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
    for x in lines:
        text = x["text"]
        # 질문과 증거 발견 줄은 학생이 이미 보는 글이라 예시 답과 겹쳐도 유출로 보지 않음
        for reason in find_text_leaks(
            text,
            answers,
            draft.forbidden_terms,
            draft.example_answer,
            overlap,
            [draft.question, discovery],
        ):
            bad.append(f"LEAK {reason}")
        if numeric and any(mission_checks._has_number(text, n) for n in numeric):
            bad.append("LEAK ANSWER_KEY")
        if key and key in compact(text):
            bad.append("THEME_ANSWER_LEAK 대화에 테마 정답")
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
VIDEO_REVIEW_IDS = ("MORPH", "ANSWER_HINT", "TEXT", "SAFETY")

# 움직임 상한(기준안, ai.md 15.1 움직임 행)
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


def motion(generated: dict, speakers: list[str], captions: list[dict]) -> tuple[dict, list[str]]:
    """생성 모델의 움직임 값 → ThemeMotion 모양과 맞춘 항목 사유(warnings MOTION).

    상한 밖 숫자는 상한으로 맞추고, 색이 #RRGGBB가 아니면 그 효과를 빼고, 화자가 아닌 이름은
    뺀다. 다시 생성하지 않는다(정해진 처리, ai.md 15.1).
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
    }
    return result, notes
