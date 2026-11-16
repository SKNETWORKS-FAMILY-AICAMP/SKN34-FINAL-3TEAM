"""추억 검색 하이브리드 흉내 실험 (#568 → #679 설계 참고). 조정용(초3) 학생만 쓴다.

#679 기준안(질문 → LLM 변환 {keywords, period, searchText} → 벡터(기준값 통과분) + 키워드(content_text ILIKE, 하나 이상 일치)
+ 기간 필터 → 회차 순위 RRF(k=60) → 상위 3)을 구현 전에 오프라인으로 흉내 내 방식별로 비교한다.
- 서비스 코드·DB는 바꾸지 않는다(learning_db 읽기 전용). 변환·임베딩은 이 스크립트가 OpenAI에 직접 요청
- 변환 지시문은 이 실험용 임시안이다(#681 프롬프트가 아님). 변환 결과는 캐시 파일에 남겨 다시 돌려도 같은 값을 쓴다
- 평가용(초5) 학생은 읽지 않는다. 결과 파일에는 숫자만(변환 캐시에는 질문에서 뽑은 낱말이 있어 커밋하지 않음)
- 가정: RRF는 회차 단위 순위(벡터 = 회차 최고 유사도, 키워드 = 회차 문서 중 가장 많이 맞은 키워드 수), 동점은 주 내림·테마

    python -I evaluation/runners/memory_hybrid_exp.py --psql "<learning_db psql>"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # python -I는 스크립트 폴더를 경로에 넣지 않음
import memory_doc_variant_exp as D  # noqa: E402
import memory_search_eval as M  # noqa: E402

DOC_SQL = """
SELECT json_build_object('sid', d.student_id, 'theme', d.theme_id, 'week', d.theme_week_start, 'text', d.content_text,
  'title', tv.title, 'answer', ans.plain_text)::text
FROM memory_search_doc d JOIN attempt a ON a.id = d.attempt_id
JOIN theme_frame f ON f.student_id = d.student_id AND f.theme_id = d.theme_id AND f.theme_week_start = d.theme_week_start
JOIN weekly_theme t ON t.id = a.theme_id
JOIN weekly_theme_version tv ON tv.id = coalesce(t.published_version_id, t.current_version_id)
JOIN LATERAL (SELECT plain_text FROM answer WHERE attempt_id = a.id ORDER BY version DESC LIMIT 1) ans ON true
WHERE d.student_id IN ({ids}) AND a.student_id = d.student_id AND d.theme_week_start < '{before}' AND d.status = 'READY'
  AND a.context IN ('THEME_DAY','THEME_REVIEW') AND a.completed_at IS NOT NULL
"""
REWRITE_SYSTEM = """너는 초등학생이 자기 지난 학습 기록(추억)을 찾으려고 쓴 질문을 검색용으로 바꾼다. 오늘은 {today}(KST)이다.
- keywords: 질문에 있는 핵심 낱말 최대 5개. 조사·어미는 뗀다. '했던', '거', '이야기', '문제', '찾아줘'처럼 어느 기록에나 맞는 말은 넣지 않는다
- period: '지난주', '지난달', '3주 전', '10월'처럼 때를 말한 경우에만 오늘 기준 날짜 구간 from·to(YYYY-MM-DD, to는 포함하지 않음). 없으면 null
- searchText: 기록 내용과 비교하기 좋은 검색용 한 문장. 질문에 없는 내용을 더하지 않는다"""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["keywords", "period", "searchText"],
          "properties": {"keywords": {"type": "array", "items": {"type": "string"}},
                         "period": {"anyOf": [{"type": "null"}, {"type": "object", "additionalProperties": False,
                                                                 "required": ["from", "to"],
                                                                 "properties": {"from": {"type": "string"}, "to": {"type": "string"}}}]},
                         "searchText": {"type": "string"}}}
MODELS = ("text-embedding-3-small", "text-embedding-3-large")
SWEEP = [round(0.10 + 0.01 * i, 2) for i in range(61)]


def rewrite(key, model, today, query, max_tokens=256, effort=None):
    body = {"model": model, "max_completion_tokens": max_tokens,
            "messages": [{"role": "system", "content": REWRITE_SYSTEM.format(today=today)}, {"role": "user", "content": query}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "MemoryQuery", "schema": SCHEMA, "strict": True}}}
    if effort:
        body["reasoning_effort"] = effort
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(), method="POST")
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", "application/json")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        out = json.loads(data["choices"][0]["message"]["content"])
        out["keywords"] = [k.strip() for k in out["keywords"] if k.strip()][:5]
        ok = bool(out["searchText"].strip())
        usage = data.get("usage") or {}
        return {**out, "ok": ok, "ms": round((time.perf_counter() - start) * 1000, 1),
                "inTokens": usage.get("prompt_tokens"), "outTokens": usage.get("completion_tokens")}
    except (urllib.error.URLError, KeyError, ValueError, TypeError) as e:
        code = getattr(e, "code", None)
        return {"ok": False, "error": f"HTTP {code}" if code else type(e).__name__, "ms": round((time.perf_counter() - start) * 1000, 1)}


def in_period(week, period, before):
    """learning이 할 보정을 흉내: from<to, 지난 주 범위로 자름. 이상하면 기간 없음"""
    if not period:
        return True
    try:
        f, t = dt.date.fromisoformat(period["from"]), dt.date.fromisoformat(period["to"])
    except (KeyError, ValueError, TypeError):
        return True
    t = min(t, dt.date.fromisoformat(before))
    if f >= t:
        return True
    return f <= dt.date.fromisoformat(week) < t


def order(scores):
    return sorted(scores, key=lambda k: (-scores[k], -dt.date.fromisoformat(k[1]).toordinal(), k[0]))


def cards(keys, scores):
    keys = keys[:3]
    return {"state": "RESULTS" if keys else "NO_RESULTS",
            "cards": [{"themeId": k[0], "weekStart": k[1], "score": scores.get(k, 0.0), "attemptIds": []} for k in keys]}


def rrf(*ranked):
    s = {}
    for lst in ranked:
        for i, k in enumerate(lst):
            s[k] = s.get(k, 0.0) + 1 / (60 + i + 1)
    return order(s), s


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--psql", required=True)
    ap.add_argument("--llm-model", default="gpt-6-luna", help="ai 기본 LLM과 같게")
    ap.add_argument("--large-dimensions", type=int, default=1536, help="large 임베딩 차원(기본 3072, 서비스 DB는 1536)")
    ap.add_argument("--max-tokens", type=int, default=256, help="변환 출력 상한(#679 기준안 256)")
    ap.add_argument("--reasoning-effort", help="변환 추론 설정(예: minimal·low). 없으면 보내지 않음")
    ap.add_argument("--dataset", default=str(M.DATASET))
    ap.add_argument("--manifest", default=str(M.RESULTS / "load-manifest.json"))
    ap.add_argument("--cache", default=str(M.RESULTS / "hybrid-rewrites__tune.json"), help="변환 결과 캐시(커밋 안 함)")
    ap.add_argument("--today")
    ap.add_argument("--out", default=str(M.RESULTS / "hybrid-exp__tune.json"))
    args = ap.parse_args()
    key = os.environ.get("EVAL_OPENAI_API_KEY") or sys.exit("환경 변수 EVAL_OPENAI_API_KEY가 없음")

    queries, _ = M.load_dataset(pathlib.Path(args.dataset))
    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    themes = manifest["themes"]
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(M.KST).date()
    before = M.week_monday(today).isoformat()
    current_ok = {r["studentKey"] for r in manifest["attempts"] if r["week"] == "CURRENT"}
    tune = [q for q in queries if q["split"] == "tune"
            and not (q["category"] == "SCOPE" and q["evidence"] == "CURRENT" and q["studentKey"] not in current_ok)]
    sids = {k: manifest["students"][k]["studentId"] for k in sorted({q["studentKey"] for q in tune})}
    rows = M.Psql(args.psql).run([("d", DOC_SQL.format(ids=",".join(f"'{s}'" for s in sids.values()), before=before))])["d"]
    docs = [json.loads(r[0]) for r in rows]
    own = {}
    for d in docs:
        own.setdefault(d["sid"], []).append(d)
    print(f"조정용 학생 {list(sids)} · 문서 {len(docs)}개 · 질문 {len(tune)}개")

    # 1) 변환(캐시)
    cache_path = pathlib.Path(args.cache)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    for q in tune:
        if q["queryId"] not in cache or not cache[q["queryId"]].get("ok"):
            cache[q["queryId"]] = rewrite(key, args.llm_model, today.isoformat(), q["query"], args.max_tokens, args.reasoning_effort)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    rw = {q["queryId"]: cache[q["queryId"]] for q in tune}
    ok = [r for r in rw.values() if r.get("ok")]
    ms = [r["ms"] for r in rw.values()]
    fails = [r.get("error") for r in rw.values() if not r.get("ok")]
    print(f"변환 {len(ok)}/{len(rw)} 성공(실패 이유 {fails}) · 기간 나온 질문 {sum(bool(r.get('period')) for r in ok)}개 · "
          f"지연 p50 {M.percentile(ms, 0.5)}ms p95 {M.percentile(ms, 0.95)}ms · "
          f"토큰 입력 {sum(r.get('inTokens') or 0 for r in ok)} 출력 {sum(r.get('outTokens') or 0 for r in ok)}")

    # 2) 임베딩(모델별)
    sims = {}
    for model in MODELS:
        emb = D.Embedder(key, model, args.large_dimensions if model.endswith("large") else 1536)
        texts = [d["text"] for d in docs] + [q["query"] for q in tune] + [r["searchText"] for r in ok]
        emb.add(texts)
        for q in tune:
            r = rw[q["queryId"]]
            for kind, text in (("orig", q["query"]), ("rw", r["searchText"] if r.get("ok") else q["query"])):
                v = emb[text]
                per = {}
                for d in own.get(sids[q["studentKey"]], []):
                    k = (d["theme"], d["week"])
                    per[k] = max(D.cos(v, emb[d["text"]]), per.get(k, -2.0))
                sims[(model, kind, q["queryId"])] = per
        print(f"  {model} 임베딩 토큰 {emb.tokens}")

    # 3) 키워드 회차 순위(변환 키워드, 기간 필터). where = 찾는 곳: 문서 전체(content_text) 또는 제목+답만
    def keyword_rounds(where):
      out = {}
      for q in tune:
        r = rw[q["queryId"]] if where != "raw" else {"ok": True, "keywords": M.query_terms(q["query"]), "period": None}
        words = [w.lower() for w in r.get("keywords", [])] if r.get("ok") else []
        per = {}
        for d in own.get(sids[q["studentKey"]], []):
            if not in_period(d["week"], r.get("period") if r.get("ok") else None, before):
                continue
            hay = d["text"] if where == "all" else f"{d['title']}\n{d['answer'] or ''}"
            n = sum(w in hay.lower() for w in words)
            if n:
                k = (d["theme"], d["week"])
                per[k] = max(n, per.get(k, 0))
        out[q["queryId"]] = per
      return out
    kw = keyword_rounds("all")
    kw_ta = keyword_rounds("title+answer")
    kw_raw = keyword_rounds("raw")  # LLM 없이: 질문 낱말(2자 이상, 끝 조사 1개 뗌 = K2와 같은 규칙), 문서 전체에서

    def method(name, model, t):
        res = {}
        for q in tune:
            r = rw[q["queryId"]]
            period = r.get("period") if r.get("ok") else None
            use_rw = name not in ("V 원문",) and not name.startswith("H LLM 없이")
            per = {k: s for k, s in sims[(model, "rw" if use_rw else "orig", q["queryId"])].items()
                   if (not use_rw or in_period(k[1], period, before))}
            vec = [k for k in order(per) if per[k] >= t]
            if name in ("V 원문", "V 변환문"):
                res[q["queryId"]] = {name: cards(vec, per)}
                continue
            key_rank = order(kw[q["queryId"]])
            if name == "H 키워드만 걸린 것도 포함(#679 기준안)":
                keys, s = rrf(vec, key_rank)
            elif name == "H 포함, 키워드는 제목+답에서만":
                keys, s = rrf(vec, order(kw_ta[q["queryId"]]))
            elif name == "H LLM 없이: 원문 벡터 + 질문 낱말, 키워드로만 걸린 건 2개 이상":
                raw = kw_raw[q["queryId"]]
                keys, s = rrf(vec, [k for k in order(raw) if k in vec or raw[k] >= 2])
            elif name == "H 포함, 키워드로만 걸린 건 2개 이상 맞을 때":
                keys, s = rrf(vec, [k for k in key_rank if k in vec or kw[q["queryId"]][k] >= 2])
            else:  # "H 키워드는 순서만(벡터 통과분 안에서)"
                keys, s = rrf(vec, [k for k in key_rank if k in vec])
            res[q["queryId"]] = {name: cards(keys, s)}
        return M.summarize(tune, {"themes": themes, "results": res}, name, None)

    names = ["V 원문", "V 변환문", "H 키워드만 걸린 것도 포함(#679 기준안)", "H 포함, 키워드는 제목+답에서만",
             "H 포함, 키워드로만 걸린 건 2개 이상 맞을 때", "H 키워드는 순서만(벡터 통과분 안에서)",
             "H LLM 없이: 원문 벡터 + 질문 낱말, 키워드로만 걸린 건 2개 이상"]
    report = {"date": today.isoformat(), "largeDimensions": args.large_dimensions, "llmModel": args.llm_model, "maxTokens": args.max_tokens, "reasoningEffort": args.reasoning_effort, "queries": len(tune), "docs": len(docs),
              "rewrite": {"ok": len(ok), "n": len(rw), "p50ms": M.percentile(ms, 0.5), "p95ms": M.percentile(ms, 0.95)},
              "methods": {}}
    kres = {q["queryId"]: {"K": cards(order(kw[q["queryId"]]), kw[q["queryId"]])} for q in tune}
    ks = M.summarize(tune, {"themes": themes, "results": kres}, "K", None)
    report["methods"]["K 변환 키워드만"] = ks
    print(f"\n{'방식':42} 기준값  Recall@3  거절  평균 | 종류별 Recall")
    cat = lambda s: {c: v.get("recall") for c, v in s["byCategory"].items() if c in M.RESULT_CATS}
    print(f"{'K 변환 키워드만(기준값 없음)':42}  -     {ks['recall@3']:.3f}   {ks['reject']:.3f} "
          f"{((ks['recall@3'] or 0) + (ks['reject'] or 0)) / 2:.3f} | {cat(ks)}")
    for model in MODELS:
        for name in names:
            best = None
            for t in SWEEP:
                s = method(name, model, t)
                o = ((s["recall@3"] or 0) + (s["reject"] or 0)) / 2
                if best is None or (round(o, 6), -abs(t - M.CURRENT_THRESHOLD)) > (round(best[0], 6), -abs(best[1] - M.CURRENT_THRESHOLD)):
                    best = (o, t, s)
            o, t, s = best
            s35 = method(name, model, M.CURRENT_THRESHOLD)
            report["methods"][f"{name} · {model}"] = {"chosenThreshold": t, "atChosen": s, "at0.35": s35}
            label = f"{name[:30] if not name.startswith('H LLM') else 'H LLM 없이(질문 낱말, 2개 이상)'} · {model.split('-')[-1]}"
            print(f"{label:42} {t:.2f}   {s['recall@3']:.3f}   {s['reject']:.3f} {o:.3f} | {cat(s)}")
    pathlib.Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {args.out} (변환 캐시 {cache_path}는 커밋하지 않음)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
