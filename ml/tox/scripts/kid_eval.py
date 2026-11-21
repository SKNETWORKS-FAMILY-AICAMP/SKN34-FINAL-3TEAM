"""아이 말투 시험 문장(`eval_sets/kid_test.json`)으로 막을 글 재현율·정상 글 오탐을 잰다(#690 보완).

scoring과 같은 길로 잰다: int8이면 채널별 양자화(quant.py)·글 하나씩·창 8개씩. 임계값은
`train_info.json`의 `threshold`(int8) 또는 `--threshold`. 모델만 본다(단어 목록은 따로).

    uv run python scripts/kid_eval.py --model checkpoints/kcelectra-base-s42 --int8
"""

from __future__ import annotations

import argparse
import json
import pathlib

from eval import score_texts
from quant import quantize_int8

TEST = pathlib.Path(__file__).resolve().parents[1] / "eval_sets/kid_test.json"


def summarize(block: list[float], ok: list[float], threshold: float) -> dict:
    caught = sum(p >= threshold for p in block)
    wrong = sum(p >= threshold for p in ok)
    return {
        "threshold": threshold,
        "blockCaught": caught,
        "block": len(block),
        "recall": round(caught / len(block), 4) if block else None,
        "passFlagged": wrong,
        "pass": len(ok),
        "falsePositiveRate": round(wrong / len(ok), 4) if ok else None,
    }


def by_part(parts: dict | None, block: list[float], ok: list[float], threshold: float) -> dict:
    """kid_test.json `parts`(앞에서부터 차례로 붙인 묶음 크기)별 요약."""
    out, b, p = {}, 0, 0
    for name, n in (parts or {}).items():
        out[name] = summarize(block[b : b + n["block"]], ok[p : p + n["pass"]], threshold)
        b, p = b + n["block"], p + n["pass"]
    return out


def main(argv=None):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, type=pathlib.Path)
    ap.add_argument("--int8", action="store_true")
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--out", type=pathlib.Path, default=None)
    ap.add_argument("--test", type=pathlib.Path, default=TEST, help="block·pass 문장 json")
    args = ap.parse_args(argv)
    info = json.loads((args.model / "train_info.json").read_text(encoding="utf-8"))
    test = json.loads(args.test.read_text(encoding="utf-8"))
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(args.model).eval()
    if args.int8:
        model = quantize_int8(model)
    else:
        model = model.to("cuda" if torch.cuda.is_available() else "cpu")
    device = "cpu" if args.int8 or not torch.cuda.is_available() else "cuda"

    def score(texts):
        return score_texts(
            model, tokenizer, texts, info["max_length"], info["stride"], device, per_text=True
        )

    block, ok = score(test["block"]), score(test["pass"])
    threshold = args.threshold if args.threshold is not None else info["threshold"]
    result = {
        "model": str(args.model.name),
        "int8": args.int8,
        "summary": summarize(block, ok, threshold),
        "byPart": by_part(test.get("parts"), block, ok, threshold),
        "missed": sorted(
            (
                {"text": t, "prob": round(p, 4)}
                for t, p in zip(test["block"], block, strict=True)
                if p < threshold
            ),
            key=lambda x: x["prob"],
        ),
        "wrong": [
            {"text": t, "prob": round(p, 4)}
            for t, p in zip(test["pass"], ok, strict=True)
            if p >= threshold
        ],
        "probs": {"block": [round(p, 4) for p in block], "pass": [round(p, 4) for p in ok]},
    }
    out = args.out or pathlib.Path(
        f"results/kid_eval_{args.model.name}_{'int8' if args.int8 else 'fp32'}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    s = result["summary"]
    print(
        f"{out.name}: 막을 글 {s['blockCaught']}/{s['block']} 잡음 · "
        f"정상 글 {s['passFlagged']}/{s['pass']} 잘못 막음 (임계값 {threshold})"
    )


if __name__ == "__main__":
    main()
