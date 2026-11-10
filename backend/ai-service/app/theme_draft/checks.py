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
DIALOGUE_LINES = {3: (2, 3), 4: (2, 3), 5: (1, 2), 6: (1, 2)}  # recap·단서 줄 포함
LINE_MAX = 40
LAST_ELIMINATION_MIN = DAYS.index("THU")  # 마지막 틀린 후보는 목요일 이후(수요일까지 2개 이상 남음)
# 글자 수 상한(기준안, 학년 공통). 단서는 대화 한 줄로 그대로 나가 LINE_MAX와 같음
TEXT_MAX = {
    "title": 20,
    "bigQuestion": 40,
    "intro": 200,
    "outro": 300,
    "place": 20,
    "sceneNote": 150,
    "clue": LINE_MAX,
}
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
        for k in ("place", "sceneNote", "clue"):
            v = d.get(k) or ""
            if not v.strip():
                bad.append(f"REQUIRED {d['day']}.{k}")
            elif len(v) > TEXT_MAX[k]:
                bad.append(f"LENGTH {d['day']}.{k} {len(v)}자 > {TEXT_MAX[k]}")
    bad += check_logic(theme, cands, answer, days)
    types = [d.get("clueType") for d in days]
    if any(x not in CLUE_TYPES for x in types) or len(set(types)) != len(types):
        bad.append(f"CLUE_TYPE 다섯 단서는 서로 다른 종류(지금 {types})")
    if answer:  # 정답 이름은 종료 이야기에만
        key = compact(answer)
        fields = [
            (k, theme.get(k))
            for k in ("title", "world", "intro", "bigQuestion", "styleNote", "outfit")
        ]
        fields += [
            (f"{d['day']}.{k}", d.get(k)) for d in days for k in ("place", "sceneNote", "clue")
        ]
        fields += [
            (f"characters.{c.get('name')}", (c.get("name") or "") + (c.get("look") or ""))
            for c in chars
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
    """테마 미션 검사: 기존 미션 초안 ai 검사 + 학년별 생각 열기 개수 + 테마 정답 유출 + 언어."""
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
        bad.append("THEME_ANSWER_LEAK 문제·안내·생각 열기 질문·예시 답에 테마 정답")
    if any(FOREIGN.search(x) for x in [*texts, draft.title]):
        bad.append("LANGUAGE 한국어 밖 글자(가나·한자)")
    return bad


def clue_list(theme: Theme, upto: int) -> list[str]:
    return [f"{DAY_KO[d['day']]}요일: {d['clue']}" for d in theme["days"][:upto]]


def finish_mission(theme: Theme, day: str, draft: Draft) -> Draft:
    """금요일 안내에 그때까지의 단서 전부(놓친 날 대응). 검사를 거친 단서 글이라 검사 뒤에 "
    "넣는다."""
    if day != "FRI":
        return draft
    return draft.model_copy(
        update={"guide": "지금까지 모은 단서\n" + "\n".join(clue_list(theme, 5))}
    )


def day_clue(theme: Theme, day: str) -> str:
    return next(d for d in theme["days"] if d["day"] == day)["clue"]


def dialogue_lines(generated: dict, clue: str) -> list[dict[str, str]]:
    """recap(뭉치) + LLM 줄 + 그날 단서 문장 그대로(clueSpeaker)."""
    recap = (generated.get("recap") or "").strip()
    return (
        ([{"speaker": "뭉치", "text": recap}] if recap else [])
        + [{"speaker": x["speaker"], "text": x["text"]} for x in generated.get("lines") or []]
        + [{"speaker": generated.get("clueSpeaker") or "", "text": clue}]
    )


def is_target(theme: Theme, speaker: str | None) -> bool:
    """화자가 찾는 대상인지(이름 일부만 써도 같은 대상: '강아지 보리'와 '보리')."""
    s, target = compact(speaker), compact(theme.get("target"))
    return len(s) >= 2 and bool(target) and (s in target or target in s)


def check_dialogue(
    theme: Theme, day: str, generated: dict, draft: Draft, grade: int, overlap: int
) -> list[str]:
    bad = []
    recap = (generated.get("recap") or "").strip()
    if day == "MON" and recap:
        bad.append("RECAP 월요일에는 요약 없음")
    if day != "MON" and not recap:
        bad.append("RECAP 화~금은 앞 요일까지 단서 요약 한 줄")
    clue = day_clue(theme, day)
    lines = dialogue_lines(generated, clue)
    lo, hi = DIALOGUE_LINES[grade]
    if not lo <= len(lines) <= hi:
        bad.append(f"LINE_COUNT {len(lines)}줄(초{grade}는 단서 줄 포함 {lo}~{hi}줄)")
    speakers = {"뭉치"} | {c["name"] for c in theme["characters"]}
    if generated.get("clueSpeaker") not in speakers:
        bad.append(f"CLUE_SPEAKER 단서 화자는 {sorted(speakers)} 중 하나")
    if any(overlaps(x.get("text"), clue, overlap) for x in generated.get("lines") or []):
        bad.append("CLUE_REPEATED LLM 줄이 단서 문장을 다시 말함")
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
        # 질문과 단서 문장은 학생이 이미 보는 글이라 예시 답과 겹쳐도 유출로 보지 않음
        for reason in find_text_leaks(
            text,
            answers,
            draft.forbidden_terms,
            draft.example_answer,
            overlap,
            [draft.question, clue],
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
