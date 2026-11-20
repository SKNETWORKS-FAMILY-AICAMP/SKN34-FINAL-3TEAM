"""AI Hub 초5·6 실제 답안(정상 글로 봄)에 대한 모델 확률만 저장(11/18 #690 오탐 시험).
글 원문은 출력·저장하지 않는다. scoring과 같은 길: int8 채널별·글 하나씩·창 8개씩.
    uv run python scripts/aihub_probs.py --model checkpoints/<모델> \
        --data data/aihub/kid16k.jsonl --out <json>
"""

from __future__ import annotations

import argparse
import json
import pathlib

from eval import score_texts
from quant import quantize_int8


def main(argv=None):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, type=pathlib.Path)
    ap.add_argument("--data", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    a = ap.parse_args(argv)
    info = json.loads((a.model / "train_info.json").read_text(encoding="utf-8"))
    texts = [
        json.loads(line)["text"]
        for line in a.data.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    tok = AutoTokenizer.from_pretrained(a.model)
    model = quantize_int8(AutoModelForSequenceClassification.from_pretrained(a.model).eval())
    probs = [
        round(p, 4)
        for p in score_texts(
            model, tok, texts, info["max_length"], info["stride"], "cpu", per_text=True
        )
    ]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"n": len(probs), "probs": probs}), encoding="utf-8")
    print({"n": len(probs), "over0.95": sum(p >= 0.95 for p in probs)})


if __name__ == "__main__":
    main()
