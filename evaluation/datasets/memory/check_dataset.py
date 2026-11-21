"""추억 검색 평가셋 memory@1(#568)·memory@2(#853) 검사. 표준 라이브러리만 씀.

    python -I check_dataset.py [평가셋 폴더]     # 기본 이 폴더(memory@1), memory@2는 ../memory@2

형식·참조·개수·나누기와 정답 근거(그 소재가 정답 회차에만 있는지)를 본다. memory@2는 정답·경계를 기간 규칙으로 다시 계산해 맞춰 본다.
문제가 있으면 목록을 찍고 1로 끝난다. 정답표 사람 확인(checkedBy, 1명)은 개수만 알려 주고 막지 않는다.
"""
import datetime as dt
import json
import pathlib
import re
import sys

DAYS = ["MON", "TUE", "WED", "THU", "FRI"]
CATS = {"TITLE": 2, "PARAPHRASE": 3, "ANSWER": 3, "MULTI": 1, "NONE": 2, "OTHER": 2, "SCOPE": 2}
RESULT_CATS = {"TITLE", "PARAPHRASE", "ANSWER", "MULTI"}
PARTICLES = ("에서", "으로", "을", "를", "이", "가", "은", "는", "에", "의", "와", "과", "도", "로", "요")
TEXT_MIN, TEXT_MAX = 30, 150

errors = []


def err(msg):
    errors.append(msg)


def stems(title):
    out = []
    for w in title.split():
        for p in PARTICLES:
            if w.endswith(p) and len(w) - len(p) >= 2:
                w = w[: -len(p)]
                break
        if len(w) >= 2:
            out.append(w)
    return out


def plain(answer, mission):
    """learning AnswerContent.plainText와 같은 모양으로 근사(선택형은 빈 글)."""
    if answer is None:
        return ""
    if "text" in answer:
        return answer["text"]
    if "essay" in answer:
        e = answer["essay"]
        return "\n".join([e["claim"], *e["reasons"], e["rebuttal"]])
    if "steps" in answer:
        return "\n".join(answer["steps"]) + "\n최종 답: " + answer["finalAnswer"]
    return ""


def shape_ok(answer, input_type):
    if answer is None:
        return input_type in ("CHOICE", "ORDERING", "CLASSIFICATION", "SOLUTION_STEPS")
    return {"NARRATIVE": "text" in answer, "ESSAY": "essay" in answer,
            "SOLUTION_STEPS": "steps" in answer and "finalAnswer" in answer}.get(input_type, "choiceIds" in answer)


def weekdays_in(week_start, period):
    """회차 주 월~금 중 반열림 기간 [from, to) 안에 든 날 수(memory@2 정답·경계 규칙: 3일 이상 정답, 1~2일 경계)"""
    s, f, t = (dt.date.fromisoformat(x) for x in (week_start, period["from"], period["to"]))
    return sum(f <= s + dt.timedelta(days=i) < t for i in range(5))


def report(summary):
    print(summary)
    if errors:
        print(f"문제 {len(errors)}건")
        for e in errors:
            print(" -", e)
        return 1
    print("문제 없음")
    return 0


def main_v2(themes, data, queries):
    """memory@2(#853): 주마다 다른 미션 52주, 학생마다 최근 N주, 기간 질문. 정답·경계는 기간 규칙으로 다시 계산해 맞춰 본다."""
    weeks, gaps = data["weeks"], set(data["gapWeeks"])
    order = list(weeks)
    if order != [f"W{i:02d}" for i in range(1, len(order) + 1)]:
        err("주 키가 W01부터 차례가 아님")
    dates = [dt.date.fromisoformat(weeks[k]) for k in order]
    if any(d.isoweekday() != 1 for d in dates) or dates != sorted(dates):
        err("주 시작일이 월요일 오름차순이 아님")
    d = dates[0]
    while d <= dates[-1]:  # 처음~마지막 주 사이 모든 월요일은 푸는 주 아니면 방학 주
        if (d in dates) == (d.isoformat() in gaps):
            err(f"{d}: 푸는 주와 방학 주 중 정확히 하나여야 함")
        d += dt.timedelta(days=7)
    today = dt.date.fromisoformat(data["evalToday"])
    this_monday = today - dt.timedelta(days=today.isoweekday() - 1)
    if dates[-1] >= this_monday:
        err("마지막 주가 평가 기준일의 진행 주보다 앞이 아님")

    if len({t["themeKey"] for t in themes}) != len(themes) or len({t["title"] for t in themes}) != len(themes):
        err("테마 키·제목 중복")
    theme_of = {}
    for t in themes:
        if [x["day"] for x in t["days"]] != DAYS or any(not x["dialogue"] for x in t["days"]):
            err(f"{t['themeKey']} 요일·대화가 월~금 다섯 개가 아님")
        if t["week"] in theme_of or t["week"] not in weeks or t["grade"] != 5:
            err(f"{t['themeKey']} 주 {t['week']}·학년 배정이 다름")
        theme_of[t["week"]] = t
    if set(theme_of) != set(order):
        err("테마가 없는 주가 있음")

    seed = data["seedMissions"]["G5"]
    if list(seed) != DAYS or len({m["code"].rsplit("-", 1)[-1] for m in seed.values()}) != 5:
        err("시드 틀 미션이 월~금 생각 유형 다섯이 아님")
    docs = {}  # 주 → 검색 문서와 비슷한 글(답 두 변형 모두)
    questions = {d: set() for d in DAYS}
    for wk in order:
        wm = data["weekMissions"].get(wk) or {}
        parts = [theme_of[wk]["title"]] if wk in theme_of else []
        for i, day in enumerate(DAYS):
            m = wm.get(day)
            if not m or not m.get("title") or not m.get("question"):
                err(f"{wk} {day} 미션 제목·질문 없음")
                continue
            if m["question"] in questions[day]:
                err(f"{wk} {day} 질문이 다른 주와 같음")
            questions[day].add(m["question"])
            kind = seed[day]["inputType"]
            if kind == "SOLUTION_STEPS" and not re.fullmatch(r"\d+", m.get("finalAnswer") or ""):
                err(f"{wk} {day} 풀이 단계 정답이 수가 아님")
            if wk in theme_of:
                parts += [" ".join(x["text"] for x in theme_of[wk]["days"][i]["dialogue"]), m["question"]]
            for v in ("A", "B"):
                a = (m.get("answers") or {}).get(v)
                if a is None or not shape_ok(a, kind):
                    err(f"{wk} {day} 답 {v} 모양이 {kind}와 맞지 않음")
                    continue
                if "text" in a and not TEXT_MIN <= len(a["text"]) <= TEXT_MAX:
                    err(f"{wk} {day} 답 {v} 글 길이 {len(a['text'])}자({TEXT_MIN}~{TEXT_MAX} 밖)")
                if "essay" in a and any(not 10 <= len(f) <= 120 for f in [a["essay"]["claim"], *a["essay"]["reasons"], a["essay"]["rebuttal"]]):
                    err(f"{wk} {day} 답 {v} 논술 칸 길이(10~120 밖)")
                if "steps" in a and a["finalAnswer"] != m.get("finalAnswer"):
                    err(f"{wk} {day} 답 {v} 최종 답이 미션 정답과 다름")
                parts.append(plain(a, None))
        docs[wk] = "\n".join(parts)

    # 소재: 태그한 주에만 그 낱말이 있어야 "기간 + 소재" 질문의 정답·섞임이 정해진다
    for subj, word in data["subjectWords"].items():
        tagged = sorted(wk for wk in order if (data["weekMissions"].get(wk) or {}).get("subject") == subj)
        if tagged != sorted(data["subjects"].get(subj, [])):
            err(f"소재 {subj}: subjects 목록과 주별 태그가 다름")
        having = sorted(wk for wk, t in docs.items() if word in t)
        if having != tagged:
            err(f"소재 낱말 '{word}'가 든 주 {having} ≠ 태그한 주 {tagged}")

    students = {s["studentKey"]: s for s in data["students"]}
    parents = {}
    for s in data["students"]:
        n = s["weekCount"]
        if not re.fullmatch(r"[a-z0-9]{1,10}", s["nickname"]) or not re.fullmatch(r"[a-z0-9]{1,5}", s.get("parent") or ""):
            err(f"{s['studentKey']} 닉네임·parent 형식")
        if s["grade"] != 5 or s["variant"] not in ("A", "B") or s["deleteAfterLoad"]:
            err(f"{s['studentKey']} 학년·답 변형·삭제 칸")
        if not 1 <= n <= len(order) or s["firstWeek"] != order[-n] or s["size"] != 5 * n:
            err(f"{s['studentKey']} 풀이 주 수·첫 주·기록 수가 맞지 않음")
        if any(s["nickname"] in t for t in docs.values()):
            err(f"{s['studentKey']} 글에 닉네임이 들어 있음")
        parents.setdefault(s["parent"], []).append(s)
    if len({s["nickname"] for s in data["students"]}) != len(students):
        err("닉네임 중복")
    for p, kids in parents.items():
        if len(kids) > 3:
            err(f"학부모 {p} 자녀 {len(kids)}명 > 3")

    if len({q["queryId"] for q in queries}) != len(queries):
        err("질문 ID 중복")
    count = {}
    for q in queries:
        s = students.get(q["studentKey"])
        if s is None:
            err(f"{q['queryId']} 없는 학생")
            continue
        count[(s["studentKey"], q["category"])] = count.get((s["studentKey"], q["category"]), 0) + 1
        p = q["period"]
        if not p["from"] < p["to"] <= this_monday.isoformat():
            err(f"{q['queryId']} 기간 {p}가 비었거나 진행 주를 넘음")
        if (q["category"] == "PERIOD_ONLY") != (q["subject"] is None) and q["category"] != "PERIOD_EMPTY":
            err(f"{q['queryId']} 기간만 질문인데 소재가 있거나, 소재 질문인데 소재가 없음")
        mine = order[-s["weekCount"]:]
        gold = [wk for wk in mine if weekdays_in(weeks[wk], p) >= 3
                and (q["subject"] is None or data["weekMissions"][wk]["subject"] == q["subject"])]
        edge = [wk for wk in mine if 1 <= weekdays_in(weeks[wk], p) <= 2]
        if [g["week"] for g in q["gold"]] != gold or [b["week"] for b in q["boundary"]] != edge:
            err(f"{q['queryId']} 정답·경계가 기간 규칙과 다름(정답 {gold}, 경계 {edge})")
        if any(g["themeKey"] != theme_of[g["week"]]["themeKey"] for g in q["gold"] + q["boundary"]):
            err(f"{q['queryId']} 정답·경계 테마 키가 주 배정과 다름")
        if q["expect"] != ("RESULTS" if gold else "NO_RESULTS"):
            err(f"{q['queryId']} expect가 정답 유무와 맞지 않음")
        if q["category"] == "PERIOD_EMPTY" and gold:
            err(f"{q['queryId']} 기록 없음 질문인데 정답이 있음")
    want = {"PERIOD_TOPIC": 10, "PERIOD_ONLY": 6, "PERIOD_EMPTY": 4}
    for key in students:
        got = {c: n for (k, c), n in count.items() if k == key}
        if got != want:
            err(f"{key} 질문 종류 개수 {got} ≠ {want}")
    exp = {}
    for q in queries:
        k = (students[q["studentKey"]]["weekCount"], q["expect"])
        exp[k] = exp.get(k, 0) + 1
    checked = sum(bool(q["checkedBy"]) for q in queries)
    return report(f"주 {len(order)}(방학 {len(gaps)}) · 테마 {len(themes)} · 학생 {len(students)} · 질문 {len(queries)} · "
                  f"정답 확인 {checked}/{len(queries)} · (주 수, 기대)별 {dict(sorted(exp.items()))}")


def main(folder):
    root = pathlib.Path(folder)
    themes = json.loads((root / "themes.json").read_text(encoding="utf-8"))
    data = json.loads((root / "students.json").read_text(encoding="utf-8"))
    queries = [json.loads(line) for line in (root / "queries.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if data["dataset"] == "memory@2":
        return main_v2(themes, data, queries)

    # 주
    weeks = data["weeks"]
    dates = [dt.date.fromisoformat(weeks[f"W{i}"]) for i in range(1, len(weeks) + 1)]
    for i, d in enumerate(dates):
        if d.isoweekday() != 1:
            err(f"W{i + 1} {d}가 월요일이 아님")
        if i and (d - dates[i - 1]).days != 7:
            err(f"W{i + 1}가 앞 주와 7일 차이가 아님")

    # 테마
    by_key = {t["themeKey"]: t for t in themes}
    if len(by_key) != len(themes):
        err("테마 키 중복")
    if len({t["title"] for t in themes}) != len(themes):
        err("테마 제목 중복")
    slot = {}
    for t in themes:
        if [d["day"] for d in t["days"]] != DAYS or any(not d["dialogue"] for d in t["days"]):
            err(f"{t['themeKey']} 요일·대화가 월~금 다섯 개가 아님")
        k = (t["grade"], t["week"])
        if k in slot:
            err(f"학년 {k[0]} {k[1]}에 테마가 둘({slot[k]}, {t['themeKey']})")
        slot[k] = t["themeKey"]

    # 미션
    missions = data["missions"]
    for g, plan in missions.items():
        if list(plan) != DAYS:
            err(f"{g} 미션 요일이 월~금이 아님")
        kinds = {m["code"].rsplit("-", 1)[-1] for m in plan.values()}
        if len(kinds) != 5:
            err(f"{g} 생각 유형 다섯이 하나씩이 아님: {kinds}")

    # 학생과 학생별 글
    students = {s["studentKey"]: s for s in data["students"]}
    if len({s["nickname"] for s in data["students"]}) != len(students):
        err("닉네임 중복")
    for s in data["students"]:
        if not re.fullmatch(r"[a-z0-9]{1,10}", s["nickname"]):
            err(f"{s['studentKey']} 닉네임 {s['nickname']}: 영문 소문자·숫자만(PowerShell 인자)")
    # 학부모: 자녀 최대 3명(core MAX_CHILDREN), 준비 SQL은 초3·초5 짝이 같은 학부모 1명이어야 함
    parents = {}
    for s in data["students"]:
        if not re.fullmatch(r"[a-z0-9]{1,5}", s.get("parent") or ""):
            err(f"{s['studentKey']} parent 칸이 없거나 형식이 다름")
        parents.setdefault(s.get("parent"), []).append(s)
    for p, kids in parents.items():
        if len(kids) > 3:
            err(f"학부모 {p} 자녀 {len(kids)}명 > 3")
        live = [k for k in kids if not k["deleteAfterLoad"]]
        if sorted(k["grade"] for k in live) != [3, 5]:
            err(f"학부모 {p}: 남는 자녀가 초3·초5 한 명씩이 아님(준비 SQL 짝)")
    docs = {}      # (학생, 주) → 검색 문서와 비슷한 글(완주 회차만)
    scope = {}     # (학생, 칸) → 범위 시험 글
    for s in data["students"]:
        key, grade, plan = s["studentKey"], s["grade"], missions[f"G{s['grade']}"]
        want_split = "deleted" if s["deleteAfterLoad"] else ("tune" if grade == 3 else "eval")
        if s["split"] != want_split:
            err(f"{key} split {s['split']} ≠ {want_split}")
        texts = []
        for r in s["rounds"]:
            if slot.get((grade, r["week"])) != r["themeKey"]:
                err(f"{key} {r['week']} 테마 {r['themeKey']}가 학년·주 배정과 다름")
            if r["complete"] != (r["week"] != "W7") or (r["complete"] and r["days"] != DAYS) or (not r["complete"] and len(r["days"]) != 3):
                err(f"{key} {r['week']} 완주·요일 수가 규칙(W1~W6 다섯, W7 셋)과 다름")
            if list(r["answers"]) != r["days"]:
                err(f"{key} {r['week']} 답 요일이 days와 다름")
            theme = by_key[r["themeKey"]]
            parts = [theme["title"]]
            for d in r["days"]:
                a, m = r["answers"][d], plan[d]
                if not shape_ok(a, m["inputType"]):
                    err(f"{key} {r['week']} {d} 답 모양이 {m['inputType']}와 맞지 않음")
                    continue
                if a is not None and "text" in a and not TEXT_MIN <= len(a["text"]) <= TEXT_MAX:
                    err(f"{key} {r['week']} {d} 글 길이 {len(a['text'])}자({TEXT_MIN}~{TEXT_MAX} 밖)")
                if a is not None and "essay" in a:
                    e = a["essay"]
                    for f in [e["claim"], *e["reasons"], e["rebuttal"]]:
                        if not 10 <= len(f) <= 120:
                            err(f"{key} {r['week']} {d} 논술 칸 길이 {len(f)}자(10~120 밖)")
                body = plain(a, m)
                texts.append(body)
                day_dialogue = " ".join(x["text"] for x in theme["days"][DAYS.index(d)]["dialogue"])
                parts += [day_dialogue, m["question"], body]
                if not r["complete"]:
                    scope[(key, f"{r['week']}.{d}")] = body
            if r["complete"]:
                docs[(key, r["week"])] = "\n".join(parts)
        for name in ("extra", "current"):
            if s.get(name):
                body = plain(s[name]["answer"], None)
                texts.append(body)
                scope[(key, name.upper())] = body
            elif not s["deleteAfterLoad"] and (name == "current" or grade == 5):
                err(f"{key} {name} 기록 없음")  # EXTRA는 프리미엄 전용이라 초5만
        if grade == 3 and s.get("extra"):
            err(f"{key} 초3은 무료라 EXTRA를 풀 수 없음")
        for t in texts:
            if s["nickname"] in t:
                err(f"{key} 글에 닉네임이 들어 있음")
        if not s["deleteAfterLoad"] and sum(r["complete"] for r in s["rounds"]) != 6:
            err(f"{key} 완주 회차가 6개가 아님")

    # 질문
    if len({q["queryId"] for q in queries}) != len(queries):
        err("질문 ID 중복")
    count = {}
    for q in queries:
        key, cat = q["studentKey"], q["category"]
        s = students.get(key)
        if s is None:
            err(f"{q['queryId']} 없는 학생 {key}")
            continue
        count[(key, cat)] = count.get((key, cat), 0) + 1
        if q["split"] != s["split"]:
            err(f"{q['queryId']} split이 학생과 다름")
        want = "NO_RECORDS" if cat == "DELETED" else ("RESULTS" if cat in RESULT_CATS else "NO_RESULTS")
        if q["expect"] != want or bool(q["gold"]) != (want == "RESULTS"):
            err(f"{q['queryId']} expect·gold가 종류 {cat}와 맞지 않음")
        gold_weeks = [g["week"] for g in q["gold"]]
        for g in q["gold"]:
            if (key, g["week"]) not in docs or slot[(s["grade"], g["week"])] != g["themeKey"]:
                err(f"{q['queryId']} 정답 {g}가 그 학생 완주 회차가 아님")
        own = {w: t for (k, w), t in docs.items() if k == key}
        if cat == "TITLE":
            title = by_key[q["gold"][0]["themeKey"]]["title"]
            if not any(w in q["query"] for w in stems(title)):
                err(f"{q['queryId']} 제목 질문인데 제목 낱말이 없음")
        if cat == "PARAPHRASE":
            title = by_key[q["gold"][0]["themeKey"]]["title"]
            hit = [w for w in stems(title) if w in q["query"]]
            if hit:
                err(f"{q['queryId']} 다른 표현 질문에 제목 낱말 {hit}")
        if cat in ("ANSWER", "MULTI"):
            phrases = q["mustContain"]
            having = sorted(w for w, t in own.items() if all(p in t for p in phrases))
            if having != sorted(gold_weeks):
                err(f"{q['queryId']} 소재 {phrases}가 든 회차 {having} ≠ 정답 {sorted(gold_weeks)}")
        if cat == "SCOPE":
            target = scope.get((key, q["evidence"]))
            if target is None or not all(p in target for p in q["mustContain"]):
                err(f"{q['queryId']} 범위 시험 소재 {q['mustContain']}가 {q['evidence']} 글에 없음")
            leaked = [w for w, t in own.items() if all(p in t for p in q["mustContain"])]
            if leaked:
                err(f"{q['queryId']} 범위 시험 소재가 완주 회차 {leaked}에도 있음")
        if cat in ("NONE", "OTHER"):
            leaked = [w for w, t in own.items() if any(p in t for p in q["mustNotContain"])]
            if leaked:
                err(f"{q['queryId']} {q['mustNotContain']}가 그 학생 회차 {leaked}에 있음")
        if cat == "OTHER":
            t = by_key.get(q["evidence"])
            if t is None or t["grade"] == s["grade"]:
                err(f"{q['queryId']} 다른 학생 질문의 테마 {q['evidence']}가 다른 학년 테마가 아님")
    for key, s in students.items():
        want = {"DELETED": 2} if s["deleteAfterLoad"] else CATS
        got = {c: n for (k, c), n in count.items() if k == key}
        if got != want:
            err(f"{key} 질문 종류 개수 {got} ≠ {want}")

    # 요약
    by_split = {}
    for q in queries:
        b = by_split.setdefault(q["split"], {"RESULTS": 0, "NO_RESULTS": 0, "NO_RECORDS": 0})
        b[q["expect"]] += 1
    checked = sum(bool(q["checkedBy"]) for q in queries)
    return report("\n".join([f"테마 {len(themes)} · 학생 {len(students)} · 질문 {len(queries)} · 정답 확인 {checked}/{len(queries)}",
                             *(f"  {split}: {b}" for split, b in sorted(by_split.items()))]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).parent))
