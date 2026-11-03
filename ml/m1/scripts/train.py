"""M1 풀이 점검 모델 학습.

입력: [문제 / 정답] + [학생 풀이]  (mathtext.model_input, 서비스와 같은 형식)
출력 3개 (손실은 더함, 라벨 없는 칸은 손실에서 뺌)
  - is_correct (2클래스)
  - has_required_error (2클래스)
  - calc_accuracy (데이터에 있는 값 그대로: 0.0 / 0.5 / 1.0, 합치지 않음)

필요 패키지: uv sync (pyproject.toml)
실행 예:
  uv run python scripts/train.py --epochs 2                       # 전체
  uv run python scripts/train.py --grades P3,P4,P5,P6,M1,M2,M3     # 서비스 대상 학년만
  uv run python scripts/train.py --limit 2000 --epochs 1          # 코드가 도는지 빠르게 확인
결과: models/ (m1.pt, meta.json, config.json, 토크나이저, 커밋 안 함)
GPU가 없으면 매우 느리다(전체 ≈ 수십 시간). Colab 등 GPU 환경을 권장.
"""

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path

from common import MODEL_DIR, WORK_DIR
from model import build_model


def read_rows(split, grades=None, limit=None, seed=0):
    with open(WORK_DIR / "records.csv", encoding="utf-8-sig") as f:
        rows = [
            r
            for r in csv.DictReader(f)
            if r["split"] == split and (not grades or r["grade"] in grades)
        ]
    if limit and len(rows) > limit:
        rows = random.Random(seed).sample(rows, limit)
    return rows


def balanced_acc(y, p):
    recs = []
    for c in set(y):
        idx = [i for i, v in enumerate(y) if v == c]
        recs.append(sum(p[i] == c for i in idx) / len(idx))
    return sum(recs) / max(len(recs), 1)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="klue/roberta-base")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max_len", type=int, default=256)
    ap.add_argument("--grades", default="", help="예: P3,P4,P5,P6,M1,M2,M3 (비우면 전체)")
    ap.add_argument("--limit", type=int, default=0, help="train 표본 수 제한 (빠른 확인용)")
    ap.add_argument("--out", default=str(MODEL_DIR))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    import torch
    from torch.utils.data import DataLoader
    from transformers import AutoModel, AutoTokenizer

    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    grades = [g for g in args.grades.split(",") if g]
    train_rows = read_rows("train", grades, args.limit, args.seed)
    val_rows = read_rows("val", grades, args.limit // 4 if args.limit else 0, args.seed)
    calc_classes = sorted({r["calc_accuracy"] for r in train_rows if r["calc_accuracy"]}, key=float)
    print(
        f"device {device} · train {len(train_rows)} · val {len(val_rows)} · "
        f"계산 클래스 {calc_classes}"
    )

    tok = AutoTokenizer.from_pretrained(args.base)

    def collate(batch):
        enc = tok(
            [r["input_a"] for r in batch],
            [r["input_b"] for r in batch],
            truncation="longest_first",
            max_length=args.max_len,
            padding=True,
            return_tensors="pt",
        )

        def lab(r, key, classes=None):
            v = r[key]
            if v in ("", "None"):
                return -100
            return classes.index(v) if classes else int(v)

        enc["y_correct"] = torch.tensor([int(r["is_correct"]) for r in batch])
        enc["y_req"] = torch.tensor([lab(r, "has_required_error") for r in batch])
        enc["y_calc"] = torch.tensor(
            [
                lab(r, "calc_accuracy", calc_classes)
                if r["calc_accuracy"] in calc_classes
                else -100
                for r in batch
            ]
        )
        return enc

    model = build_model(AutoModel.from_pretrained(args.base), len(calc_classes)).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    ce = torch.nn.CrossEntropyLoss(ignore_index=-100)
    dl = DataLoader(train_rows, batch_size=args.batch, shuffle=True, collate_fn=collate)
    vdl = DataLoader(val_rows, batch_size=args.batch * 2, collate_fn=collate)
    total = len(dl) * args.epochs
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / max(1, int(0.06 * total))) * max(0.0, (total - s) / total)
    )

    def inputs(b):
        return {
            k: b[k].to(device) for k in ("input_ids", "attention_mask", "token_type_ids") if k in b
        }

    out_dir = Path(args.out)
    best, t0 = -1.0, time.time()
    for ep in range(args.epochs):
        model.train()
        for step, b in enumerate(dl):
            lc, lr_, lk = model(**inputs(b))
            loss = (
                ce(lc, b["y_correct"].to(device))
                + ce(lr_, b["y_req"].to(device))
                + ce(lk, b["y_calc"].to(device))
            )
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            done = ep * len(dl) + step + 1
            if step % max(1, len(dl) // 20) == 0 or step == len(dl) - 1:
                el = time.time() - t0
                left = el / done * (total - done)
                print(
                    f"ep{ep} step {step + 1}/{len(dl)} loss {loss.item():.4f} "
                    f"(경과 {el / 60:.1f}분 · 남은 학습 약 {left / 60:.1f}분, 검증 제외)",
                    flush=True,
                )
        model.eval()
        ys, ps = {"c": [], "r": [], "k": []}, {"c": [], "r": [], "k": []}
        with torch.no_grad():
            for b in vdl:
                lc, lr_, lk = model(**inputs(b))
                for key, logit, y in (
                    ("c", lc, b["y_correct"]),
                    ("r", lr_, b["y_req"]),
                    ("k", lk, b["y_calc"]),
                ):
                    p = logit.argmax(-1).cpu().tolist()
                    for yy, pp in zip(y.tolist(), p, strict=False):
                        if yy != -100:
                            ys[key].append(yy)
                            ps[key].append(pp)
        val = {
            name: round(balanced_acc(ys[k], ps[k]), 4) if ys[k] else None
            for name, k in (("정답여부", "c"), ("필수과정", "r"), ("계산", "k"))
        }
        print(f"ep{ep} val 균형정확도 {val}")
        score = val["정답여부"] or 0
        if score > best:
            best = score
            out_dir.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), out_dir / "m1.pt")
            tok.save_pretrained(out_dir)
            model.enc.config.save_pretrained(out_dir)
            (out_dir / "meta.json").write_text(
                json.dumps(
                    {
                        "base": args.base,
                        "max_len": args.max_len,
                        "calc_classes": calc_classes,
                        "input_format": "mathtext.model_input-v1",
                        "grades": grades or "all",
                        "train_n": len(train_rows),
                        "val_balanced_acc": val,
                        "epoch": ep,
                        "version": f"m1-{time.strftime('%Y%m%d')}-ep{ep}",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
    print(f"저장: {out_dir} (val 정답여부 균형정확도 {best:.4f})")
    print("서비스 연결 여부는 evaluate.py 결과와 팀이 미리 정한 허용 기준으로 결정")
    return 0


if __name__ == "__main__":
    sys.exit(main())
