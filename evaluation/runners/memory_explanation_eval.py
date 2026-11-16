"""추억 설명 평가 (#568, 기준안 retention-expansion.md 17.2 "추억 설명"). 평가용(초5) 결과 카드로 설명 20건을 만들고 사람이 표시한다.

순서: 검색 평가(memory_search_eval.py collect)가 끝난 뒤, learning 기준값을 0.35로 되돌리고 ai를 실제 LLM으로 띄운 상태에서
    # 1) 모으기: 표시지 CSV(근거 답·설명 원문 있음 → 커밋·공유 금지, 결과 정리 뒤 지움)
    python -I evaluation/runners/memory_explanation_eval.py collect --learning-url http://127.0.0.1:8081 --token $T \
        --psql "<learning_db psql>" --label pc-1117
    # 2) 표시지의 표시 칸을 채운 뒤 숫자만 요약(결과서용)
    python -I evaluation/runners/memory_explanation_eval.py summarize --sheet evaluation/results/memory/memory@1__pc-1117.explain-sheet.csv --checker 수빈

고르는 규칙(실행 전에 고정): 평가용 질문 중 결과가 있어야 하는 질문(TITLE·PARAPHRASE·ANSWER·MULTI)을 질문 ID 순으로 서비스 검색 API에
보내고, 카드가 나온 질문만 1위 카드 미션 앞 3개(API 순서 = 점수 순)로 설명을 요청한다. 20건이 차면 멈춘다.
core를 거치지 않고 learning 내부 API를 부른다(하루 한도 밖). 토큰·키는 출력하지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # python -I는 스크립트 폴더를 경로에 넣지 않음
import memory_search_eval as M  # noqa: E402

MARKS = ["근거 일치(O/X)", "근거 밖 활동(0/1)", "감정 추정(0/1)", "의도 추정(0/1)", "능력 추정(0/1)", "메모"]
EVIDENCE_SQL = """
SELECT json_build_object('attempt', a.id, 'week', a.theme_week_start, 'title', tv.title, 'question', mv.question,
  'answer', ans.plain_text)::text
FROM attempt a JOIN mission_version mv ON mv.id = a.mission_version_id
JOIN theme_frame f ON f.student_id = a.student_id AND f.theme_id = a.theme_id AND f.theme_week_start = a.theme_week_start
JOIN weekly_theme_version tv ON tv.id = f.theme_version_id
JOIN LATERAL (SELECT plain_text FROM answer WHERE attempt_id = a.id ORDER BY version DESC LIMIT 1) ans ON true
WHERE a.id IN ({ids})
"""


def post(url, token, sid, path, body, timeout=90):
    req = urllib.request.Request(f"{url.rstrip('/')}/internal/students/{sid}/memories/{path}",
                                 data=json.dumps(body).encode(), method="POST")
    for k, v in {"Content-Type": "application/json", "X-Internal-Token": token, "X-User-Role": "STUDENT",
                 "X-User-Id": sid, "X-Student-Scope": sid}.items():
        req.add_header(k, v)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, payload = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, payload = e.code, e.read()
    return status, (json.loads(payload) if payload else {}), round((time.perf_counter() - start) * 1000, 1)


def cmd_collect(args):
    queries, _ = M.load_dataset(pathlib.Path(args.dataset))
    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    sids = {k: v["studentId"] for k, v in manifest["students"].items()}
    targets = [q for q in queries if q["split"] == "eval" and q["category"] in M.RESULT_CATS]
    psql = M.Psql(args.psql)
    rows, searched = [], 0
    for q in targets:
        if len(rows) >= args.n:
            break
        sid = sids[q["studentKey"]]
        status, body, _ = post(args.learning_url, args.token, sid, "search", {"query": q["query"]})
        if status != 200:
            raise SystemExit(f"{q['queryId']} 검색 HTTP {status} — 서비스·토큰 확인")
        searched += 1
        cards = body.get("cards") or []
        low = [c["score"] for c in cards if c["score"] < args.threshold - 1e-9]
        if low:
            raise SystemExit(f"{q['queryId']} 카드 점수 {min(low):.3f} < {args.threshold} — learning 기준값이 {args.threshold}인지 확인"
                             "(검색 평가 때 -1로 바꿨다면 되돌리기)")
        if not cards:
            continue
        ids = [m["attemptId"] for m in cards[0]["missions"]][:3]
        status, exp, ms = post(args.learning_url, args.token, sid, "explanations", {"query": q["query"], "attemptIds": ids})
        state = exp.get("state") if status == 200 else ("AI_UNAVAILABLE" if status == 503 else f"HTTP_{status}")
        ev = {json.loads(r[0])["attempt"]: json.loads(r[0]) for r in
              psql.run([("e", EVIDENCE_SQL.format(ids=",".join(f"'{i}'" for i in ids)))])["e"]}
        evidence = "\n\n".join(f"[{n}] {ev[i]['week']} {ev[i]['title']}\n질문: {ev[i]['question']}\n답: {ev[i]['answer']}"
                               for n, i in enumerate(ids, 1))
        cites = ",".join(str(c["no"]) for c in exp.get("citations") or []) if status == 200 else ""
        rows.append({"번호": len(rows) + 1, "queryId": q["queryId"], "종류": q["category"], "질문": q["query"],
                     "1위 카드 주": cards[0]["weekStart"], "1위 점수": round(cards[0]["score"], 3),
                     "정답 카드인지": (cards[0]["themeId"], cards[0]["weekStart"]) in M.gold_keys(q, manifest["themes"]),
                     "근거(번호·주·테마·질문·답)": evidence, "상태": state, "설명": exp.get("text") or "", "인용 번호": cites,
                     "시간 ms": ms, **{m: "" for m in MARKS}})
        print(f"  {len(rows):2}. {q['queryId']} {q['category']:10} 근거 {len(ids)}개 → {state} ({ms}ms)")
    out = pathlib.Path(args.out or M.RESULTS / f"memory@1__{args.label}.explain-sheet.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["번호"])
        w.writeheader()
        w.writerows(rows)
    print(f"검색 {searched}개 중 카드 나온 질문 {len(rows)}개로 설명 요청 → {out}")
    print("표시지에 근거 답·설명 원문이 있음: 커밋·공유하지 말고, summarize 뒤 지우기")


def flag(v, name, no):
    v = (v or "").strip().upper()
    if v not in {"0", "1", "O", "X"}:
        raise SystemExit(f"{no}번 '{name}' 칸이 비었거나 값이 이상함({v!r})")
    return v in {"1", "O"}


def cmd_summarize(args):
    with pathlib.Path(args.sheet).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    states = {}
    for r in rows:
        states[r["상태"]] = states.get(r["상태"], 0) + 1
    gen = [r for r in rows if r["상태"] == "GENERATED"]
    marks = {m: 0 for m in MARKS[:5]}
    for r in gen:
        for m in MARKS[:5]:
            marks[m] += flag(r[m], m, r["번호"])
    bad = marks["근거 밖 활동(0/1)"] + marks["감정 추정(0/1)"] + marks["의도 추정(0/1)"] + marks["능력 추정(0/1)"]
    ms = [float(r["시간 ms"]) for r in rows]
    report = {"dataset": "memory@1", "sheet": pathlib.Path(args.sheet).name, "checker": args.checker,
              "summarizedAt": dt.datetime.now(M.KST).isoformat(timespec="seconds"),
              "requests": len(rows), "states": states, "generated": len(gen),
              "topCardIsGold": sum(r["정답 카드인지"] == "True" for r in rows),
              "marks": {"근거 일치": marks["근거 일치(O/X)"], "근거 밖 활동": marks["근거 밖 활동(0/1)"],
                        "감정 추정": marks["감정 추정(0/1)"], "의도 추정": marks["의도 추정(0/1)"], "능력 추정": marks["능력 추정(0/1)"]},
              "criteria": {"근거 밖 활동·추정 0건": bad == 0},
              "latencyMs": {"p50": M.percentile(ms, 0.5), "p95": M.percentile(ms, 0.95), "max": max(ms) if ms else None,
                            "note": "learning 내부 API, 질문 임베딩·LLM 생성 포함"}}
    out = pathlib.Path(args.out or pathlib.Path(args.sheet).with_name(pathlib.Path(args.sheet).name.replace(".explain-sheet.csv", ".explain.json")))
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"설명 요청 {len(rows)}건 · 상태 {states} · 표시한 생성 {len(gen)}건")
    print(f"  근거 일치 {marks['근거 일치(O/X)']}/{len(gen)} · 근거 밖 활동·추정 {bad}건 → {'통과' if bad == 0 else '미달'}")
    print(f"→ {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("collect")
    p.add_argument("--dataset", default=str(M.DATASET))
    p.add_argument("--manifest", default=str(M.RESULTS / "load-manifest.json"))
    p.add_argument("--learning-url", required=True)
    p.add_argument("--token", required=True, help="learning 내부 토큰(출력하지 않음)")
    p.add_argument("--psql", required=True, help="learning_db psql 명령(근거 표시용, 읽기 전용)")
    p.add_argument("--label", required=True)
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--threshold", type=float, default=M.CURRENT_THRESHOLD, help="learning 기준값(이보다 낮은 카드가 오면 멈춤)")
    p.add_argument("--out")
    p = sub.add_parser("summarize")
    p.add_argument("--sheet", required=True)
    p.add_argument("--checker", required=True, help="표시한 사람")
    p.add_argument("--out")
    args = ap.parse_args()
    {"collect": cmd_collect, "summarize": cmd_summarize}[args.cmd](args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
