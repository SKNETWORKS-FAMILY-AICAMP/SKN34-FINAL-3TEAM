"""추억 검색 평가 러너 (#568, 기준안 retention-expansion.md 18장, 하이브리드는 score --as-served).

평가셋 memory@1(evaluation/datasets/memory/)의 질문마다 같은 DB·같은 접근 범위에서 검색 방식만 바꿔 비교한다.

- V  = learning 내부 검색 API(실제 임베딩·pgvector). 평가 동안 MEMORY_MINIMUM_SIMILARITY=-1로 상위 3회차와 점수를 받고
       기준값은 여기서 다시 적용한다(기준값은 상위 3회차 안에서만 거르므로 결과가 같다)
- K1 = 서비스 키워드 기준선 그대로(MemoryVectorMapper.hits 키워드 쪽: 최신 답 plain_text ILIKE '%질문 전체%')
- K2 = 같은 검색 문서 content_text에 질문 낱말(2자 이상, 끝 조사 1개 뗌)이 많이 든 순
K1·K2 SQL은 learning_db 읽기 전용 세션에서 psql로 돌린다(새 라이브러리 없음). 표준 라이브러리만 쓴다.

    # 1) 모으기: 검색 결과·점수·응답 시간 → raw 파일(답·질문 원문 없음)
    python -I memory_search_eval.py collect --learning-url http://127.0.0.1:18082 --token "$INTERNAL_TOKEN" \
        --psql "kubectl exec -i -n platform postgres-0 -- psql -U learning -d learning_db" --label kind-1117
    # 2) 계산: 기준값 고르기(조정용) → 평가용 지표·통과 기준 → 요약 파일
    python -I memory_search_eval.py score --raw ../results/memory/memory@1__kind-1117.raw.json
    # (선택) 임베딩 토큰: 모으기 시간대의 core llm_usage MEMORY_EMBEDDING 합
    python -I memory_search_eval.py usage --psql "<core_db psql>" --since <ISO> --until <ISO>

토큰·비밀번호는 출력하지 않는다. 결과 파일에는 질문 ID·회차 키·시도 ID·점수·시간만 남는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = ROOT / "evaluation" / "datasets" / "memory"
RESULTS = ROOT / "evaluation" / "results" / "memory"
KST = dt.timezone(dt.timedelta(hours=9))
METHODS = ("V", "K1", "K2")
RESULT_CATS = {"TITLE", "PARAPHRASE", "ANSWER", "MULTI"}
REJECT_CATS = {"NONE", "OTHER", "SCOPE"}
PARTICLES = ("에서", "으로", "을", "를", "이", "가", "은", "는", "에", "의", "와", "과", "도", "로", "요")
CURRENT_THRESHOLD = 0.35
SWEEP = [round(0.10 + 0.01 * i, 2) for i in range(51)]  # 0.10~0.60
CRITERIA = {"recall": 0.80, "gap": 0.10, "reject": 0.80, "violations": 0, "p95_ms": 2000}


# ---------- 공통 ----------
def load_dataset(folder: pathlib.Path):
    queries = [json.loads(x) for x in (folder / "queries.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    students = json.loads((folder / "students.json").read_text(encoding="utf-8"))
    return queries, students


def week_monday(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.isoweekday() - 1)


def query_terms(query: str) -> list[str]:
    out = []
    for w in query.split():
        for p in PARTICLES:
            if w.endswith(p) and len(w) - len(p) >= 2:
                w = w[: -len(p)]
                break
        if len(w) >= 2 and w not in out:
            out.append(w)
    return out


def sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def like(value: str) -> str:
    return sql_text("%" + value.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%")


class Psql:
    """psql 명령을 한 번 띄워 읽기 전용으로 여러 질의를 돌린다. 결과는 '@@ 표지'로 나눈다."""

    def __init__(self, command: str):
        self.command = shlex.split(command)

    def run(self, blocks: list[tuple[str, str]]) -> dict[str, list[list[str]]]:
        script = ["\\set ON_ERROR_STOP on", "\\pset footer off", "BEGIN READ ONLY;"]
        for tag, sql in blocks:
            script += [f"\\echo @@{tag}", sql.strip().rstrip(";") + ";"]
        script.append("ROLLBACK;")
        proc = subprocess.run(self.command + ["-X", "-q", "-At", "-F", "\t"], input="\n".join(script),
                              capture_output=True, text=True, encoding="utf-8", check=False)
        if proc.returncode:
            raise SystemExit(f"psql 실패(코드 {proc.returncode}): {proc.stderr.strip()[:300]}")
        out, tag = {}, None
        for line in proc.stdout.splitlines():
            if line.startswith("@@"):
                tag = line[2:]
                out[tag] = []
            elif tag is not None and line and line not in ("BEGIN", "ROLLBACK"):
                out[tag].append(line.split("\t"))
        return out


# ---------- 모으기 ----------
SCOPE_SQL = """
SELECT d.theme_id::text, d.theme_week_start::text, d.attempt_id::text, {score} AS score
FROM memory_search_doc d JOIN attempt a ON a.id = d.attempt_id
JOIN theme_frame f ON f.student_id = d.student_id AND f.theme_id = d.theme_id AND f.theme_week_start = d.theme_week_start
JOIN LATERAL (SELECT plain_text FROM answer WHERE attempt_id = a.id ORDER BY version DESC LIMIT 1) ans ON true
WHERE d.student_id = '{sid}' AND a.student_id = d.student_id AND d.theme_week_start < '{before}' AND d.status = 'READY'
  AND a.context IN ('THEME_DAY','THEME_REVIEW') AND a.completed_at IS NOT NULL AND {where}
"""


def k_sql(method: str, sid: str, before: str, query: str) -> str:
    """K1·K2: 서비스 검색과 같은 범위 조건, 회차 최고 점수로 상위 3회차(서비스 SQL의 rounds와 같은 정렬)."""
    if method == "K1":
        hits = SCOPE_SQL.format(score="1.0", sid=sid, before=before, where=f"ans.plain_text ILIKE {like(query)} ESCAPE '!'")
    else:
        terms = query_terms(query) or [query]
        count = " + ".join(f"(d.content_text ILIKE {like(t)} ESCAPE '!')::int" for t in terms)
        hits = SCOPE_SQL.format(score=f"({count})::float", sid=sid, before=before, where="true")
    return f"""
WITH hits AS ({hits}), rounds AS (
  SELECT theme_id, theme_week_start, max(score) score FROM hits WHERE score > 0
  GROUP BY theme_id, theme_week_start ORDER BY score DESC, theme_week_start DESC, theme_id LIMIT 3)
SELECT r.theme_id, r.theme_week_start, r.score, string_agg(h.attempt_id, ',' ORDER BY h.attempt_id)
FROM rounds r JOIN hits h USING (theme_id, theme_week_start) WHERE h.score > 0
GROUP BY r.theme_id, r.theme_week_start, r.score ORDER BY r.score DESC, r.theme_week_start DESC, r.theme_id"""


def v_search(url: str, token: str, sid: str, query: str) -> tuple[dict, float]:
    req = urllib.request.Request(f"{url.rstrip('/')}/internal/students/{sid}/memories/search",
                                 data=json.dumps({"query": query}).encode(), method="POST")
    for k, v in {"Content-Type": "application/json", "X-Internal-Token": token, "X-User-Role": "STUDENT",
                 "X-User-Id": sid, "X-Student-Scope": sid}.items():
        req.add_header(k, v)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status, payload = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, payload = e.code, e.read()
    ms = (time.perf_counter() - start) * 1000
    if status != 200:
        raise SystemExit(f"검색 API HTTP {status} — 서비스·토큰·학생 ID 확인")
    body = json.loads(payload)
    cards = [{"themeId": c["themeId"], "weekStart": c["weekStart"], "score": c["score"],
              "attemptIds": sorted(m["attemptId"] for m in c.get("missions") or [])} for c in body.get("cards") or []]
    return {"state": body["state"], "cards": cards}, ms


def cmd_collect(args):
    queries, data = load_dataset(pathlib.Path(args.dataset))
    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(KST).date()
    before = week_monday(today).isoformat()
    if before <= data["weeks"]["W7"]:
        raise SystemExit(f"오늘({today}) 기준 진행 주가 W7 이후가 아님 — 평가는 W7 다음 주부터")
    psql = Psql(args.psql)
    sids = {k: v["studentId"] for k, v in manifest["students"].items()}

    # 사전 점검: 평가 학생 문서가 모두 READY인지, 적재 표에 빈 시도 ID가 있으면 학생·테마·주·미션으로 채움
    ids = ",".join(f"'{s}'" for s in sids.values())
    pre = psql.run([("status", f"SELECT status, count(*) FROM memory_search_doc WHERE student_id IN ({ids}) GROUP BY status")])
    status = {r[0]: int(r[1]) for r in pre["status"]}
    if set(status) - {"READY"} and not args.allow_not_ready:
        raise SystemExit(f"READY 아닌 검색 문서가 있음 {status} — 1분 주기 작업을 기다리거나 FAILED 원인 확인")
    themes = manifest["themes"]
    missing = [r for r in manifest["attempts"] if not r["attemptId"] and r["themeKey"]]
    if missing:
        blocks = [(str(i), f"""SELECT id::text FROM attempt WHERE student_id = '{sids[r['studentKey']]}'
            AND theme_id = '{themes[r['themeKey']]['themeId']}' AND theme_week_start = '{themes[r['themeKey']]['weekStart']}'
            AND mission_id = '{r['missionId']}' AND context = 'THEME_DAY'""") for i, r in enumerate(missing)]
        found = psql.run(blocks)
        for i, r in enumerate(missing):
            rows = found.get(str(i)) or []
            if len(rows) != 1:
                raise SystemExit(f"{r['studentKey']} {r['week']} {r['day']} 시도를 하나로 못 찾음({len(rows)}개)")
            r["attemptId"] = rows[0][0]

    raw = {"dataset": "memory@1", "label": args.label, "collectedAt": dt.datetime.now(KST).isoformat(timespec="seconds"),
           "today": today.isoformat(), "before": before, "docStatus": status, "repeats": args.repeats,
           "environment": args.environment, "attempts": manifest["attempts"], "students": manifest["students"],
           "themes": themes, "results": {}}
    # V: 예열 뒤 질문마다 repeats번, 결과는 첫 번째, 시간은 모두
    first = next(q for q in queries if q["category"] != "DELETED")
    for _ in range(args.warmup):
        v_search(args.learning_url, args.token, sids[first["studentKey"]], first["query"])
    for q in queries:
        sid = sids[q["studentKey"]]
        runs = [v_search(args.learning_url, args.token, sid, q["query"]) for _ in range(args.repeats)]
        raw["results"].setdefault(q["queryId"], {})["V"] = {**runs[0][0], "ms": [round(ms, 1) for _, ms in runs]}
    # K1·K2: 한 번에(질문마다 블록)
    for method in ("K1", "K2"):
        blocks = [(q["queryId"], k_sql(method, sids[q["studentKey"]], before, q["query"])) for q in queries]
        out = psql.run(blocks)
        for q in queries:
            rows = out.get(q["queryId"], [])
            raw["results"][q["queryId"]][method] = {
                "state": "RESULTS" if rows else "NO_RESULTS",
                "cards": [{"themeId": r[0], "weekStart": r[1], "score": float(r[2]), "attemptIds": r[3].split(",")} for r in rows]}
    raw["collectedUntil"] = dt.datetime.now(KST).isoformat(timespec="seconds")
    path = pathlib.Path(args.out or RESULTS / f"memory@1__{args.label}.raw.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"질문 {len(queries)}개 × {METHODS} 모음 → {path}")


# ---------- 계산 ----------
def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    i = (len(values) - 1) * q
    lo, hi = math.floor(i), math.ceil(i)
    return round(values[lo] + (values[hi] - values[lo]) * (i - lo), 1)


def allowed_sets(raw):
    """학생별 허용 시도(W1~W6 완주 THEME_DAY)와 회차 키, 그 밖의 시도는 모두 범위 밖."""
    themes, out = raw["themes"], {}
    for r in raw["attempts"]:
        a = out.setdefault(r["studentKey"], {"attempts": set(), "rounds": set()})
        if r["complete"] and r["context"] == "THEME_DAY":
            a["attempts"].add(r["attemptId"])
            t = themes[r["themeKey"]]
            a["rounds"].add((t["themeId"], t["weekStart"]))
    return out


def gold_keys(q, themes):
    return [(themes[g["themeKey"]]["themeId"], themes[g["themeKey"]]["weekStart"]) for g in q["gold"]]


def judge(q, res, threshold, themes):
    cards = [c for c in res["cards"] if threshold is None or c["score"] >= threshold]
    keys = [(c["themeId"], c["weekStart"]) for c in cards]
    if q["category"] == "DELETED":
        return {"ok": res["state"] == "NO_RECORDS"}
    if q["category"] in REJECT_CATS:
        return {"rejected": not keys}
    gold = gold_keys(q, themes)
    found = [k for k in keys[:3] if k in gold]
    rank = next((i + 1 for i, k in enumerate(keys[:3]) if k in gold), None)
    return {"recall": len(set(found)) / len(gold), "hit1": bool(keys[:1] and keys[0] in gold),
            "mrr": 1 / rank if rank else 0.0,
            "recall_at": {k: len({x for x in keys[:k] if x in gold}) / len(gold) for k in (1, 2, 3)}}


def summarize(qs, raw, method, threshold):
    themes = raw["themes"]
    rs = [judge(q, raw["results"][q["queryId"]][method], threshold, themes) for q in qs]
    res = [r for q, r in zip(qs, rs) if q["category"] in RESULT_CATS]
    rej = [r for q, r in zip(qs, rs) if q["category"] in REJECT_CATS]
    rec_k = sum(r["recall"] for r in res)
    out = {"threshold": threshold, "nResults": len(res), "nReject": len(rej),
           "recall@3": round(rec_k / len(res), 3) if res else None,
           "recall@3_ci": wilson(round(rec_k), len(res)),
           "hit@1": round(sum(r["hit1"] for r in res) / len(res), 3) if res else None,
           "mrr@3": round(sum(r["mrr"] for r in res) / len(res), 3) if res else None,
           "recall@k": {k: round(sum(r["recall_at"][k] for r in res) / len(res), 3) for k in (1, 2, 3)} if res else None,
           "reject": round(sum(r["rejected"] for r in rej) / len(rej), 3) if rej else None,
           "reject_ci": wilson(sum(r["rejected"] for r in rej), len(rej)),
           "byCategory": {}}
    for cat in sorted({q["category"] for q in qs}):
        part = [(q, r) for q, r in zip(qs, rs) if q["category"] == cat]
        key = "recall" if cat in RESULT_CATS else ("rejected" if cat in REJECT_CATS else "ok")
        out["byCategory"][cat] = {"n": len(part), key: round(sum(float(r[key]) for _, r in part) / len(part), 3)}
    return out


def violations(qs, raw, method, allowed):
    """임계값과 관계없이 돌아온 결과(상위 3회차 전부)에 범위 밖 회차·시도가 있으면 센다."""
    bad = []
    for q in qs:
        res = raw["results"][q["queryId"]][method]
        a = allowed.get(q["studentKey"], {"attempts": set(), "rounds": set()})
        for c in res["cards"]:
            if (c["themeId"], c["weekStart"]) not in a["rounds"] or any(x not in a["attempts"] for x in c["attemptIds"]):
                bad.append(q["queryId"])
                break
    return bad


def cmd_score(args):
    raw = json.loads(pathlib.Path(args.raw).read_text(encoding="utf-8"))
    queries, _ = load_dataset(pathlib.Path(args.dataset))
    checked = [q for q in queries if len(set(q["checkedBy"])) >= args.min_checkers]
    if args.min_checkers and len(checked) < len(queries):
        print(f"정답 확인 {args.min_checkers}명 미만 질문 {len(queries) - len(checked)}개 제외")
    # 실행 주 기록이 없는 학생(열린 서술 문제가 없었음)의 CURRENT 질문은 제외
    current_ok = {r["studentKey"] for r in raw["attempts"] if r["week"] == "CURRENT"}
    used = [q for q in checked if not (q["category"] == "SCOPE" and q["evidence"] == "CURRENT" and q["studentKey"] not in current_ok)]
    dropped_current = len(checked) - len(used)
    tune = [q for q in used if q["split"] == "tune"]
    ev = [q for q in used if q["split"] == "eval"]
    if not tune or not ev:
        raise SystemExit(f"계산할 질문이 없음(조정용 {len(tune)}·평가용 {len(ev)}) — 정답 확인(checkedBy) 또는 --min-checkers 확인")
    allowed = allowed_sets(raw)

    # 기준값 고르기: 조정용만
    def objective(t):
        s = summarize(tune, raw, "V", t)
        return ((s["recall@3"] or 0) + (s["reject"] or 0)) / 2
    if args.as_served:
        # 하이브리드(#682)처럼 learning이 기준값을 이미 적용해 돌려준 결과: 카드 점수는 벡터 점수라 다시 자르면 키워드로 들어온 회차가 빠짐
        best, sweep = None, []
        vt, vname = None, "V@served"
    else:
        best = max(SWEEP, key=lambda t: (round(objective(t), 6), -abs(t - CURRENT_THRESHOLD)))
        sweep = [{"threshold": t, **{k: summarize(tune, raw, "V", t)[k] for k in ("recall@3", "reject")}} for t in SWEEP]
        vt, vname = best, "V@chosen"

    report = {"dataset": raw["dataset"], "label": raw["label"], "collectedAt": raw["collectedAt"],
              "environment": raw.get("environment"), "today": raw["today"], "docStatus": raw["docStatus"],
              "minCheckers": args.min_checkers, "queriesUsed": len(used), "droppedUnchecked": len(queries) - len(checked),
              "droppedCurrentMissing": dropped_current, "chosenThreshold": best, "tuneSweep": sweep,
              "asServed": args.as_served,
              "tune": {vname: summarize(tune, raw, "V", vt), **({} if args.as_served else {"V@0.35": summarize(tune, raw, "V", CURRENT_THRESHOLD)})},
              "eval": {vname: summarize(ev, raw, "V", vt), **({} if args.as_served else {"V@0.35": summarize(ev, raw, "V", CURRENT_THRESHOLD)}),
                       "K1": summarize(ev, raw, "K1", None), "K2": summarize(ev, raw, "K2", None)},
              "deleted": {m: summarize([q for q in used if q["split"] == "deleted"], raw, m, None)["byCategory"] for m in ("V",)},
              "violations": {m: violations(used, raw, m, allowed) for m in METHODS}}
    ms = [x for q in used for x in raw["results"][q["queryId"]]["V"]["ms"]]
    report["latencyMs"] = {"n": len(ms), "p50": percentile(ms, 0.5), "p95": percentile(ms, 0.95), "max": max(ms) if ms else None,
                           "repeats": raw["repeats"], "note": "learning 내부 API 순차 호출, 질문 임베딩 포함, core·브라우저 제외"}
    e = report["eval"]
    v = e[vname]
    k_best = max(e["K1"]["recall@3"] or 0, e["K2"]["recall@3"] or 0)
    report["criteria"] = {
        "recall@3 ≥ 0.80": (v["recall@3"] or 0) >= CRITERIA["recall"],
        "V − max(K1,K2) ≥ 0.10": (v["recall@3"] or 0) - k_best >= CRITERIA["gap"],
        "reject ≥ 0.80": (v["reject"] or 0) >= CRITERIA["reject"],
        "violations = 0": all(not report["violations"][m] for m in METHODS),
        "p95 ≤ 2000ms": (report["latencyMs"]["p95"] or 1e9) <= CRITERIA["p95_ms"],
        "explanation (human)": "별도 표시지로 판정",
    }
    path = pathlib.Path(args.out or pathlib.Path(args.raw).with_name(pathlib.Path(args.raw).name.replace(".raw.json", ".json")))
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{'돌려준 그대로(기준값 안 고름)' if args.as_served else f'고른 기준값 {best}'} (조정용 {len(tune)}개) · 평가용 {len(ev)}개")
    for name, s in [(vname, v), *([] if args.as_served else [("V@0.35", e["V@0.35"])]), ("K1", e["K1"]), ("K2", e["K2"])]:
        print(f"  {name:8} Recall@3 {s['recall@3']} {s['recall@3_ci']} · Hit@1 {s['hit@1']} · MRR {s['mrr@3']} · 거절 {s['reject']} {s['reject_ci']}")
    print(f"  범위 위반 { {m: len(x) for m, x in report['violations'].items()} } · p95 {report['latencyMs']['p95']}ms")
    for k, ok in report["criteria"].items():
        print(f"  {'통과' if ok is True else ('미달' if ok is False else '-')} {k}")
    print(f"→ {path}")


def cmd_usage(args):
    out = Psql(args.psql).run([("u", f"""SELECT count(*), coalesce(sum(input_tokens), 0) FROM llm_usage
        WHERE call_type = 'MEMORY_EMBEDDING' AND occurred_at BETWEEN {sql_text(args.since)} AND {sql_text(args.until)}""")])
    calls, tokens = out["u"][0]
    print(f"MEMORY_EMBEDDING {args.since} ~ {args.until}: 호출 {calls}회, 입력 토큰 {tokens} (같은 시간 다른 사용이 섞였는지 확인)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("collect")
    p.add_argument("--dataset", default=str(DATASET))
    p.add_argument("--manifest", default=str(RESULTS / "load-manifest.json"))
    p.add_argument("--learning-url", required=True)
    p.add_argument("--token", required=True, help="learning 내부 토큰(출력하지 않음)")
    p.add_argument("--psql", required=True, help="learning_db에 붙는 psql 명령(읽기 전용으로 씀)")
    p.add_argument("--label", required=True)
    p.add_argument("--environment", default="kind", help="결과에 같이 남길 측정 환경 설명")
    p.add_argument("--today", help="진행 주 계산 기준 날짜(기본 KST 오늘, learning 시계와 같아야 함)")
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--allow-not-ready", action="store_true")
    p.add_argument("--out")
    p = sub.add_parser("score")
    p.add_argument("--raw", required=True)
    p.add_argument("--dataset", default=str(DATASET))
    p.add_argument("--min-checkers", type=int, default=1, help="정답 확인 사람 수 하한(0이면 모두 사용, 시험용)")
    p.add_argument("--as-served", action="store_true",
                   help="learning이 서비스 기준값으로 돌려준 결과를 그대로 채점(하이브리드 #682). 조정용으로 기준값을 고르지 않음")
    p.add_argument("--out")
    p = sub.add_parser("usage")
    p.add_argument("--psql", required=True, help="core_db에 붙는 psql 명령")
    p.add_argument("--since", required=True)
    p.add_argument("--until", required=True)
    args = ap.parse_args()
    {"collect": cmd_collect, "score": cmd_score, "usage": cmd_usage}[args.cmd](args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
