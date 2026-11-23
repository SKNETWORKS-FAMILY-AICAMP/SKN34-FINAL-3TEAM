"""답변 표현 분류(#690) 학습: KcELECTRA 2분류(1 = 막을 글, 0 = 정상), scoring 등록부 모양으로 저장.

입력은 prepare_data.py 출력(`data/processed/{train,valid}.jsonl`, 칸 text·label·source).
저장 폴더(`checkpoints/<실험>/`, gitignore)에 남는 것
- 등록부 업로드 5개(api-spec 5.2.1): config.json·model.safetensors(fp32)·tokenizer.json·
  tokenizer_config.json·train_info.json
- valid_probs.npz: 가장 좋은 에폭의 검증 글별 막을 확률과 라벨(글 원문 없음, 앞 128토큰만 본 값).
  eval.py는 서비스와 같은 창 방식으로 다시 재서 임계값을 정한다

임계값은 여기서 정하지 않는다. train_info.json에는 우선 0.5를 넣고(`thresholdSource`에 표시),
eval.py가 검증셋으로 정해 다시 쓴다.
학습·검증 글은 외부 API로 보내지 않는다. GPU가 있으면 GPU, 없으면 CPU(동작 확인용 `--limit`).

    uv run python scripts/train.py --data data/processed --out checkpoints/kcelectra-base-s42
    #  동작 확인만: --limit 500 --epochs 1
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import random

BASE_MODEL = "beomi/KcELECTRA-base"  # MIT, 라이선스 확인 11/16 (learning.md 16장)
MAX_LENGTH = 128  # 학습 데이터 95%가 100자 미만, scoring 창 길이와 같게 (api-spec 4.3.4)
STRIDE = 32
DEFAULT_THRESHOLD = 0.5
ARTIFACT_FILES = (
    "config.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "train_info.json",
)
DATA_SOURCES = [
    {"name": "K-MHaS", "license": "CC BY-SA 4.0", "use": "학습·검증·시험"},
    {"name": "Korean HateSpeech (BEEP!)", "license": "CC BY-SA 4.0", "use": "학습·검증"},
]
KID_SOURCE_NAME = "kid-written"  # scripts/kid_data.py
KID_SOURCE = [
    {
        "name": "아이 말투 직접 작성(eval_sets/kid_train.json)",
        "license": "Claude 작성, NFR-DAT-03 예외(#887)",
        "use": "학습만(시험 문장 eval_sets/kid_test.json과 겹침 검사)",
    }
]


def read_jsonl(path: pathlib.Path, limit: int | None = None) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                x = json.loads(line)
                if x.get("label") not in (0, 1) or not str(x.get("text", "")).strip():
                    raise ValueError(f"{path.name}: 라벨 0·1과 글이 있어야 함")
                row = {"text": x["text"], "label": int(x["label"])}
                if "source" in x:  # kid_data.py가 더한 줄 수를 train_info.json에 남기려고
                    row["source"] = x["source"]
                rows.append(row)
    if limit:
        random.Random(42).shuffle(rows)
        rows = rows[:limit]
    return rows


def binary_metrics(probs: list[float], labels: list[int], threshold: float) -> dict:
    """막을 글(1)을 양성으로 본 정밀도·재현율·F1과 정상 글 오탐률."""
    tp = sum(1 for p, y in zip(probs, labels, strict=True) if p >= threshold and y == 1)
    fp = sum(1 for p, y in zip(probs, labels, strict=True) if p >= threshold and y == 0)
    fn = sum(1 for p, y in zip(probs, labels, strict=True) if p < threshold and y == 1)
    neg = sum(1 for y in labels if y == 0)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "threshold": threshold,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "falsePositiveRate": round(fp / neg, 4) if neg else 0.0,
        "n": len(labels),
    }


def build_train_info(
    *,
    base_revision: str | None,
    args: argparse.Namespace,
    sizes: dict,
    best_epoch: int,
    valid: dict,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    if not 0 < threshold < 1:
        raise ValueError("threshold는 0 초과 1 미만 (api-spec 5.2)")
    return {
        "task": "toxicity-binary",
        "labels": {"0": "ok", "1": "block"},
        "positiveLabel": 1,
        "max_length": args.max_length,
        "stride": STRIDE,
        "threshold": threshold,
        "thresholdSource": "기본값 0.5, eval.py가 검증셋 기준으로 다시 정함",
        "baseModel": args.model,
        "baseRevision": base_revision,
        "data": DATA_SOURCES + (KID_SOURCE if sizes.get("kidWritten") else []),
        "sizes": sizes,
        "train": {
            "epochs": args.epochs,
            "lr": args.lr,
            "batchSize": args.batch_size,
            "warmupRatio": 0.1,
            "seed": args.seed,
            "deterministic": True,
            "bestEpoch": best_epoch,
        },
        "valid": valid,
        "trainedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


def check_artifact(folder: pathlib.Path) -> list[str]:
    """등록부 업로드 파일이 다 있는지, train_info가 로더 검사를 통과할 모양인지(문제 목록)."""
    problems = [f"{name} 없음" for name in ARTIFACT_FILES if not (folder / name).is_file()]
    info_path = folder / "train_info.json"
    if info_path.is_file():
        info = json.loads(info_path.read_text(encoding="utf-8"))
        if not (isinstance(info.get("threshold"), (int, float)) and 0 < info["threshold"] < 1):
            problems.append("threshold가 0 초과 1 미만이 아님")
        for key in ("max_length", "stride"):
            if not (isinstance(info.get(key), int) and info[key] > 0):
                problems.append(f"{key}가 양의 정수가 아님")
    config_path = folder / "config.json"
    if config_path.is_file():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if len(config.get("id2label", {})) != 2:
            problems.append("2분류 config가 아님(num_labels=2)")
    return problems


def train(args: argparse.Namespace) -> pathlib.Path:
    import os

    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")  # torch import 전에(결정적 cuBLAS)
    import numpy as np
    import torch
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        get_linear_schedule_with_warmup,
    )

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    # 같은 시드·GPU 종류·라이브러리면 같은 가중치가 나오게 GPU 계산 순서도 고정(11/19, 조금 느려짐)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_rows = read_jsonl(args.data / "train.jsonl", args.limit)
    valid_rows = read_jsonl(args.data / "valid.jsonl", args.limit)
    print(f"학습 {len(train_rows)} · 검증 {len(valid_rows)} · 장치 {device}")
    teacher = None
    if args.teacher:  # 증류: 글 순서가 같은지 sha256으로 확인
        from teacher_probs import texts_digest

        t = np.load(args.teacher)
        if args.limit or len(t["probs"]) != len(train_rows):
            raise ValueError("선생님 확률 수가 학습 글 수와 다름(--limit 같이 못 씀)")
        if str(t["digest"]) != texts_digest([r["text"] for r in train_rows]):
            raise ValueError("선생님 확률의 글 순서가 학습 글과 다름")
        teacher = np.clip(t["probs"].astype(np.float64), 1e-6, 1 - 1e-6)
        print(f"증류: 선생님 {list(t['models'])} · alpha {args.alpha} · T {args.temperature}")

    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision, use_fast=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model,
        revision=args.revision,
        num_labels=2,
        id2label={0: "ok", 1: "block"},
        label2id={"ok": 0, "block": 1},
        problem_type="single_label_classification",
    ).to(device)
    base_revision = getattr(model.config, "_commit_hash", None) or args.revision

    def batches(rows, shuffle):
        order = list(range(len(rows)))
        if shuffle:
            random.shuffle(order)
        for i in range(0, len(order), args.batch_size):
            part = [rows[j] for j in order[i : i + args.batch_size]]
            enc = tokenizer(
                [x["text"] for x in part],
                truncation=True,
                max_length=args.max_length,
                padding=True,
                return_tensors="pt",
            )
            y = torch.tensor([x["label"] for x in part], device=device)
            yield {k: v.to(device) for k, v in enc.items()}, y, order[i : i + args.batch_size]

    steps = math.ceil(len(train_rows) / args.batch_size) * args.epochs
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scheduler = get_linear_schedule_with_warmup(optimizer, int(steps * 0.1), steps)
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    args.out.mkdir(parents=True, exist_ok=True)
    best = {"f1": -1.0}
    for epoch in range(1, args.epochs + 1):
        model.train()
        total, n = 0.0, 0
        for enc, y, idx in batches(train_rows, True):
            n += 1
            with torch.autocast(device.type, enabled=use_amp):
                logits = model(**enc).logits
                loss = torch.nn.functional.cross_entropy(logits, y)
            if teacher is not None:
                # 선생님 확률 p → 로짓 log(p/(1-p))를 온도 T로 부드럽게, 학생도 T로 나눠 KL·T²
                tp = teacher[idx]
                t_logit = torch.tensor(np.log(tp / (1 - tp)) / args.temperature, device=device)
                soft = torch.stack(
                    [torch.sigmoid(-t_logit), torch.sigmoid(t_logit)], dim=-1
                ).float()
                s_logp = torch.log_softmax(logits.float() / args.temperature, dim=-1)
                kd = torch.nn.functional.kl_div(s_logp, soft, reduction="batchmean")
                loss = args.alpha * loss.float() + (1 - args.alpha) * kd * args.temperature**2
            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            total += loss.item()
        model.eval()
        probs, labels = [], []
        with torch.no_grad():
            for enc, y, _ in batches(valid_rows, False):
                p = torch.softmax(model(**enc).logits.float(), dim=-1)[:, 1]
                probs += p.cpu().tolist()
                labels += y.cpu().tolist()
        m = binary_metrics(probs, labels, DEFAULT_THRESHOLD)
        print(
            f"에폭 {epoch}: 학습 손실 {total / n:.4f} · 검증 F1 {m['f1']} · "
            f"정밀도 {m['precision']} · 재현율 {m['recall']} · "
            f"정상 오탐 {m['falsePositiveRate']}"
        )
        if m["f1"] > best["f1"]:
            best = {**m, "epoch": epoch}
            model.save_pretrained(args.out, safe_serialization=True)
            tokenizer.save_pretrained(args.out)
            np.savez_compressed(
                args.out / "valid_probs.npz",
                probs=np.array(probs, dtype=np.float32),
                labels=np.array(labels, dtype=np.int8),
            )
    sizes = {"train": len(train_rows), "valid": len(valid_rows)}
    kid = sum(1 for r in train_rows if r.get("source") == KID_SOURCE_NAME)
    if kid:
        sizes["kidWritten"] = kid  # 반복 포함 줄 수(kid_data.py)
    info = build_train_info(
        base_revision=base_revision,
        args=args,
        sizes=sizes,
        best_epoch=best["epoch"],
        valid={k: v for k, v in best.items() if k != "epoch"},
    )
    if teacher is not None:
        t = np.load(args.teacher)
        info["distill"] = {
            "teachers": [str(x) for x in t["models"]],
            "alpha": args.alpha,
            "temperature": args.temperature,
        }
    parent_info = pathlib.Path(args.model) / "train_info.json"
    if parent_info.is_file():  # 로컬 모델에서 이어 학습: 원래 기본 모델·출처를 이어받음
        parent = json.loads(parent_info.read_text(encoding="utf-8"))
        info["baseModel"] = parent["baseModel"]
        info["baseRevision"] = parent["baseRevision"]
        info["initFrom"] = {
            "model": pathlib.Path(args.model).name,
            "trainedAt": parent.get("trainedAt"),
        }
    text = json.dumps(info, ensure_ascii=False, indent=2)
    (args.out / "train_info.json").write_text(text, encoding="utf-8")
    problems = check_artifact(args.out)
    note = f" · 확인 필요: {problems}" if problems else ""
    print(f"가장 좋은 에폭 {best['epoch']} 저장 → {args.out}{note}")
    return args.out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=pathlib.Path("data/processed"), type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--model", default=BASE_MODEL)
    ap.add_argument("--revision", default=None, help="허브 커밋 해시(재현용, 비우면 최신)")
    ap.add_argument("--max-length", default=MAX_LENGTH, type=int)
    ap.add_argument("--epochs", default=3, type=int)
    ap.add_argument("--lr", default=2e-5, type=float)
    ap.add_argument("--batch-size", default=32, type=int)
    ap.add_argument("--seed", default=42, type=int)
    ap.add_argument("--limit", default=None, type=int, help="동작 확인용: 학습·검증을 앞에서 N개만")
    ap.add_argument(
        "--teacher", default=None, type=pathlib.Path, help="증류: teacher_probs.py 출력 npz"
    )
    ap.add_argument("--alpha", default=0.5, type=float, help="증류: 정답 라벨 손실 비중")
    ap.add_argument("--temperature", default=2.0, type=float, help="증류: 온도")
    train(ap.parse_args(argv))


if __name__ == "__main__":
    main()
