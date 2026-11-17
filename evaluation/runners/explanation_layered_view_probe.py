"""One-call development demo of a medium default explanation plus existing long detail.

No API exemplar text or hidden GT is supplied. This is a UI/output-shape probe, not a new blind
benchmark or evidence of model superiority. Reuses the same source and prior Gemma evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from explanation_eval import Client, canonical, digest, load_env, public_input, save, valid_evidence

RULES = """학부모가 기본 화면에서 읽는 설명을 쓴다. 너무 짧은 요약이나 긴 상세 보고서가 아니다.
원문에서 확인되는 구체적인 생각과 근거를 친근한 해요체로 4~6문장, 공백 포함 320~480자로 쓴다.
글에서 무엇을 주장하고 어떤 구체적인 이유·사례를 썼는지 먼저 설명한다.
글의 실제 순서나 표현에서 보이는 특징을 연결하고, 끝에는 부모가 바로 해 볼 질문이나 도움을 제안한다.
이미 쓴 근거를 부족하다고 지적하지 말고, 보완 제안은 아직 더 설명할 수 있는 지점과 구분한다.
실제로 등장하는 대상과 활동을 '다양한 효과'처럼 뭉뚱그리지 않는다.
'글의 전반적인 특징과 지도 방향을 안내합니다' 같은 머리말, 제목, 항목별 나열은 쓰지 않는다.
글에 없는 독서·능력 향상·학습 활동을 권장하지 않는다. 과도한 칭찬이나 장래 효과를 단정하지 않는다.
너무 길어지면 원문 반복과 일반적인 칭찬을 줄인다. 문장을 길게 이어 분량을 채우지 않는다.
출력은 {"text":"기본 화면 설명"}인 JSON 객체 하나다."""


def run(args):
    case = json.loads(args.cases.read_text(encoding="utf-8"))[0]
    if case.get("origin") != "user_form_synthetic":
        raise ValueError("SYNTHETIC_CASE_REQUIRED")
    manifest = json.loads((args.out / "manifest.json").read_text(encoding="utf-8"))
    if manifest["dataset_hash"] != digest([case]):
        raise ValueError("CASE_CHANGED")
    evidence = valid_evidence(json.loads((args.out / "evidence-extraction.json").read_text(
        encoding="utf-8")), case["answer"])
    user = RULES + "\n자료:\n" + canonical(public_input(case)) + "\n추출 근거:\n" + canonical(evidence)
    save(args.out / "layered-view-probe-manifest.json", {
        "phase": "post-pilot-layered-output-development-demo-v3", "prompt_hash": digest(user),
        "expected_additional_calls": 1, "total_paid_cap_including_prior_work": 12,
        "api_exemplar_in_prompt": False, "hidden_gt_in_prompt": False,
        "note": "Medium default from Gemma; long detail is the original P0005 A, unchanged",
    })
    env = load_env(args.env_file)
    client = Client(env, args.out, "SAGOMUNGCHI_SLLM_SERVERLESS_gemma",
                    "SAGOMUNGCHI_SLLM_SERVERLESS_KEY_gemma",
                    env.get("REPORT_GEMMA_MODEL", ""), 300, 12)
    try:
        value, key = client.generate("gemma", "layered_default_view_probe_v3", user)
        text = value.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("MISSING_TEXT")
        result = {"state": "COMPLETED", "text": text, "call_key": key,
                  "characters": len(text), "length_ok": 320 <= len(text) <= 480,
                  "human_review": "PENDING", "superiority_claim": False}
    except ValueError as exc:
        result = {"state": "FAILED", "error": str(exc)}
    save(args.out / "layered-view-probe-results.json", result)
    print(result["state"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    run(parser.parse_args())
