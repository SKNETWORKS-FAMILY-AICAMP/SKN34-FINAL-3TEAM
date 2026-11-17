"""추억 검색 평가셋 memory@1 검사 (#568). 표준 라이브러리만 씀.

    python -I check_dataset.py [평가셋 폴더]

형식·참조·개수·나누기와 정답 근거(그 소재가 정답 회차에만 있는지)를 본다.
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


def main(folder):
    root = pathlib.Path(folder)
    themes = json.loads((root / "themes.json").read_text(encoding="utf-8"))
    data = json.loads((root / "students.json").read_text(encoding="utf-8"))
    queries = [json.loads(line) for line in (root / "queries.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

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
    print(f"테마 {len(themes)} · 학생 {len(students)} · 질문 {len(queries)} · 정답 확인 {checked}/{len(queries)}")
    for split, b in sorted(by_split.items()):
        print(f"  {split}: {b}")
    if errors:
        print(f"문제 {len(errors)}건")
        for e in errors:
            print(" -", e)
        return 1
    print("문제 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).parent))
