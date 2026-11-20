"""꼭 통과할 글 전부의 모델 확률을 저장한다(11/18 #690 평균 실험용, eval.py는 상위 10개만 남김).

scoring과 같은 길: int8 채널별(quant.py)·글 하나씩·창 8개씩. 글 원문은 저장하지 않고 확률만.
    uv run python scripts/mustpass_probs.py --model checkpoints/<모델> --out <json>
"""

from __future__ import annotations

import argparse
import json
import pathlib

from eval import REPO, must_pass, score_texts
from quant import quantize_int8


def main(argv=None):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args(argv)
    info = json.loads((args.model / "train_info.json").read_text(encoding="utf-8"))
    tok = AutoTokenizer.from_pretrained(args.model)
    model = quantize_int8(AutoModelForSequenceClassification.from_pretrained(args.model).eval())
    sets = must_pass(REPO)
    out = {
        name: [
            round(p, 4)
            for p in score_texts(
                model, tok, texts, info["max_length"], info["stride"], "cpu", per_text=True
            )
        ]
        for name, texts in sets.items()
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out), encoding="utf-8")
    print({k: (len(v), max(v)) for k, v in out.items()})


if __name__ == "__main__":
    main()
