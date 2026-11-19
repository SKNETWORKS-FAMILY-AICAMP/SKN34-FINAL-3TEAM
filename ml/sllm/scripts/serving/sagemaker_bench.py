"""SageMaker 엔드포인트에 가상 입력 요청을 보내 지연·토큰 수를 잰다(#746). aws CLI만 쓴다.

- compare: 기반 IC와 어댑터 IC(LoRA)에 같은 가상 입력을 runs번씩 보낸다. 요청마다 system 앞에 무작위 표식을 붙여
  접두 캐시를 피한다. 생성 원문은 --texts 폴더에만 저장하고(저장소에 넣지 않음) 표준 출력에는 수치만 낸다.
- worst: 최악의 경우(출력이 max_tokens까지 감)를 흉내 내려고 response_format 없이 ignore_eos로 max_tokens를 모두
  생성하게 하고, 동시 요청 수별로 지연을 잰다. 60초 응답 제한(InvokeEndpoint) 확인용이다.
"""
import argparse, concurrent.futures as cf, copy, json, subprocess, tempfile, time, uuid
from pathlib import Path


def invoke(a, component, body):
    with tempfile.TemporaryDirectory() as tmp:
        req, out = Path(tmp) / "req.json", Path(tmp) / "out.json"
        req.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        cmd = ["aws", "sagemaker-runtime", "invoke-endpoint", "--endpoint-name", a.endpoint,
               "--inference-component-name", component, "--content-type", "application/json",
               "--body", f"fileb://{req}", "--region", a.region, "--cli-read-timeout", "70", str(out)]
        if a.profile:
            cmd += ["--profile", a.profile]
        t0 = time.perf_counter()
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        sec = round(time.perf_counter() - t0, 2)
        if r.returncode != 0:
            return {"ok": False, "seconds": sec, "error": r.stderr.strip()[:200]}
        d = json.loads(out.read_text(encoding="utf-8"))
    ch = d["choices"][0]
    return {"ok": True, "seconds": sec, "finish": ch.get("finish_reason"),
            "completion_tokens": (d.get("usage") or {}).get("completion_tokens"), "text": ch["message"].get("content")}


def fresh(body, max_tokens=None):
    b = copy.deepcopy(body)
    b["messages"][0]["content"] = f"[req {uuid.uuid4().hex[:8]}]\n" + b["messages"][0]["content"]
    if max_tokens:
        b["max_tokens"] = max_tokens
    return b


p = argparse.ArgumentParser()
p.add_argument("mode", choices=["compare", "worst"])
p.add_argument("--profile"); p.add_argument("--region", default="ap-northeast-2")
p.add_argument("--endpoint", default="sagomungchi-demo-explanation")
p.add_argument("--base", default="sagomungchi-demo-explanation-ic")
p.add_argument("--adapter", default="sagomungchi-demo-explanation-explain")
p.add_argument("--prompts", required=True, help="gen_prompts.py 결과")
p.add_argument("--runs", type=int, default=5)
p.add_argument("--explanation-max-tokens", type=int, default=1536)
p.add_argument("--narrative-max-tokens", type=int, default=1024)
p.add_argument("--concurrency", default="1,4,8")
p.add_argument("--texts", help="생성 원문을 저장할 폴더(저장소 밖)")
p.add_argument("--out", required=True)
a = p.parse_args()
P = json.load(open(a.prompts, encoding="utf-8"))
limits = {"explanation": a.explanation_max_tokens, "narrative": a.narrative_max_tokens}
res = {"mode": a.mode, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rows": []}
if a.mode == "compare":
    for name, comp in (("base", a.base), ("explain", a.adapter)):
        for kind in ("explanation", "narrative"):
            for i in range(a.runs):
                r = invoke(a, comp, fresh(P[kind], limits[kind]))
                text = r.pop("text", None)
                if a.texts and text is not None:
                    Path(a.texts).mkdir(parents=True, exist_ok=True)
                    (Path(a.texts) / f"{name}-{kind}-{i}.txt").write_text(text, encoding="utf-8")
                r.update(component=name, kind=kind, run=i)
                print(json.dumps(r, ensure_ascii=False), flush=True)
                res["rows"].append(r)
else:
    body = copy.deepcopy(P["explanation"]); body.pop("response_format", None)
    body.update(ignore_eos=True, max_tokens=a.explanation_max_tokens)
    for n in [int(x) for x in a.concurrency.split(",")]:
        t0 = time.perf_counter()
        with cf.ThreadPoolExecutor(n) as ex:
            rows = list(ex.map(lambda _: invoke(a, a.base, fresh(body)), range(n)))
        wall = round(time.perf_counter() - t0, 2)
        for r in rows:
            r.pop("text", None)
        summary = {"concurrency": n, "wall_s": wall, "max_s": max(r["seconds"] for r in rows),
                   "ok": sum(r["ok"] for r in rows), "tokens": [r.get("completion_tokens") for r in rows],
                   "errors": [r["error"] for r in rows if not r["ok"]]}
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        res["rows"].append(summary)
Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
