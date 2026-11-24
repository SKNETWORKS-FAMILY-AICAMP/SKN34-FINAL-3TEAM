"""증류(#690 11/18 실험 H) 선생님 확률: 학습 글마다 선생님 모델들의 막을 확률을 평균해 저장.
학습과 같은 방식(앞 max_length 토큰 한 창, fp32, GPU)으로 잰다. 글 원문은 저장하지 않고,
글 순서가 train.py와 같은지 확인하려고 글 목록의 sha256만 남긴다.
    uv run python scripts/teacher_probs.py --data data/p_kid \
        --models checkpoints/kid-s48 --out data/teacher_s48.npz
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


def texts_digest(texts: list[str]) -> str:
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def main(argv=None):
    import os

    import numpy as np

    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    torch.use_deterministic_algorithms(True)  # 11/19: 선생님 확률도 매번 같게
    torch.backends.cudnn.benchmark = False
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=pathlib.Path)
    ap.add_argument("--models", required=True, nargs="+", type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--batch-size", default=256, type=int)
    a = ap.parse_args(argv)
    lines = (a.data / "train.jsonl").read_text(encoding="utf-8").splitlines()
    texts = [json.loads(x)["text"] for x in lines if x.strip()]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    each = []
    for m in a.models:
        info = json.loads((m / "train_info.json").read_text(encoding="utf-8"))
        tok = AutoTokenizer.from_pretrained(m)
        model = AutoModelForSequenceClassification.from_pretrained(m).to(device).eval()
        probs = []
        with torch.no_grad():
            for i in range(0, len(texts), a.batch_size):
                enc = tok(
                    texts[i : i + a.batch_size],
                    truncation=True,
                    max_length=info["max_length"],
                    padding=True,
                    return_tensors="pt",
                ).to(device)
                probs += torch.softmax(model(**enc).logits.float(), dim=-1)[:, 1].cpu().tolist()
        each.append(np.array(probs, dtype=np.float32))
        print(f"{m.name}: 평균 확률 {each[-1].mean():.4f}")
    avg = np.mean(each, axis=0).astype(np.float32)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        a.out,
        probs=avg,
        digest=np.array(texts_digest(texts)),
        models=np.array([m.name for m in a.models]),
    )
    print({"n": len(avg), "models": [m.name for m in a.models], "out": str(a.out)})


if __name__ == "__main__":
    main()
