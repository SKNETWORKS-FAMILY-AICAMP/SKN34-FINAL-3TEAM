"""Generate RunPod Gemma details for the synthetic weekly report shown by the web mock."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from explanation_eval import Client, canonical, digest, load_env, public_input, save

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "frontend/web"
MOCK_SAMPLES = WEB / "src/mocks/fixtures/structuredReportSamples.json"
DEFAULT_CACHE = WEB / ".taste-skill/structured-report-demo/gemma-explanations.json"
DEFAULT_OUT = ROOT / "local_data/explanation_eval/structured-report-demo"
DEFAULT_PROMPT = ROOT / "evaluation/datasets/explanation/structured-detail-prompt.md"
RUNPOD_ENDPOINT = "SAGOMUNGCHI_SLLM_SERVERLESS_GEMMA"
RUNPOD_KEY = "SAGOMUNGCHI_SLLM_SERVERLESS_KEY_GEMMA"


def mock_cases():
    data = json.loads(MOCK_SAMPLES.read_text(encoding="utf-8"))
    return [
        {
            "id": sample["attemptId"],
            "origin": "synthetic_ui_demo",
            "grade": data["grade"],
            "topic": sample["question"],
            "answer": sample["texts"][-1],
            "answerVersion": len(sample["texts"]),
        }
        for sample in data["samples"]
    ]


def valid(value):
    if set(value) != {"analysis", "improvement_points", "next_steps"}:
        raise ValueError("STRUCTURE_KEYS")
    if not isinstance(value["analysis"], str) or not value["analysis"].strip():
        raise ValueError("ANALYSIS_MISSING")
    if value["improvement_points"] is not None and (
        not isinstance(value["improvement_points"], str) or not value["improvement_points"].strip()
    ):
        raise ValueError("IMPROVEMENT_SHAPE")
    steps = value["next_steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 2 or not all(
        isinstance(step, str) and step.strip() for step in steps
    ):
        raise ValueError("STEPS_SHAPE")
    text = " ".join([value["analysis"], value["improvement_points"] or "", *steps])
    if re.search(r"안녕하세요|학부모님|분석한 결과를 드립니다|지금부터 살펴보겠", text):
        raise ValueError("UNWANTED_PREFACE")


def run(args):
    cases = json.loads(args.cases.read_text(encoding="utf-8")) if args.cases else mock_cases()
    if len(cases) != 3 or any(case.get("origin") != "synthetic_ui_demo" for case in cases):
        raise ValueError("THREE_SYNTHETIC_DEMO_CASES_REQUIRED")
    rules = args.prompt.read_text(encoding="utf-8").split("```text\n", 1)[1].split("```", 1)[0]
    manifest = {"version": "structured-report-detail@2", "dataset_hash": digest(cases),
                "rules_hash": digest(rules), "max_new_inference_calls": 3,
                "model": args.model,
                "human_quality_review": "PENDING", "is_benchmark": False}
    if (args.out / "manifest.json").exists():
        if json.loads((args.out / "manifest.json").read_text(encoding="utf-8")) != manifest:
            raise ValueError("MANIFEST_CHANGED")
    env = load_env(args.env_file)
    for name in (RUNPOD_ENDPOINT, RUNPOD_KEY):
        if not env.get(name):
            env[name] = env.get(name.removesuffix("GEMMA") + "gemma", "")
    client = Client(env, args.out, RUNPOD_ENDPOINT, RUNPOD_KEY, args.model, 600, 3)
    save(args.out / "manifest.json", manifest)
    results = {}
    # Browser-facing cache contains only synthetic source and final model content, never receipts/keys.
    cache = {"model": client.model, "promptVersion": manifest["version"], "items": []}
    for case in cases:
        try:
            value, key = client.generate("gemma", "structured_report_detail_v2",
                                         rules + "\n자료:\n" + canonical(public_input(case)))
            valid(value)
            cache["items"].append({"attemptId": case["id"], "answerVersion": case["answerVersion"],
                                   "sourceText": case["answer"], "text": json.dumps(value, ensure_ascii=False)})
            results[case["id"]] = {"state": "COMPLETED", "call_key": key,
                                   "characters": len(json.dumps(value, ensure_ascii=False))}
        except ValueError as exc:
            results[case["id"]] = {"state": "FAILED", "error": str(exc)}
        save(args.out / "results.json", results)
        save(args.cache, cache)
        print(case["id"], results[case["id"]]["state"], flush=True)
    print("Completed", len(cache["items"]), "of", len(cases), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, help="Override with three synthetic demo cases")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--model", default="explain", help="RunPod model alias for the report LoRA")
    run(parser.parse_args())
