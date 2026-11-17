"""vLLM에서 설명 LoRA가 올라가고, Unsloth와 같은 해설이 나오는지 확인한다.

확인하는 것
1. 어댑터를 vLLM이 읽을 수 있는 모양으로 복사 (target_modules 정규식 → 이름 목록)
2. vLLM이 어댑터를 실제로 붙이는지 (LoRA 켠 결과와 끈 결과가 달라야 함)
3. 생각 끄기: 학습 때 프롬프트와 enable_thinking=False 프롬프트가 같은지
4. 해설 품질 지표 (eval_lora.py와 같은 채점) + Unsloth 결과(eval_samples.jsonl)와 겹침

화면에는 숫자만 찍는다. 생성 원문은 --samples-out에만 저장한다 (Pod 안에서만 보기).

vLLM은 Unsloth와 패키지가 부딪히니 따로 만든 가상환경의 python으로 돌린다:
    /workspace/vllm-env/bin/python vllm_check.py                       # 16비트 원본
    /workspace/vllm-env/bin/python vllm_check.py --model /workspace/models/gemma-awq --tag awq
"""

import argparse
import json
import re
import shutil
import statistics
import sys
import time
import types
from pathlib import Path

# eval_lora.py의 채점 함수를 그대로 쓴다. eval_lora는 맨 위에서 unsloth를 import하는데
# 이 가상환경에는 unsloth가 없어서 빈 모듈로 막아 둔다 (채점 함수는 unsloth를 안 씀).
sys.modules.setdefault("unsloth", types.SimpleNamespace(FastModel=None))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_lora import bigram_f1, score, summarize  # noqa: E402

from transformers import AutoTokenizer  # noqa: E402
from vllm import LLM, SamplingParams  # noqa: E402
from vllm.lora.request import LoRARequest  # noqa: E402

ATTN = ["q_proj", "k_proj", "v_proj", "o_proj"]


def prepare_adapter(src: Path, dst: Path) -> None:
    from safetensors import safe_open

    dst.mkdir(parents=True, exist_ok=True)
    weights = src / "adapter_model.safetensors"
    shutil.copy2(weights, dst / weights.name)
    cfg = json.loads((src / "adapter_config.json").read_text(encoding="utf-8"))
    with safe_open(str(weights), "pt") as f:
        keys = list(f.keys())
    found = sorted({m for k in keys for m in ATTN if f".{m}." in k})
    print(f"어댑터 텐서 {len(keys)}개, 붙은 모듈 {found}")
    shapes = sorted({re.sub(r"\.\d+\.", ".N.", k) for k in keys})
    print("텐서 이름 모양:", shapes[:4])
    if isinstance(cfg.get("target_modules"), str):
        print("target_modules가 정규식이라 이름 목록으로 바꿈")
        cfg["target_modules"] = found
    cfg["modules_to_save"] = None
    (dst / "adapter_config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="/workspace/models/gemma-4-26b-qat")
    p.add_argument("--tag", default="bf16", help="결과 파일 이름에 붙는 꼬리")
    p.add_argument("--adapter", type=Path, default=Path("/workspace/outputs/explain-lora/adapter"))
    p.add_argument("--vllm-adapter", type=Path, default=Path("/workspace/outputs/explain-lora/adapter-vllm"))
    p.add_argument("--data", type=Path, default=Path("/workspace/data/jsonl/valid.jsonl"))
    p.add_argument("--unsloth-samples", type=Path, default=Path("/workspace/outputs/eval_samples.jsonl"))
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--max-new", type=int, default=800)
    p.add_argument("--max-model-len", type=int, default=4096)
    p.add_argument("--gpu-util", type=float, default=0.88)
    args = p.parse_args()

    prepare_adapter(args.adapter, args.vllm_adapter)

    tok = AutoTokenizer.from_pretrained(str(args.adapter))
    probe = [{"role": "user", "content": "(질문)"}]
    trained = tok.apply_chat_template(probe, tokenize=False, add_generation_prompt=True)
    try:
        off = tok.apply_chat_template(
            probe, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        print(f"enable_thinking=False 프롬프트가 학습 때와 같음: {off == trained}")
    except Exception as e:  # 템플릿이 인자를 모르면
        print(f"enable_thinking 인자 확인 실패: {type(e).__name__}")
    print(f"학습 때 생성 프롬프트: {trained!r}")

    with args.data.open(encoding="utf-8") as f:
        recs = [json.loads(x) for x in f if x.strip()][: args.n]
    prompts = []
    for rec in recs:
        text = tok.apply_chat_template(
            [rec["messages"][0]], tokenize=False, add_generation_prompt=True
        )
        # 템플릿에 <bos>가 이미 있어서 특수 토큰을 또 붙이지 않는다
        prompts.append({"prompt_token_ids": tok(text, add_special_tokens=False)["input_ids"]})

    llm = LLM(
        model=args.model,
        tokenizer=str(args.adapter),
        enable_lora=True,
        max_lora_rank=16,
        max_loras=1,
        max_model_len=args.max_model_len,
        gpu_memory_utilization=args.gpu_util,
    )
    sp = SamplingParams(temperature=0, max_tokens=args.max_new, skip_special_tokens=True)
    lora = LoRARequest("explain", 1, str(args.vllm_adapter))

    outs, per = {}, {}
    for name, req in (("lora", lora), ("base", None)):
        t0 = time.time()
        res = llm.generate(prompts, sp, lora_request=req)
        secs = time.time() - t0
        outs[name] = [r.outputs[0].text.strip() for r in res]
        per[name] = secs / max(1, len(res))
        toks = sum(len(r.outputs[0].token_ids) for r in res)
        print(f"[{name}] {len(res)}개 {secs:.0f}초 (한꺼번에 생성), 출력 {toks:,}토큰, {toks / secs:.0f} 토큰/초")

    same = sum(a == b for a, b in zip(outs["lora"], outs["base"]))
    print(f"\nLoRA 켠 결과 = 끈 결과인 경우 {same}/{len(recs)} (많으면 어댑터가 안 붙은 것)")

    for name, label in (("base", "vLLM 학습 전"), ("lora", "vLLM 학습 후 LoRA")):
        rows = [
            score(r["messages"][0]["content"], o, r["messages"][1]["content"])
            for r, o in zip(recs, outs[name])
        ]
        summarize(label, rows, [per[name]])  # 시간은 한꺼번에 생성한 시간 ÷ 개수

    if args.unsloth_samples.exists():
        with args.unsloth_samples.open(encoding="utf-8") as f:
            prev = {s["id"]: s for s in (json.loads(x) for x in f if x.strip())}
        for name in ("lora", "base"):
            pairs = [(prev[r["id"]][name], o) for r, o in zip(recs, outs[name]) if name in prev.get(r["id"], {})]
            if pairs:
                exact = sum(a == b for a, b in pairs)
                f1 = statistics.mean(bigram_f1(a, b) for a, b in pairs)
                print(f"Unsloth와 비교 [{name}] 완전히 같음 {exact}/{len(pairs)}, 글자 2-gram F1 {f1:.3f}")

    out = Path(f"/workspace/outputs/vllm_samples_{args.tag}.jsonl")
    with out.open("w", encoding="utf-8") as f:
        for r, a, b in zip(recs, outs["lora"], outs["base"]):
            f.write(json.dumps({"id": r["id"], "lora": a, "base": b}, ensure_ascii=False) + "\n")
    print(f"\n생성 원문: {out} (Pod 안에서만 보기)")


if __name__ == "__main__":
    main()
