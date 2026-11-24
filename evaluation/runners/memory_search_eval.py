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

memory@2(#853, 18.5): --dataset evaluation/datasets/memory@2로 모으고(--today는 평가셋 evalToday가 기본), 하이브리드는
collect --capture-period --ai-url --ai-token으로 질문마다 ai 질의 변환을 한 번 더 불러 해석 기간을 남긴다(원인 분류용).
score는 조정용 나누기가 없어 V를 --threshold(기본 0.35)로 채점하고, 기간 섞임 지표(카드 섞임 비율·질문 단위 섞임 발생률·
경계 카드 비율·원인)를 방식별·기록 수(학생 풀이 주 수)별로 더한다. 회차 주 월~금 중 질문 기간 안 날이 3일 이상이면 기간 안,
1~2일이면 경계(섞임에서 뺌), 0일이면 섞임.

#878 뒤 learning은 기간을 말한 질문의 질의 변환이 끝내 실패하면 503 AI_UNAVAILABLE을 돌려준다.
모으기는 멈추지 않고 그 질문을 state UNAVAILABLE(카드 없음)로 남기고,
채점은 결과 질문 Recall 0·기록 없음 질문 거절 실패로 세며 건수(unavailable)를 따로 낸다.
해석 기간 수집은 키워드 개수(keywordCount, 원문 없음)도 남겨 기간만 질문 판정(#879)을 확인한다.

토큰·비밀번호는 출력하지 않는다. 결과 파일에는 질문 ID·회차 키·시도 ID·점수·시간·해석 기간만 남는다.
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
CRITERIA = {"recall": 0.80, "gap": 0.10, "reject": 0.80, "violations": 0, "p95_ms": 2000, "mix_queries": 0.10}


# ---------- 공통 ----------
def load_dataset(folder: pathlib.Path):
    queries = [json.loads(x) for x in (folder / "queries.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    students = json.loads((folder / "students.json").read_text(encoding="utf-8"))
    return queries, students


def week_monday(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.isoweekday() - 1)


def kind(q) -> str:
    """채점 갈래: result(정답 회차 찾기)·reject(NO_RESULTS)·deleted. memory@2 기간 질문은 학생 기록에 따라 expect로 정한다."""
    if q["category"] == "DELETED":
        return "deleted"
    if "period" in q:
        return "result" if q["expect"] == "RESULTS" else "reject"
    return "result" if q["category"] in RESULT_CATS else ("reject" if q["category"] in REJECT_CATS else "other")


def weekdays_in(week_start: str, period) -> int:
    """회차 주 월~금 중 반열림 기간 [from, to) 안에 든 날 수(check_dataset.weekdays_in과 같은 규칙)"""
    s, f, t = (dt.date.fromisoformat(x) for x in (week_start, period["from"], period["to"]))
    return sum(f <= s + dt.timedelta(days=i) < t for i in range(5))


def overlaps(week_start: str, period) -> bool:
    """서비스 기간 필터(16.3)와 같은 겹침: 회차 주 [월요일, +7일)과 기간이 하루라도 겹침(주말 포함).
    #879 기간만 질문 경로는 월~금 중 1일 이상만 넣어 이보다 좁으므로
    "필터 누락" 판정에는 이 넓은 규칙을 그대로 쓴다(16.9)"""
    s = dt.date.fromisoformat(week_start)
    return dt.date.fromisoformat(period["from"]) < s + dt.timedelta(days=7) and s < dt.date.fromisoformat(period["to"])


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
    # #878: 기간 질문의 질의 변환 실패 안내(임베딩 장애도 같은 코드). 멈추지 않고 기록
    if status == 503:
        return {"state": "UNAVAILABLE", "cards": []}, ms
    if status != 200:
        raise SystemExit(f"검색 API HTTP {status} — 서비스·토큰·학생 ID 확인")
    body = json.loads(payload)
    cards = [{"themeId": c["themeId"], "weekStart": c["weekStart"], "score": c["score"],
              "attemptIds": sorted(m["attemptId"] for m in c.get("missions") or [])} for c in body.get("cards") or []]
    return {"state": body["state"], "cards": cards}, ms


def ai_period(url: str, token: str, query: str, today: str):
    """ai 질의 변환(api-spec 4.2.7)을 learning 호출자 토큰으로 직접 불러 해석 기간과 키워드 개수만 돌려준다.

    원인 분류용이고 검색 때 호출과 별개다. 키워드 원문은 남기지 않는다.
    실패하면 {"error": HTTP 상태}. 질문은 합성 평가셋 그대로(닉네임 없음).
    """
    req = urllib.request.Request(f"{url.rstrip('/')}/internal/memory-queries", method="POST",
                                 data=json.dumps({"query": query, "today": today}).encode())
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Internal-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read())
            return {"period": body.get("period"), "keywordCount": len(body.get("keywords") or [])}
    except urllib.error.HTTPError as e:
        return {"error": e.code}
    except (urllib.error.URLError, TimeoutError):
        return {"error": "connection"}


def cmd_collect(args):
    queries, data = load_dataset(pathlib.Path(args.dataset))
    name = data["dataset"]
    manifest_path = args.manifest or RESULTS / ("load-manifest.json" if name == "memory@1" else f"load-manifest__{name}.json")
    manifest = json.loads(pathlib.Path(manifest_path).read_text(encoding="utf-8"))
    if manifest["dataset"] != name:
        raise SystemExit(f"적재 표가 {manifest['dataset']} 것 — --manifest 확인")
    today = dt.date.fromisoformat(args.today or data.get("evalToday") or dt.datetime.now(KST).date().isoformat())
    before = week_monday(today).isoformat()
    last = list(data["weeks"])[-1]
    if before <= data["weeks"][last]:
        raise SystemExit(f"오늘({today}) 기준 진행 주가 {last} 이후가 아님 — 평가는 {last} 다음 주부터")
    if data.get("evalToday") and today.isoformat() != data["evalToday"]:
        print(f"주의: 기준일 {today}가 평가셋 evalToday {data['evalToday']}와 다름(기간 질문 정답은 evalToday 기준)")
    if args.capture_period and not (args.ai_url and args.ai_token):
        raise SystemExit("--capture-period에는 --ai-url·--ai-token(learning 호출자 토큰)이 필요")
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

    raw = {"dataset": name, "label": args.label, "collectedAt": dt.datetime.now(KST).isoformat(timespec="seconds"),
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
    if args.capture_period:  # 하이브리드 원인 분류: 검색이 끝난 뒤 따로 불러 검색 시간에 섞이지 않게 함
        raw["periods"] = {q["queryId"]: ai_period(args.ai_url, args.ai_token, q["query"], today.isoformat())
                          for q in queries if "period" in q}
        failed = sum("error" in p for p in raw["periods"].values())
        print(f"해석 기간 {len(raw['periods'])}개 모음(실패 {failed})")
    path = pathlib.Path(args.out or RESULTS / f"{name}__{args.label}.raw.json")
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
    unavailable = res["state"] == "UNAVAILABLE"  # 503 안내(#878): 결과도 거절 성공도 아님
    if kind(q) == "deleted":
        return {"ok": res["state"] == "NO_RECORDS", "unavailable": unavailable}
    if kind(q) == "reject":
        return {"rejected": not keys and not unavailable, "unavailable": unavailable}
    gold = gold_keys(q, themes)
    # memory@2 기간만 질문은 정답 회차가 3개보다 많을 수 있어(카드 최대 3) 분모를 min(3, 정답 수)로 둔다
    denom = lambda k: min(k, len(gold)) if "period" in q else len(gold)
    found = [k for k in keys[:3] if k in gold]
    rank = next((i + 1 for i, k in enumerate(keys[:3]) if k in gold), None)
    return {"recall": len(set(found)) / denom(3), "hit1": bool(keys[:1] and keys[0] in gold),
            "unavailable": unavailable,
            "mrr": 1 / rank if rank else 0.0,
            "recall_at": {k: len({x for x in keys[:k] if x in gold}) / denom(k) for k in (1, 2, 3)}}


def summarize(qs, raw, method, threshold):
    themes = raw["themes"]
    rs = [judge(q, raw["results"][q["queryId"]][method], threshold, themes) for q in qs]
    res = [r for q, r in zip(qs, rs) if kind(q) == "result"]
    rej = [r for q, r in zip(qs, rs) if kind(q) == "reject"]
    rec_k = sum(r["recall"] for r in res)
    out = {"threshold": threshold, "nResults": len(res), "nReject": len(rej),
           "recall@3": round(rec_k / len(res), 3) if res else None,
           "recall@3_ci": wilson(round(rec_k), len(res)),
           "hit@1": round(sum(r["hit1"] for r in res) / len(res), 3) if res else None,
           "mrr@3": round(sum(r["mrr"] for r in res) / len(res), 3) if res else None,
           "recall@k": {k: round(sum(r["recall_at"][k] for r in res) / len(res), 3) for k in (1, 2, 3)} if res else None,
           "reject": round(sum(r["rejected"] for r in rej) / len(rej), 3) if rej else None,
           "reject_ci": wilson(sum(r["rejected"] for r in rej), len(rej)),
           "unavailable": sum(r["unavailable"] for r in rs),
           "byCategory": {}}
    for cat in sorted({q["category"] for q in qs}):
        part = [(q, r) for q, r in zip(qs, rs) if q["category"] == cat]
        for key in ("recall", "rejected", "ok"):  # memory@2는 같은 종류에 결과 있음·없음이 섞임
            got = [float(r[key]) for _, r in part if key in r]
            if got:
                out["byCategory"].setdefault(cat, {"n": len(part)})[key] = round(sum(got) / len(got), 3)
    return out


def interpreted(raw, q, before):
    """수집한 해석 기간을 learning 규칙(16.3: to를 진행 주 월요일 이하로 자르고 from < to가 아니면 버림)대로 정리. 없으면 None"""
    got = (raw.get("periods") or {}).get(q["queryId"])
    if not got or "error" in got:
        return "missing"
    p = got.get("period")
    if not p:
        return None
    to = min(p["to"], before)
    return {"from": p["from"], "to": to} if p["from"] < to else None


def mixing(qs, raw, method, threshold, uses_period):
    """기간 질문의 섞임(#853): 카드마다 회차 주 월~금 중 질문 기간 안 날 수로 기간 안(3~5)·경계(1~2)·섞임(0)을 나눈다.
    uses_period(하이브리드)면 섞인 카드마다 원인을 해석 기간과 서비스 겹침 규칙으로 추정한다."""
    qs = [q for q in qs if "period" in q]
    if not qs:
        return None
    cards = out_cards = edge_cards = mixed_queries = 0
    causes, per_query = {}, {}
    for q in qs:
        res = raw["results"][q["queryId"]][method]
        got = [c for c in res["cards"] if threshold is None or c["score"] >= threshold]
        days = [weekdays_in(c["weekStart"], q["period"]) for c in got]
        out = [c for c, n in zip(got, days) if n == 0]
        cards += len(got)
        out_cards += len(out)
        edge_cards += sum(1 <= n <= 2 for n in days)
        mixed_queries += bool(out)
        if out:
            per_query[q["queryId"]] = len(out)
        for c in out:
            if not uses_period:
                cause = "기간 미사용(벡터 유사·키워드 일치)"
            else:
                p = interpreted(raw, q, raw["before"])
                if p == "missing":
                    cause = "해석 기간 미수집"
                elif p is None:
                    cause = "기간 해석 실패(기간 없음)"
                elif not overlaps(c["weekStart"], p):
                    cause = "필터 누락(해석 기간과 안 겹침, 확인 필요)"
                elif p == q["period"]:
                    cause = "겹침 규칙(해석은 맞고 주말·경계로 겹침)"
                else:
                    cause = "기간 해석 다름"
            causes[cause] = causes.get(cause, 0) + 1
    return {"nQueries": len(qs), "cards": cards,
            "cardMixRate": round(out_cards / cards, 3) if cards else None,
            "queryMixRate": round(mixed_queries / len(qs), 3), "queryMixRate_ci": wilson(mixed_queries, len(qs)),
            "boundaryCardRate": round(edge_cards / cards, 3) if cards else None,
            "mixedQueries": mixed_queries, "mixedCards": out_cards, "boundaryCards": edge_cards,
            "causes": causes, "mixedByQuery": per_query}


def period_accuracy(raw, qs):
    """해석 기간이 사람이 정한 기간과 같은 비율(learning 자르기 뒤). 하이브리드 원인 분류의 바탕"""
    got = [interpreted(raw, q, raw["before"]) for q in qs if "period" in q]
    got = [p for p in got if p != "missing"]
    if not got:
        return None
    want = [q["period"] for q in qs if "period" in q and interpreted(raw, q, raw["before"]) != "missing"]
    return {"n": len(got), "exact": round(sum(p == w for p, w in zip(got, want)) / len(got), 3),
            "none": round(sum(p is None for p in got) / len(got), 3)}


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
    queries, data = load_dataset(pathlib.Path(args.dataset))
    if data["dataset"] != raw["dataset"]:
        raise SystemExit(f"raw는 {raw['dataset']}, --dataset은 {data['dataset']} — 같은 평가셋으로")
    checked = [q for q in queries if len(set(q["checkedBy"])) >= args.min_checkers]
    if args.min_checkers and len(checked) < len(queries):
        print(f"정답 확인 {args.min_checkers}명 미만 질문 {len(queries) - len(checked)}개 제외")
    # 실행 주 기록이 없는 학생(열린 서술 문제가 없었음)의 CURRENT 질문은 제외
    current_ok = {r["studentKey"] for r in raw["attempts"] if r["week"] == "CURRENT"}
    used = [q for q in checked if not (q["category"] == "SCOPE" and q["evidence"] == "CURRENT" and q["studentKey"] not in current_ok)]
    dropped_current = len(checked) - len(used)
    tune = [q for q in used if q["split"] == "tune"]
    ev = [q for q in used if q["split"] == "eval"]
    fixed = args.threshold
    if not tune and not args.as_served and fixed is None and any(q.get("split") == "eval" for q in queries) \
            and not any(q.get("split") == "tune" for q in queries):
        fixed = CURRENT_THRESHOLD  # memory@2: 조정용 나누기가 없어 서비스 기준값으로 채점
        print(f"조정용 질문이 없는 평가셋이라 V를 서비스 기준값 {fixed}로 채점(--threshold로 바꿈)")
    if not ev or (not tune and not args.as_served and fixed is None):
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
    elif fixed is not None:
        best, sweep = fixed, []
        vt, vname = fixed, f"V@{fixed}"
    else:
        best = max(SWEEP, key=lambda t: (round(objective(t), 6), -abs(t - CURRENT_THRESHOLD)))
        sweep = [{"threshold": t, **{k: summarize(tune, raw, "V", t)[k] for k in ("recall@3", "reject")}} for t in SWEEP]
        vt, vname = best, "V@chosen"

    report = {"dataset": raw["dataset"], "label": raw["label"], "collectedAt": raw["collectedAt"],
              "environment": raw.get("environment"), "today": raw["today"], "docStatus": raw["docStatus"],
              "minCheckers": args.min_checkers, "queriesUsed": len(used), "droppedUnchecked": len(queries) - len(checked),
              "droppedCurrentMissing": dropped_current, "chosenThreshold": best, "tuneSweep": sweep,
              "asServed": args.as_served,
              "tune": {} if not tune else {vname: summarize(tune, raw, "V", vt), **({} if sweep == [] else {"V@0.35": summarize(tune, raw, "V", CURRENT_THRESHOLD)})},
              "eval": {vname: summarize(ev, raw, "V", vt), **({} if sweep == [] else {"V@0.35": summarize(ev, raw, "V", CURRENT_THRESHOLD)}),
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
    if any("period" in q for q in ev):  # memory@2 기간 섞임(#853, 18.5)
        sizes = {s["studentKey"]: s["weekCount"] * 5 for s in data["students"]}
        runs = [(vname, "V", vt, args.as_served), ("K1", "K1", None, False), ("K2", "K2", None, False)]
        report["mixing"] = {name: mixing(ev, raw, m, t, use) for name, m, t, use in runs}
        report["bySize"] = {}
        for n in sorted(set(sizes.values())):
            part = [q for q in ev if sizes[q["studentKey"]] == n]
            report["bySize"][n] = {name: {**{k: summarize(part, raw, m, t)[k] for k in ("recall@3", "reject", "nResults", "nReject")},
                                          "mixing": mixing(part, raw, m, t, use)} for name, m, t, use in runs}
        report["periodAccuracy"] = period_accuracy(raw, ev)
        if args.as_served:
            report["criteria"]["H 질문 단위 섞임 발생률 ≤ 0.10"] = report["mixing"][vname]["queryMixRate"] <= CRITERIA["mix_queries"]
    path = pathlib.Path(args.out or pathlib.Path(args.raw).with_name(pathlib.Path(args.raw).name.replace(".raw.json", ".json")))
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    how = "돌려준 그대로(기준값 안 고름)" if args.as_served else (f"고른 기준값 {best}" if sweep else f"고정 기준값 {best}")
    print(f"{how} (조정용 {len(tune)}개) · 평가용 {len(ev)}개")
    for name, s in [(vname, v), *([] if not sweep else [("V@0.35", e["V@0.35"])]), ("K1", e["K1"]), ("K2", e["K2"])]:
        print(f"  {name:8} Recall@3 {s['recall@3']} {s['recall@3_ci']} · Hit@1 {s['hit@1']}"
              f" · MRR {s['mrr@3']} · 거절 {s['reject']} {s['reject_ci']}"
              f" · 503 {s['unavailable']}")
    print(f"  범위 위반 { {m: len(x) for m, x in report['violations'].items()} } · p95 {report['latencyMs']['p95']}ms")
    for name, mx in (report.get("mixing") or {}).items():
        print(f"  {name:8} 섞임: 카드 {mx['cardMixRate']} · 질문 {mx['queryMixRate']} {mx['queryMixRate_ci']} · 경계 카드 {mx['boundaryCardRate']} · 원인 {mx['causes']}")
    for n, by in (report.get("bySize") or {}).items():
        print(f"  기록 {n}개: " + " · ".join(f"{name} 질문 섞임 {x['mixing']['queryMixRate']}·Recall {x['recall@3']}" for name, x in by.items()))
    if report.get("periodAccuracy"):
        print(f"  해석 기간: {report['periodAccuracy']}")
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
    p.add_argument("--manifest", help="적재 표(기본 memory@1 load-manifest.json, 그 밖 load-manifest__<평가셋>.json)")
    p.add_argument("--learning-url", required=True)
    p.add_argument("--token", required=True, help="learning 내부 토큰(출력하지 않음)")
    p.add_argument("--psql", required=True, help="learning_db에 붙는 psql 명령(읽기 전용으로 씀)")
    p.add_argument("--label", required=True)
    p.add_argument("--environment", default="kind", help="결과에 같이 남길 측정 환경 설명")
    p.add_argument("--today", help="진행 주 계산 기준 날짜(기본 평가셋 evalToday, 없으면 KST 오늘. learning 시계와 같아야 함)")
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--allow-not-ready", action="store_true")
    p.add_argument("--capture-period", action="store_true", help="기간 질문마다 ai 질의 변환을 따로 불러 해석 기간 저장(하이브리드 원인 분류)")
    p.add_argument("--ai-url", help="ai 주소(--capture-period, 예 http://127.0.0.1:8000)")
    p.add_argument("--ai-token", help="ai가 받는 learning 호출자 토큰 INTERNAL_TOKEN_LEARNING(출력하지 않음)")
    p.add_argument("--out")
    p = sub.add_parser("score")
    p.add_argument("--raw", required=True)
    p.add_argument("--dataset", default=str(DATASET))
    p.add_argument("--min-checkers", type=int, default=1, help="정답 확인 사람 수 하한(0이면 모두 사용, 시험용)")
    p.add_argument("--as-served", action="store_true",
                   help="learning이 서비스 기준값으로 돌려준 결과를 그대로 채점(하이브리드 #682). 조정용으로 기준값을 고르지 않음")
    p.add_argument("--threshold", type=float,
                   help="V 기준값 고정(조정용으로 고르지 않음). 조정용 질문이 없는 평가셋(memory@2)은 기본 0.35")
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
