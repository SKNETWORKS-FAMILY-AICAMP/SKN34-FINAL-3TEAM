"""답변 표현 분류(#690) 지연 측정: CPU 1코어에서 글 길이별 중앙값·p95.

#690 목표: CPU 1코어(`OMP_NUM_THREADS=1`), 200~1,200자 입력, p95 300ms 이하.
scoring 계약(api-spec 4.3.4)과 같은 길로 잰다: 토큰화 → `max_length`·`stride` 창 → 창 8개씩 추론
→ 창별 막을 확률 최댓값. 한 창이 걸려도 멈추지 않고 끝까지(가장 느린 경우).
글은 데모 미션 시드 문장을 이어 붙여 길이를 맞춘다(우리가 쓴 글, 학생 글 아님).
`--int8`이면 불러온 뒤 Linear 층만 동적 양자화(파일은 fp32 그대로, 11/16 측정 약 3~5배 빠름).
정확도 차이는 `eval.py --int8`로 따로 잰다.

    OMP_NUM_THREADS=1 uv run python scripts/latency.py --model checkpoints/kcelectra-base-s42
    OMP_NUM_THREADS=1 uv run python scripts/latency.py --model checkpoints/kcelectra-base-s42 --int8
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import platform
import statistics
import time

from eval import REPO, must_pass

LENGTHS = (200, 600, 1200, 1500)
TARGET_MS = 300
WINDOW_BATCH = 8


def make_text(sentences: list[str], length: int) -> str:
    """문장을 공백으로 이어 붙여 정확히 length 글자로 자른다."""
    if not sentences:
        raise ValueError("문장이 없음")
    text, i = "", 0
    while len(text) < length:
        text = f"{text} {sentences[i % len(sentences)]}" if text else sentences[0]
        i += 1
    return text[:length]


def percentile(values: list[float], q: float) -> float:
    """선형 보간 백분위(numpy 기본과 같음)."""
    xs = sorted(values)
    k = (len(xs) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def load(model_dir: pathlib.Path, int8: bool):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "1")))
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).eval()
    if int8:
        model = torch.ao.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
    return model, tokenizer


def check_once(model, tokenizer, text: str, max_length: int, stride: int) -> tuple[float, int]:
    import torch

    enc = tokenizer(
        text,
        truncation=True,
        max_length=max_length,
        stride=stride,
        return_overflowing_tokens=True,
        padding=True,
        return_tensors="pt",
    )
    ids, mask = enc["input_ids"], enc["attention_mask"]
    best = 0.0
    with torch.no_grad():
        for i in range(0, len(ids), WINDOW_BATCH):
            logits = model(
                input_ids=ids[i : i + WINDOW_BATCH], attention_mask=mask[i : i + WINDOW_BATCH]
            )
            best = max(best, torch.softmax(logits.logits.float(), dim=-1)[:, 1].max().item())
    return best, len(ids)


def measure(args: argparse.Namespace) -> dict:
    info = json.loads((args.model / "train_info.json").read_text(encoding="utf-8"))
    model, tokenizer = load(args.model, args.int8)
    sentences = must_pass(args.repo)["demo"]
    rows = []
    for length in args.lengths:
        text = make_text(sentences, length)
        for _ in range(args.warmup):
            check_once(model, tokenizer, text, info["max_length"], info["stride"])
        times, windows = [], 0
        for _ in range(args.repeat):
            start = time.perf_counter()
            _, windows = check_once(model, tokenizer, text, info["max_length"], info["stride"])
            times.append((time.perf_counter() - start) * 1000)
        p95 = percentile(times, 0.95)
        rows.append(
            {
                "chars": length,
                "windows": windows,
                "medianMs": round(statistics.median(times), 1),
                "p95Ms": round(p95, 1),
                "maxMs": round(max(times), 1),
                "meetsTarget": p95 <= TARGET_MS if length <= 1200 else None,
            }
        )
        print(
            f"{length}자 창 {windows}개: 중앙 {rows[-1]['medianMs']}ms · p95 {rows[-1]['p95Ms']}ms"
        )
    import torch

    return {
        "measuredAt": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "int8": args.int8,
        "threads": torch.get_num_threads(),
        "machine": f"{platform.system()} {platform.machine()} {platform.processor()}".strip(),
        "torch": torch.__version__,
        "window": {"max_length": info["max_length"], "stride": info["stride"]},
        "repeat": args.repeat,
        "warmup": args.warmup,
        "targetP95Ms": TARGET_MS,
        "rows": rows,
        "meetsTarget200to1200": all(r["meetsTarget"] for r in rows if r["meetsTarget"] is not None),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True, type=pathlib.Path)
    ap.add_argument("--repo", default=REPO, type=pathlib.Path)
    ap.add_argument("--lengths", default=list(LENGTHS), type=int, nargs="+")
    ap.add_argument("--repeat", default=30, type=int)
    ap.add_argument("--warmup", default=3, type=int)
    ap.add_argument("--int8", action="store_true")
    ap.add_argument("--out", default=None, type=pathlib.Path)
    args = ap.parse_args(argv)
    if os.environ.get("OMP_NUM_THREADS") is None:
        print("OMP_NUM_THREADS가 없어 1로 잼(#690 기준 CPU 1코어)")
    result = measure(args)
    out = args.out or pathlib.Path(f"results/latency_{'int8' if args.int8 else 'fp32'}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"200~1,200자 p95 ≤ {TARGET_MS}ms: {result['meetsTarget200to1200']} → {out}")


if __name__ == "__main__":
    main()
