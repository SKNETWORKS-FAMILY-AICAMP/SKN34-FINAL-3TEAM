"""추억 검색 참고 시험 묶음 (#568, memory@1 본 평가와 따로, 결과서에는 참고로만).

`evaluation/datasets/memory-probe/`의 세 묶음(모두 평가용 초5 학생)
- typo.jsonl: 평가용 질문 12개에 오타를 넣음 → 원래 질문과 나란히 검색해 정답 회차가 카드 3개 안에 남는지
- request.jsonl: 평가용 질문 12개를 아이가 말하듯 요청·구어체("…찾아줘", "그거 있잖아")로 → 원래 질문과 나란히
- period.jsonl: 기간 표현 질문 8개(16장 하이브리드 기간 필터 대상). 정답이 있으면 카드 3개 안, 없으면 NO_RESULTS여야 맞음.
  상대 기간("지지난주")은 실행 주가 2026-11-16 주일 때만 정답이 맞음(`assumesRunWeek`)

learning을 재고 싶은 설정(벡터만 또는 하이브리드, 서비스 기준값 0.35)으로 띄운 뒤 같은 설정에서 돌린다.
learning이 돌려준 결과를 그대로 본다(기준값을 다시 자르지 않음). 결과 파일에는 질문 ID·맞힘·순위·시간만 넣는다.

    python -I evaluation/runners/memory_probe.py --learning-url http://127.0.0.1:8081 --token "$T" --label pc-1117-hybrid
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # python -I는 스크립트 폴더를 경로에 넣지 않음
import memory_search_eval as M  # noqa: E402

PROBE = M.ROOT / "evaluation" / "datasets" / "memory-probe"
PAIRED = ("typo", "request")


def load(name):
    return [json.loads(x) for x in (PROBE / f"{name}.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


def rank(res, gold):
    keys = [(c["themeId"], c["weekStart"]) for c in res["cards"]][:3]
    return next((i + 1 for i, k in enumerate(keys) if k in gold), None)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--learning-url", required=True)
    ap.add_argument("--token", required=True, help="learning 내부 토큰(출력하지 않음)")
    ap.add_argument("--label", required=True)
    ap.add_argument("--manifest", default=str(M.RESULTS / "load-manifest.json"))
    args = ap.parse_args()
    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    sids = {k: v["studentId"] for k, v in manifest["students"].items()}
    src = {q["queryId"]: q for q in M.load_dataset(M.DATASET)[0]}
    today = dt.datetime.now(M.KST).date()
    report = {"dataset": "memory@1-probe", "label": args.label, "at": dt.datetime.now(M.KST).isoformat(timespec="seconds"),
              "note": "learning이 돌려준 그대로(서비스 기준값). 본 평가 숫자와 섞지 않는 참고 시험", "sets": {}}
    search = lambda sk, text: M.v_search(args.learning_url, args.token, sids[sk], text)  # noqa: E731
    for name in PAIRED:
        rows = []
        for p in load(name):
            q = src[p["source"]]
            gold = M.gold_keys(q, manifest["themes"])
            (orig, ms_o), (var, ms_v) = search(q["studentKey"], q["query"]), search(q["studentKey"], p["query"])
            rows.append({"queryId": p["queryId"], "source": p["source"], "category": q["category"],
                         "originalRank": rank(orig, gold), "variantRank": rank(var, gold), "ms": [round(ms_o, 1), round(ms_v, 1)]})
            print(f"  {name} {p['queryId']} 원래 {rows[-1]['originalRank'] or '-'} · 바꾼 질문 {rows[-1]['variantRank'] or '-'}")
        report["sets"][name] = {"n": len(rows), "originalHit@3": sum(r["originalRank"] is not None for r in rows),
                                "variantHit@3": sum(r["variantRank"] is not None for r in rows),
                                "lost": [r["queryId"] for r in rows if r["originalRank"] and not r["variantRank"]],
                                "gained": [r["queryId"] for r in rows if r["variantRank"] and not r["originalRank"]], "rows": rows}
    rows = []
    for p in load("period"):
        res, ms = search(p["studentKey"], p["query"])
        if p["expect"] == "RESULTS":
            r = rank(res, M.gold_keys(p, manifest["themes"]))
            ok = r is not None
        else:
            r, ok = None, not res["cards"]
        rows.append({"queryId": p["queryId"], "expect": p["expect"], "state": res["state"], "rank": r, "ok": ok,
                     "cards": len(res["cards"]), "ms": round(ms, 1)})
        print(f"  period {p['queryId']} 기대 {p['expect']} → {res['state']}·카드 {len(res['cards'])} {'맞음' if ok else '틀림'}")
    weeks = {p["assumesRunWeek"] for p in load("period")}
    report["sets"]["period"] = {"n": len(rows), "ok": sum(r["ok"] for r in rows), "rows": rows,
                                "runWeekMatches": M.week_monday(today).isoformat() in weeks}
    out = M.RESULTS / f"memory@1-probe__{args.label}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    s = report["sets"]
    print(f"오타 {s['typo']['originalHit@3']}→{s['typo']['variantHit@3']}/{s['typo']['n']} · "
          f"요청 말투 {s['request']['originalHit@3']}→{s['request']['variantHit@3']}/{s['request']['n']} · "
          f"기간 {s['period']['ok']}/{s['period']['n']} 맞음"
          + ("" if s["period"]["runWeekMatches"] else " (실행 주가 기간 질문 기준 주와 달라 기간 정답이 안 맞을 수 있음)") + f" → {out}")


if __name__ == "__main__":
    main()
