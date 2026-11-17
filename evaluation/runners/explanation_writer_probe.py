"""Development-only writer probe: reuse an existing evidence receipt, two additional calls.

Not part of the frozen v1 comparison, not a held-out improvement claim. Both writers receive
identical source/evidence/instructions. No GT annotations enter either prompt.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from explanation_eval import (
    Client, canonical, digest, instruction, load_env, proxy_metrics, public_input,
    save, valid_evidence,
)

WRITER_RULES = """이번 출력은 학부모에게 보여 주는 요약이다. 다음을 모두 따른다.
- 원문 구절에 나오는 구체적인 대상과 활동을 '여러 사람', '다양한 변화', '긍정적인 효과'로 뭉뚱그리지 않는다.
- 원문에서 핵심인 주장과 근거를 먼저 쓰고, 그 글에 맞는 도움 행동은 마지막에 짧게 제안한다.
- 해요체를 쓴다. '썼어요', '들었어요', '도와주세요'처럼 끝내고 '작성하였습니다', '하고 있습니다'는 쓰지 않는다.
- 원문에 없는 활동을 권장하거나 아이의 능력 향상을 약속하지 않는다.
- 근거를 반복하거나 머리말로 분량을 채우지 않는다. 3문장 이내, 공백 포함 70~220자.
출력은 {"text":"요약 본문"}이다."""


def run(args):
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    case = cases[0]
    if case.get("origin") != "user_form_synthetic":
        raise ValueError("SYNTHETIC_CASE_REQUIRED")
    prior = json.loads((args.out / "manifest.json").read_text(encoding="utf-8"))
    if prior["dataset_hash"] != digest([case]):
        raise ValueError("CASE_CHANGED")
    receipts = []
    for path in (args.out / "calls").glob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("stage") == "evidence" and value.get("state") == "COMPLETED":
            receipts.append((path.stem, value))
    if len(receipts) != 1:
        raise ValueError("ONE_EXISTING_EVIDENCE_RECEIPT_REQUIRED")
    evidence_key, receipt = receipts[0]
    evidence = valid_evidence(receipt["value"], case["answer"])
    user = (instruction("parent_summary") + "\n" + WRITER_RULES
            + "\n자료:\n" + canonical(public_input(case))
            + "\n동일하게 제공하는 추출 근거:\n" + canonical(evidence))
    env = load_env(args.env_file)
    client = Client(env, args.out, "SAGOMUNGCHI_SLLM_SERVERLESS_gemma",
                    "SAGOMUNGCHI_SLLM_SERVERLESS_KEY_gemma",
                    env.get("REPORT_GEMMA_MODEL", ""), 300, 12)
    manifest = {"phase": "observed-pilot-development-probe-v2", "case_hash": digest(case),
                "prompt_hash": digest(user), "evidence_call_key": evidence_key,
                "providers": ["gemma", "api"], "total_paid_cap_including_v1": 12,
                "expected_additional_calls": 2,
                "note": "Post-v1 development probe; not a held-out test or baseline replay"}
    mp = args.out / "writer-probe-manifest.json"
    if mp.exists() and json.loads(mp.read_text(encoding="utf-8")) != manifest:
        raise ValueError("PROBE_CHANGED")
    save(mp, manifest)  # freeze before either external call
    results = {}
    for provider in ("gemma", "api"):
        try:
            value, key = client.generate(provider, "controlled_writer_probe_v2", user)
            text = value.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("MISSING_TEXT")
            results[provider] = {"state": "COMPLETED", "text": text, "call_key": key,
                                 "proxy": proxy_metrics(text, case, "parent_summary")}
        except ValueError as exc:
            results[provider] = {"state": "FAILED", "error": str(exc)}
        save(args.out / "writer-probe-results.json", results)
        print(provider, results[provider]["state"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    run(parser.parse_args())
