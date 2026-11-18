"""OpenAI 호환 서버(vLLM·llama-server)에 가상 입력 요청을 보내 지연·토큰 수를 잰다."""
import argparse, json, time, urllib.request, concurrent.futures as cf

def call(url, body):
    body = dict(body, stream=True, stream_options={"include_usage": True})
    req = urllib.request.Request(url + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t0 = time.perf_counter(); ttft = None; text = []; usage = None; finish = None; timings = None; reasoning = []
    with urllib.request.urlopen(req, timeout=3600) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data:"): continue
            data = line[5:].strip()
            if data == "[DONE]": break
            ev = json.loads(data)
            for ch in ev.get("choices") or []:
                d = ch.get("delta") or {}
                if d.get("reasoning_content") or d.get("reasoning"):
                    reasoning.append(d.get("reasoning_content") or d.get("reasoning"))
                piece = d.get("content")
                if piece:
                    if ttft is None: ttft = time.perf_counter() - t0
                    text.append(piece)
                finish = ch.get("finish_reason") or finish
            usage = ev.get("usage") or usage
            timings = ev.get("timings") or timings
    total = time.perf_counter() - t0
    out = usage.get("completion_tokens") if usage else None
    return {"total_s": round(total, 3), "ttft_s": round(ttft or total, 3),
            "prompt_tokens": usage.get("prompt_tokens") if usage else None,
            "completion_tokens": out, "finish": finish,
            "decode_tok_s": round(out / (total - ttft), 2) if out and ttft and total > ttft else None,
            "server_timings": timings, "reasoning_chars": len("".join(reasoning)), "text": "".join(text)}

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://127.0.0.1:8000"); p.add_argument("--model", required=True)
p.add_argument("--prompts", default="prompts.json"); p.add_argument("--runs", type=int, default=3)
p.add_argument("--batch", type=int, default=0, help="students for batch test (narrative+3 explanations each)")
p.add_argument("--concurrency", type=int, default=1); p.add_argument("--out", required=True)
a = p.parse_args()
P = json.load(open(a.prompts, encoding="utf-8"))
res = {"model": a.model, "single": [], "batch": None}
for kind in ("narrative", "explanation"):
    for i in range(a.runs):
        r = call(a.url, dict(P[kind], model=a.model)); r["kind"] = kind; r["run"] = i
        print(kind, i, {k: r[k] for k in ("total_s", "ttft_s", "prompt_tokens", "completion_tokens", "decode_tok_s", "finish")}, flush=True)
        res["single"].append(r)
if a.batch:
    jobs = [kind for _ in range(a.batch) for kind in ("narrative", "explanation", "explanation", "explanation")]
    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(a.concurrency) as ex:
        rs = list(ex.map(lambda k: dict(call(a.url, dict(P[k], model=a.model)), kind=k), jobs))
    wall = time.perf_counter() - t0
    res["batch"] = {"students": a.batch, "requests": len(jobs), "concurrency": a.concurrency,
                    "wall_s": round(wall, 1), "completion_tokens": sum(r["completion_tokens"] or 0 for r in rs),
                    "max_latency_s": max(r["total_s"] for r in rs),
                    "finish_length": sum(r["finish"] == "length" for r in rs)}
    res["batch_rows"] = rs
    res["batch"]["finish_length_by_kind"] = {k: sum(r["finish"] == "length" and r["kind"] == k for r in rs) for k in ("narrative", "explanation")}
    res["batch"]["agg_tok_s"] = round(res["batch"]["completion_tokens"] / wall, 1)
    print("batch", res["batch"], flush=True)
json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
