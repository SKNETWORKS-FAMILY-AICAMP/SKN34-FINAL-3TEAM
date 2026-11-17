"""단어 목록과 함께 쓸 때의 추가 차단율·추가 오탐과 임계값(#690).

이슈 기준안 "정상 문장 추가 오탐 1% 이하(단어 목록 대비)"대로, 단어 목록이 통과시킨 검증 정상 글
중 모델이 더 막는 비율이 1% 이하이고 꼭 통과할 글 최고 확률보다 큰 임계값 가운데 F1이 가장 큰
값을 고른다.

입력
- `--probs`: `eval.py --save-probs`가 저장한 글별 확률·라벨(npz, 글 없음)
- `--flags`: 같은 글 순서의 단어 목록 결과 0/1(JSON `{"valid": [...], "test": [...], ...}`).
  단어 목록은 learning-service Kotlin(`ExpressionPolicy`)이라 임시 시험으로 뽑는다(eval_tox.md 재현)
- `--eval-json`: 같은 모델·방식의 `eval.py` 결과(꼭 통과할 글 최고 확률·fp32/int8)

    uv run python scripts/wordlist.py --probs data/probs_int8.npz --flags data/wordlist_flags.json \
        --eval-json results/eval_tox_int8.json --model checkpoints/<모델> --write
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

from eval import GRID, MAX_FPR
from train import binary_metrics

SETS = ("valid", "test", "apeach")


def with_wordlist(probs, labels, flags, threshold: float) -> dict:
    """모델만·단어 목록만·둘 다 쓸 때. extra = 단어 목록이 통과시킨 글 중 모델이 더 막은 비율."""
    rows = list(zip(probs, labels, flags, strict=True))
    model = [p >= threshold for p, _, _ in rows]

    def rate(hit, keep):
        n = sum(1 for k in keep if k)
        return round(sum(1 for h, k in zip(hit, keep, strict=True) if h and k) / n, 4) if n else 0.0

    pos = [y == 1 for _, y, _ in rows]
    neg = [y == 0 for _, y, _ in rows]
    word = [f == 1 for _, _, f in rows]
    both = [m or w for m, w in zip(model, word, strict=True)]
    passed = [not w for w in word]
    return {
        "threshold": threshold,
        "model": binary_metrics(probs, labels, threshold),
        "wordListRecall": rate(word, pos),
        "wordListFalsePositiveRate": rate(word, neg),
        "extraCatch": rate(model, [p and q for p, q in zip(pos, passed, strict=True)]),
        "extraFalsePositiveRate": rate(model, [n and q for n, q in zip(neg, passed, strict=True)]),
        "combinedRecall": rate(both, pos),
        "combinedFalsePositiveRate": rate(both, neg),
    }


def pick(probs, labels, flags, must_pass_max: float, max_extra_fp: float = MAX_FPR):
    """조건을 만족하는 임계값 중 모델 F1 최대(같으면 큰 값). 없으면 (None, 이유)."""
    best = None
    for t in GRID:
        if t <= must_pass_max:
            continue
        r = with_wordlist(probs, labels, flags, t)
        if r["extraFalsePositiveRate"] > max_extra_fp:
            continue
        if best is None or r["model"]["f1"] >= best["model"]["f1"]:
            best = r
    if best is None:
        reason = f"꼭 통과할 글 {must_pass_max:.4f}·추가 오탐 {max_extra_fp} 조건 불가"
        return None, {"reason": reason}
    return best["threshold"], best


def main(argv=None):
    import numpy as np

    ap = argparse.ArgumentParser()
    ap.add_argument("--probs", required=True, type=pathlib.Path)
    ap.add_argument("--flags", required=True, type=pathlib.Path)
    ap.add_argument("--eval-json", required=True, type=pathlib.Path)
    ap.add_argument("--model", type=pathlib.Path, help="--write 때 고칠 모델 폴더")
    ap.add_argument("--max-extra-fpr", default=MAX_FPR, type=float)
    ap.add_argument("--out", default=None, type=pathlib.Path)
    ap.add_argument("--write", action="store_true", help="고른 임계값을 train_info.json에 씀")
    args = ap.parse_args(argv)

    z = np.load(args.probs)
    flags = json.loads(args.flags.read_text(encoding="utf-8"))
    ev = json.loads(args.eval_json.read_text(encoding="utf-8"))
    mode = "int8" if ev["int8"] else "fp32"
    mp_max = ev["mustPass"]["maxProb"]

    def data(name):
        return z[f"{name}_probs"].tolist(), z[f"{name}_labels"].tolist(), flags[name]

    threshold, chosen = pick(*data("valid"), mp_max, args.max_extra_fpr)
    rule = (
        f"꼭 통과할 글 최고 확률 초과 · 단어 목록이 통과시킨 검증 정상 글 추가 오탐 ≤ "
        f"{args.max_extra_fpr} · F1 최대"
    )
    result = {
        "mode": mode,
        "evaluatedAt": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "rule": rule,
        "mustPassMax": mp_max,
        "threshold": threshold,
        "valid": chosen,
        **{
            s: with_wordlist(*data(s), threshold)
            for s in ("test", "apeach")
            if threshold is not None and f"{s}_probs" in z.files and s in flags
        },
    }
    out = args.out or pathlib.Path(f"results/wordlist_{mode}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{mode} 임계값 {threshold} → {out}")
    if threshold is None:
        raise SystemExit("조건을 만족하는 임계값 없음")
    if args.write:
        path = args.model / "train_info.json"
        info = json.loads(path.read_text(encoding="utf-8"))
        info["threshold"] = threshold
        info["thresholdSource"] = f"wordlist.py {result['evaluatedAt'][:10]} {mode}: {rule}"
        info["quantization"] = "int8-dynamic" if mode == "int8" else "none"
        path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"train_info.json threshold → {threshold}")


if __name__ == "__main__":
    main()
