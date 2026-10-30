"""교사 모델: 전문가 이유 문장 → 그 항목 점수 (10/30, 증류 실험 1단계)

목적
  1) 이유 문장만 보고 점수를 얼마나 맞히는가 = "근거와 점수가 얼마나 일관된가" (멘토 지적: GT 근거)
  2) 학습 답마다 '교사 점수'를 만들어 학생 모델(train.py --distill)이 같이 배우게 함

방식
  - 입력: "[항목] content_1" + 이유 문장 (학생 글은 넣지 않음, 한 줄 = 답 1개 × 항목 1개)
  - 출력: 그 항목 점수 1개 (회귀), 정답 = 두 전문가 평균
  - 분할은 train.py와 똑같이 (load + --aihub-split) → 학생 모델과 학습·평가 글이 정확히 같음
  - 학습 답(TL)을 K등분해 서로 예측 → 학습 답에도 '외우지 않은' 교사 점수 (OOF)
  - 평가 답(VL)은 K개 교사 예측 평균 → 교사 성적 (근거-점수 일관성)
  - --agree-only: 두 전문가 점수가 같은 칸만으로 교사 학습 (예측은 전체 칸)
  - 이유 문장의 #@...# 표시는 정제와 같은 규칙으로 "○○"

출력 (커밋 금지)
  results/teacher/teacher_<dataset>[_agree].csv      항목별 교사 성적 (숫자만)
  checkpoints/teacher/<이름>/teacher_preds.csv.gz     answer_id × 9항목 교사 점수 (train.py --distill 입력)

실행 (RunPod):
  uv run python scripts/train_teacher.py --dataset descriptive --data-dir data/clean
  uv run python scripts/train_teacher.py --dataset descriptive --data-dir data/clean --agree-only
"""

import argparse
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from baseline import ITEMS
from clean_data import DEFAULT_MARKER
from torch.utils.data import DataLoader
from train import aihub_split, load, set_seed
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    get_linear_schedule_with_warmup,
)

M2 = Path(__file__).resolve().parent.parent
FEEDBACK = {"descriptive": "서술형_이유.csv.gz", "essay": "논술형_이유.csv.gz"}


def make_rows(answers: pd.DataFrame, fb: pd.DataFrame) -> pd.DataFrame:
    """답 표(점수) + 이유 표(문장) → 답 1개 × 항목 1개 한 줄"""
    long = []
    for it in ITEMS:
        part = answers[["answer_id", "split_new", f"{it}_r1", f"{it}_r2"]].copy()
        part.columns = ["answer_id", "split_new", "r1", "r2"]
        part["item"] = it
        long.append(part)
    long = pd.concat(long, ignore_index=True)
    long["y"] = (long["r1"] + long["r2"]) / 2
    rows = long.merge(fb[["answer_id", "item", "feedback"]], on=["answer_id", "item"])
    return rows.reset_index(drop=True)


def loader(rows, tok, bs, shuffle, max_len):
    enc = tok(
        ("[항목] " + rows["item"]).tolist(),
        rows["feedback"].tolist(),
        truncation="only_second",
        max_length=max_len,
    )
    data = [
        {
            "input_ids": enc["input_ids"][i],
            "attention_mask": enc["attention_mask"][i],
            "labels": [float(rows["y"].iat[i])],
        }
        for i in range(len(rows))
    ]
    order = None
    if not shuffle:
        order = np.argsort([len(d["input_ids"]) for d in data], kind="stable")
        data = [data[i] for i in order]
    dl = DataLoader(
        data,
        batch_size=bs,
        shuffle=shuffle,
        collate_fn=DataCollatorWithPadding(tok, pad_to_multiple_of=8),
    )
    dl.order = order
    return dl


@torch.no_grad()
def predict(model, dl, dev):
    model.eval()
    out = []
    for b in dl:
        with torch.autocast(
            device_type=dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"
        ):
            out.append(
                model(
                    input_ids=b["input_ids"].to(dev),
                    attention_mask=b["attention_mask"].to(dev),
                )
                .logits.float()
                .cpu()
                .numpy()[:, 0]
            )
    raw = np.concatenate(out)
    if dl.order is not None:
        back = np.empty_like(raw)
        back[dl.order] = raw
        raw = back
    return raw


def train_one(rows, args, dev, tok):
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, num_labels=1, problem_type="regression", ignore_mismatched_sizes=True
    ).to(dev)
    head = [
        m
        for m in model.modules()
        if isinstance(m, torch.nn.Linear) and m.out_features == 1
    ][-1]
    with torch.no_grad():
        head.bias.fill_(float(rows["y"].mean()))
    dl = loader(rows, tok, args.batch_size, True, args.max_length)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = len(dl) * args.epochs
    sch = get_linear_schedule_with_warmup(opt, int(steps * 0.1), steps)
    start = time.time()
    for ep in range(1, args.epochs + 1):
        model.train()
        for step, b in enumerate(dl, 1):
            b = {k: v.to(dev) for k, v in b.items()}
            with torch.autocast(
                device_type=dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"
            ):
                logits = model(
                    input_ids=b["input_ids"], attention_mask=b["attention_mask"]
                ).logits
            loss = torch.nn.functional.mse_loss(logits.float(), b["labels"])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sch.step()
            opt.zero_grad()
            if step % 500 == 0:
                print(
                    f"    에폭 {ep} 스텝 {step}/{len(dl)} loss {loss.item():.3f} ({(time.time() - start) / 60:.1f}분)"
                )
    return model


def metrics(rows: pd.DataFrame, pred: np.ndarray, name: str) -> list[dict]:
    out = []
    for it in ITEMS:
        m = (rows["item"] == it).to_numpy()
        y, p = rows["y"].to_numpy()[m], pred[m]
        r1, r2 = rows["r1"].to_numpy()[m], rows["r2"].to_numpy()[m]
        out.append(
            {
                "eval": name,
                "item": it,
                "n": int(m.sum()),
                "teacher_pearson": round(float(np.corrcoef(p, y)[0, 1]), 3),
                "teacher_mae": round(float(np.abs(p - y).mean()), 3),
                "teacher_vs_r1": round(float(np.corrcoef(p, r1)[0, 1]), 3),
                "teacher_vs_r2": round(float(np.corrcoef(p, r2)[0, 1]), 3),
                "rater_r1_vs_r2": round(float(np.corrcoef(r1, r2)[0, 1]), 3),
            }
        )
    return out


def main():
    ap = argparse.ArgumentParser(description="교사 모델: 이유 문장 → 항목 점수")
    ap.add_argument("--dataset", choices=list(FEEDBACK), default="descriptive")
    ap.add_argument("--model", default="klue/roberta-base")
    ap.add_argument("--data-dir", type=Path, default=M2 / "data" / "clean")
    ap.add_argument(
        "--feedback-dir",
        type=Path,
        default=M2 / "data",
        help="build_feedback.py 출력이 있는 폴더",
    )
    ap.add_argument("--split-dir", type=Path, default=M2 / "splits")
    ap.add_argument("--split-seed", type=int, default=42)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--folds", type=int, default=2)
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--max-length", type=int, default=256)
    ap.add_argument(
        "--agree-only",
        action="store_true",
        help="두 전문가 점수가 같은 칸만으로 교사 학습 (예측은 전체 칸)",
    )
    ap.add_argument("--limit", type=int, default=0, help="답 N개만 (동작 확인용)")
    args = ap.parse_args()
    set_seed(args.seed)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if dev.type == "cuda":
        torch.backends.cuda.matmul.allow_tf32 = True

    # train.py와 같은 읽기·분할 → 학생 모델과 같은 학습/검증/평가 글
    ns = argparse.Namespace(
        dataset=args.dataset,
        data_dir=args.data_dir,
        split_dir=args.split_dir,
        split_seed=args.split_seed,
        extra_adult=False,
    )
    answers = aihub_split(load(ns), args.split_seed)
    answers["answer_id"] = answers["answer_id"].astype(str)
    if args.limit:
        answers = answers.sample(n=args.limit, random_state=args.seed)
    fb = pd.read_csv(args.feedback_dir / FEEDBACK[args.dataset])
    fb["answer_id"] = fb["answer_id"].astype(str)
    fb["feedback"] = (
        fb["feedback"].fillna("").str.replace(DEFAULT_MARKER, "○○", regex=True)
    )
    rows = make_rows(answers, fb)
    tl = rows[rows["split_new"] != "test"].reset_index(drop=True)
    vl = rows[rows["split_new"] == "test"].reset_index(drop=True)
    print(
        f"교사 학습용(TL) {len(tl):,}줄 / 평가용(VL) {len(vl):,}줄 (답×항목), 이유 문장 짝 못 찾은 답×항목 {len(answers) * len(ITEMS) - len(rows):,}"
    )

    ids = np.sort(tl["answer_id"].unique())
    fold_of = dict(
        zip(
            np.random.RandomState(args.seed).permutation(ids),
            np.arange(len(ids)) % args.folds,
        )
    )
    tl["fold"] = tl["answer_id"].map(fold_of)
    tok = AutoTokenizer.from_pretrained(args.model)
    oof = np.full(len(tl), np.nan)
    vl_preds = []
    start = time.time()
    for k in range(args.folds):
        fit = tl[tl["fold"] != k]
        if args.agree_only:
            fit = fit[fit["r1"] == fit["r2"]]
        print(
            f"\n== 교사 {k + 1}/{args.folds}: 학습 {len(fit):,}줄 ({(time.time() - start) / 60:.1f}분)"
        )
        model = train_one(fit.reset_index(drop=True), args, dev, tok)
        hold = tl["fold"] == k
        oof[hold.to_numpy()] = predict(
            model, loader(tl[hold].reset_index(drop=True), tok, 256, False, args.max_length), dev
        )
        vl_preds.append(predict(model, loader(vl, tok, 256, False, args.max_length), dev))
        del model
        torch.cuda.empty_cache()
    vl_pred = np.mean(vl_preds, axis=0)

    tag = f"{args.dataset}{'_agree' if args.agree_only else ''}"
    res = pd.DataFrame(metrics(vl, vl_pred, "VL(평가)") + metrics(tl, oof, "TL(교차 예측)"))
    (M2 / "results" / "teacher").mkdir(parents=True, exist_ok=True)
    res.to_csv(M2 / "results" / "teacher" / f"teacher_{tag}.csv", index=False)

    # 학생 증류용: answer_id × 9항목 (TL은 교차 예측, VL도 같이 저장하지만 학생 학습엔 TL만 씀)
    allp = pd.concat(
        [
            tl[["answer_id", "item"]].assign(pred=oof),
            vl[["answer_id", "item"]].assign(pred=vl_pred),
        ]
    )
    wide = allp.pivot(index="answer_id", columns="item", values="pred").reset_index()
    out_dir = M2 / "checkpoints" / "teacher" / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    wide.to_csv(out_dir / "teacher_preds.csv.gz", index=False)
    print(
        f"\n교사 성적 (정답 = 두 전문가 평균, {(time.time() - start) / 60:.1f}분):\n{res.to_string(index=False)}"
    )
    print(f"교사 점수 저장: {out_dir / 'teacher_preds.csv.gz'}")


if __name__ == "__main__":
    main()
