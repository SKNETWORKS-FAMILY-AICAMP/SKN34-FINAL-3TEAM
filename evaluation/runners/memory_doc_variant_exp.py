"""추억 검색 문서 모양 실험 (#568 시험 실행 후속). 조정용(초3) 학생만 쓴다.

시험 실행(11/16)에서 V의 정답 점수와 관련 없는 질문 점수가 겹쳐 기준값 하나로 나눌 수 없었다.
검색 문서(제목+이야기 대사+미션 질문+답)에서 무엇을 담을지 바꿔 임베딩하고, 러너와 같은 지표로 비교한다.
- 서비스 코드·DB는 바꾸지 않는다(learning_db 읽기 전용, 임베딩은 이 스크립트가 OpenAI에 직접 요청)
- 평가용(초5) 학생 문서는 읽지도 임베딩하지도 않는다(본 실행 결과를 보고 고르지 않기 위해)
- 결과 파일에는 숫자만 남긴다(답·질문 원문 없음). 키는 환경 변수 EVAL_OPENAI_API_KEY에서 읽고 출력하지 않는다

    python -I evaluation/runners/memory_doc_variant_exp.py --psql "<learning_db psql>" \
        --raw evaluation/results/memory/memory@1__trial.raw.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import pathlib
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # python -I는 스크립트 폴더를 경로에 넣지 않음
import memory_search_eval as M  # noqa: E402

# 서비스 검색 문서 만들기(MemorySearchRepository.register)와 검색 범위(MemoryVectorMapper.hits)를 그대로 옮김
DOC_SQL = """
SELECT json_build_object('sid', d.student_id, 'theme', d.theme_id, 'week', d.theme_week_start, 'attempt', d.attempt_id,
  'title', tv.title, 'scene', scene.text, 'question', mv.question, 'answer', ans.plain_text)::text
FROM memory_search_doc d JOIN attempt a ON a.id = d.attempt_id
JOIN theme_frame f ON f.student_id = d.student_id AND f.theme_id = d.theme_id AND f.theme_week_start = d.theme_week_start
JOIN mission_version mv ON mv.id = a.mission_version_id
JOIN weekly_theme t ON t.id = a.theme_id
JOIN weekly_theme_version tv ON tv.id = coalesce(t.published_version_id, t.current_version_id)
LEFT JOIN LATERAL (SELECT string_agg(line->>'text', E'\\n' ORDER BY ord) text
  FROM weekly_theme_day day CROSS JOIN LATERAL jsonb_array_elements(coalesce(day.dialogue, '[]'::jsonb)) WITH ORDINALITY AS lines(line, ord)
  WHERE day.theme_version_id = tv.id AND day.mission_id = a.mission_id) scene ON true
JOIN LATERAL (SELECT plain_text FROM answer WHERE attempt_id = a.id ORDER BY version DESC LIMIT 1) ans ON true
WHERE d.student_id IN ({ids}) AND a.student_id = d.student_id AND d.theme_week_start < '{before}' AND d.status = 'READY'
  AND a.context IN ('THEME_DAY','THEME_REVIEW') AND a.completed_at IS NOT NULL
"""

CURRENT = "지금(제목+대사+질문+답)"
VARIANTS = {
    CURRENT: ("title", "scene", "question", "answer"),
    "제목+질문+답": ("title", "question", "answer"),
    "질문+답": ("question", "answer"),
    "제목+답": ("title", "answer"),
    "답만": ("answer",),
    "제목+대사": ("title", "scene"),
}
SPLIT = "나눠 담기 max(제목+대사, 질문+답)"
SWEEP = [round(0.10 + 0.01 * i, 2) for i in range(61)]  # 0.10~0.70


def text_of(doc, names):
    """concat_ws(E'\\n', ...)와 같게: NULL은 건너뜀"""
    return "\n".join(doc[n] for n in names if doc[n] is not None)


class Embedder:
    def __init__(self, key, model, dimensions):
        self.key, self.model, self.dimensions, self.cache, self.tokens = key, model, dimensions, {}, 0

    def add(self, texts):
        todo = [t for t in dict.fromkeys(texts) if t not in self.cache]
        for i in range(0, len(todo), 64):
            part = todo[i:i + 64]
            req = urllib.request.Request("https://api.openai.com/v1/embeddings", method="POST",
                                         data=json.dumps({"model": self.model, "dimensions": self.dimensions,
                                                           "input": [t or " " for t in part]}).encode())
            req.add_header("Authorization", "Bearer " + self.key)
            req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = json.loads(r.read())
            except urllib.error.HTTPError as e:
                raise SystemExit(f"OpenAI 임베딩 HTTP {e.code}: {e.read()[:200]!r}")
            for x in data["data"]:
                self.cache[part[x["index"]]] = x["embedding"]
            self.tokens += data["usage"]["total_tokens"]

    def __getitem__(self, text):
        return self.cache[text]


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


def rank(scores):
    """회차 최고 점수로 상위 3회차(서비스 SQL rounds와 같은 정렬: 점수 내림, 주 내림, 테마)"""
    best = {}
    for k, s in scores:
        best[k] = max(s, best.get(k, -2.0))
    order = sorted(best.items(), key=lambda kv: (-kv[1], -dt.date.fromisoformat(kv[0][1]).toordinal(), kv[0][0]))[:3]
    cards = [{"themeId": k[0], "weekStart": k[1], "score": s, "attemptIds": []} for k, s in order]
    return {"state": "RESULTS" if cards else "NO_RESULTS", "cards": cards}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--psql", required=True, help="learning_db에 붙는 psql 명령(읽기 전용으로 씀)")
    ap.add_argument("--raw", help="시험 실행 raw 파일(있으면 '지금' 모양이 서비스 V와 같은지 대조)")
    ap.add_argument("--dataset", default=str(M.DATASET))
    ap.add_argument("--manifest", default=str(M.RESULTS / "load-manifest.json"))
    ap.add_argument("--model", default="text-embedding-3-small")
    ap.add_argument("--dimensions", type=int, default=1536, help="서비스 EMBEDDING_DIMENSIONS와 같게(DB vector(1536))")
    ap.add_argument("--today", help="진행 주 계산 기준 날짜(기본 KST 오늘)")
    ap.add_argument("--out")
    args = ap.parse_args()
    key = os.environ.get("EVAL_OPENAI_API_KEY")
    if not key:
        raise SystemExit("환경 변수 EVAL_OPENAI_API_KEY가 없음")

    queries, _ = M.load_dataset(pathlib.Path(args.dataset))
    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    themes = manifest["themes"]
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(M.KST).date()
    before = M.week_monday(today).isoformat()

    # 조정용 질문만(러너 score와 같은 제외 규칙)
    current_ok = {r["studentKey"] for r in manifest["attempts"] if r["week"] == "CURRENT"}
    tune = [q for q in queries if q["split"] == "tune"
            and not (q["category"] == "SCOPE" and q["evidence"] == "CURRENT" and q["studentKey"] not in current_ok)]
    keys = sorted({q["studentKey"] for q in tune})
    sids = {k: manifest["students"][k]["studentId"] for k in keys}

    rows = M.Psql(args.psql).run([("docs", DOC_SQL.format(ids=",".join(f"'{s}'" for s in sids.values()), before=before))])["docs"]
    docs = [json.loads(r[0]) for r in rows]
    by_student = {}
    for d in docs:
        by_student.setdefault(d["sid"], []).append(d)
    print(f"조정용 학생 {keys} · 문서 {len(docs)}개 · 질문 {len(tune)}개 (평가용 학생 문서는 읽지 않음)")

    emb = Embedder(key, args.model, args.dimensions)
    emb.add([q["query"] for q in tune])
    emb.add([text_of(d, names) for d in docs for names in VARIANTS.values()])

    results = {}  # 러너 summarize에 넣을 모양: results[qid][variant]
    for q in tune:
        qv = emb[q["query"]]
        own = by_student.get(sids[q["studentKey"]], [])
        sims = {name: [((d["theme"], d["week"]), cos(qv, emb[text_of(d, names)])) for d in own] for name, names in VARIANTS.items()}
        out = {name: rank(s) for name, s in sims.items()}
        out[SPLIT] = rank([(k, max(x, y)) for (k, x), (_, y) in zip(sims["제목+대사"], sims["질문+답"])])
        results[q["queryId"]] = out
    fake = {"themes": themes, "results": results}

    if args.raw:
        raw = json.loads(pathlib.Path(args.raw).read_text(encoding="utf-8"))
        diffs, same = [], 0
        for q in tune:
            v = raw["results"][q["queryId"]]["V"]["cards"]
            c = results[q["queryId"]][CURRENT]["cards"]
            if v and c:
                same += (v[0]["themeId"], v[0]["weekStart"]) == (c[0]["themeId"], c[0]["weekStart"])
                diffs.append(abs(v[0]["score"] - c[0]["score"]))
        print(f"대조: '지금' 모양 1위 회차가 서비스 V와 같음 {same}/{len(diffs)}, 1위 점수 차 최대 {max(diffs):.4f}")

    report = {"date": today.isoformat(), "model": args.model, "dimensions": args.dimensions, "docs": len(docs), "queries": len(tune),
              "embeddingTokens": emb.tokens, "variants": {}}
    print(f"\n{'문서 모양':34} 기준값  Recall@3  거절  평균 | 기준값없음 Recall | 종류별 Recall(고른 기준값)")
    for name in list(VARIANTS) + [SPLIT]:
        def obj(t):
            s = M.summarize(tune, fake, name, t)
            return ((s["recall@3"] or 0) + (s["reject"] or 0)) / 2
        best = max(SWEEP, key=lambda t: (round(obj(t), 6), -abs(t - M.CURRENT_THRESHOLD)))
        s, s0 = M.summarize(tune, fake, name, best), M.summarize(tune, fake, name, None)
        at35 = M.summarize(tune, fake, name, M.CURRENT_THRESHOLD)
        cats = {c: v.get("recall") for c, v in s["byCategory"].items() if c in M.RESULT_CATS}
        report["variants"][name] = {"chosenThreshold": best, "atChosen": s, "at0.35": at35, "noThreshold": s0}
        print(f"{name:34} {best:.2f}   {s['recall@3']:.3f}   {s['reject']:.3f} {obj(best):.3f} | {s0['recall@3']:.3f}"
              f"            | {cats}")
    out_path = pathlib.Path(args.out or M.RESULTS / f"doc-variant__tune__{args.model}.json")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n모델 {args.model}({args.dimensions}차원) · 임베딩 토큰 {emb.tokens} · → {out_path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
