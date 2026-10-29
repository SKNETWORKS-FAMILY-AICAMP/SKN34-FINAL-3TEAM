"""AI Hub 545 에세이(채점자 3명)로 학습해 '학습한 주제'와 '처음 보는 주제' 성적을 한 번에 본다.

10/29 실험용 (계획 밖, 수빈 님 승인 14:32). 데이터: build_545.py 출력 data/에세이545_답안.csv.gz
- 50개 주제 중 10개를 시드로 떼어 '처음 보는 주제'로 둔다 (학습에 한 건도 안 씀)
- 학습: TL 중 나머지 40개 주제 (5%는 검증용, 가장 좋은 에폭 고르기)
- 평가 ① 같은 주제: VL 중 40개 주제 / 평가 ② 처음 보는 주제: 10개 주제의 TL+VL 전부
- 입력: "[학년] 초5 [글 종류] 설명글" + 학생 글 (지시문 문장은 넣지 않음, 10/29 서술형 문장 외움 확인 때문)
- 출력: 구성·내용·표현 3개 영역 (각 채점자 세부 점수 평균, 0~3), 정답 = 채점자 3명 평균
- 비교: 채점자 1명 vs 나머지 2명 평균 (같은 평가 글에서)
결과는 숫자만 출력·저장 (results/e545/). 학생 글은 출력하지 않음.

실행 (RunPod): uv run python scripts/train_545.py
"""

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    get_linear_schedule_with_warmup,
)

M2 = Path(__file__).resolve().parent.parent
AREAS = ["org", "cont", "exp"]


def target(df):
    return np.stack(
        [df[[f"{a}_r{r}" for r in (1, 2, 3)]].mean(1) for a in AREAS], 1
    ).astype("float32")


def loader(df, tok, bs, shuffle, max_len):
    first = ("[학년] " + df["grade"] + " [글 종류] " + df["essay_type"]).tolist()
    enc = tok(first, df["text"].tolist(), truncation="only_second", max_length=max_len)
    y = target(df)
    rows = [
        {
            "input_ids": enc["input_ids"][i],
            "attention_mask": enc["attention_mask"][i],
            "labels": y[i].tolist(),
        }
        for i in range(len(df))
    ]
    order = None
    if not shuffle:
        order = np.argsort([len(r["input_ids"]) for r in rows], kind="stable")
        rows = [rows[i] for i in order]
    dl = DataLoader(
        rows,
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
                .numpy()
            )
    raw = np.concatenate(out)
    if dl.order is not None:
        back = np.empty_like(raw)
        back[dl.order] = raw
        raw = back
    return raw


def scores(df, pred, name):
    """영역별 + 총점(3개 영역 평균) Pearson·MAE, 같은 글의 채점자끼리 비교 포함."""
    y = target(df)
    rows = []
    for j, a in enumerate(AREAS + ["total"]):
        g = y[:, j] if a != "total" else y.mean(1)
        p = pred[:, j] if a != "total" else pred.mean(1)
        if a == "total":
            r = [df[[f"{x}_r{k}" for x in AREAS]].mean(1).to_numpy() for k in (1, 2, 3)]
        else:
            r = [df[f"{a}_r{k}"].to_numpy() for k in (1, 2, 3)]
        one_vs_two = np.mean(
            [
                np.corrcoef(r[k], np.mean([r[m] for m in range(3) if m != k], 0))[0, 1]
                for k in range(3)
            ]
        )
        one_vs_one = np.mean(
            [
                np.corrcoef(r[0], r[1])[0, 1],
                np.corrcoef(r[0], r[2])[0, 1],
                np.corrcoef(r[1], r[2])[0, 1],
            ]
        )
        rows.append(
            {
                "eval": name,
                "area": a,
                "n": len(df),
                "model_pearson": round(float(np.corrcoef(p, g)[0, 1]), 3),
                "model_mae": round(float(np.abs(p - g).mean()), 3),
                "rater_1v2avg": round(float(one_vs_two), 3),
                "rater_1v1": round(float(one_vs_one), 3),
            }
        )
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="klue/roberta-base")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--max-length", type=int, default=512)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-new", type=int, default=10, help="처음 보는 주제로 뗄 주제 수")
    ap.add_argument(
        "--add-71819",
        action="store_true",
        help="AI Hub 71819 논술형(89문항)을 학습에만 추가: 구성=organization_1·2, 내용=task_1·content_1~3, 표현=expression_1·2, 1~5점을 0~3점으로",
    )
    args = ap.parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if dev.type == "cuda":
        torch.backends.cuda.matmul.allow_tf32 = True

    df = pd.read_csv(M2 / "data" / "에세이545_답안.csv.gz")
    topics = np.sort(df["subject"].unique())
    new = set(np.random.RandomState(args.seed).permutation(topics)[: args.n_new])
    tl = df[(df["split"] == "TL") & ~df["subject"].isin(new)]
    pick = np.random.RandomState(args.seed).rand(len(tl)) < 0.05
    sets = {
        "train": tl[~pick].reset_index(drop=True),
        "valid": tl[pick].reset_index(drop=True),
        "same_topic": df[(df["split"] == "VL") & ~df["subject"].isin(new)].reset_index(
            drop=True
        ),
        "new_topic": df[df["subject"].isin(new)].reset_index(drop=True),
    }
    tag = ""
    if args.add_71819:
        # 평가는 545 그대로, 학습에만 71819를 더해 주제 수를 늘림 (50 → 50+89, 10/29 처음 보는 주제 0.510 개선 시도)
        e = pd.read_csv(M2 / "data" / "논술형_답안.csv.gz")
        groups = {
            "org": ["organization_1", "organization_2"],
            "cont": ["task_1", "content_1", "content_2", "content_3"],
            "exp": ["expression_1", "expression_2"],
        }
        add = pd.DataFrame(
            {
                "grade": e["grade"],
                "essay_type": e["essay_type"],
                "text": e["text"],
                "subject": "71819_" + e["prompt_id"].astype(str),
            }
        )
        for a, cols in groups.items():
            for k in (1, 2):
                add[f"{a}_r{k}"] = (e[[f"{c}_r{k}" for c in cols]].mean(1) - 1) * 0.75
            # 채점자 2명이라 3번째 칸은 두 명 평균 (정답 = 두 명 평균이 됨)
            add[f"{a}_r3"] = (add[f"{a}_r1"] + add[f"{a}_r2"]) / 2
        sets["train"] = pd.concat([sets["train"], add], ignore_index=True)
        tag = "_add71819"
        print(
            f"71819 논술형 {len(add):,}건 (문항 {e['prompt_id'].nunique()}개)을 학습에 추가"
        )
    print(
        {k: len(v) for k, v in sets.items()},
        f"주제 {len(topics)}개 중 처음 보는 주제 {len(new)}개",
    )

    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model,
        num_labels=3,
        problem_type="regression",
        ignore_mismatched_sizes=True,
    ).to(dev)
    head = [
        m
        for m in model.modules()
        if isinstance(m, torch.nn.Linear) and m.out_features == 3
    ][-1]
    with torch.no_grad():
        head.bias.copy_(torch.tensor(target(sets["train"]).mean(0)))
    dls = {
        k: loader(
            v,
            tok,
            args.batch_size if k == "train" else 64,
            k == "train",
            args.max_length,
        )
        for k, v in sets.items()
    }
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = len(dls["train"]) * args.epochs
    sch = get_linear_schedule_with_warmup(opt, int(steps * 0.1), steps)
    out_dir = M2 / "checkpoints" / f"e545{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    best, start = -1.0, time.time()
    for ep in range(1, args.epochs + 1):
        model.train()
        for step, b in enumerate(dls["train"], 1):
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
            if step % 200 == 0:
                print(
                    f"  에폭 {ep} 스텝 {step}/{len(dls['train'])} loss {loss.item():.3f} ({(time.time() - start) / 60:.1f}분)"
                )
        pv = predict(model, dls["valid"], dev)
        yv = target(sets["valid"])
        r = float(np.mean([np.corrcoef(pv[:, j], yv[:, j])[0, 1] for j in range(3)]))
        print(f"에폭 {ep} 검증 평균 상관 {r:.3f} ({(time.time() - start) / 60:.1f}분)")
        if r > best:
            best = r
            model.save_pretrained(out_dir)
            tok.save_pretrained(out_dir)
    model = AutoModelForSequenceClassification.from_pretrained(out_dir).to(dev)
    rows = []
    for name in ["same_topic", "new_topic"]:
        p = predict(model, dls[name], dev)
        rows += scores(sets[name], p, name)
        elem = sets[name]["grade"].str.startswith("초").to_numpy()
        rows += scores(sets[name][elem].reset_index(drop=True), p[elem], name + "_elem")
    res = pd.DataFrame(rows)
    (M2 / "results" / "e545").mkdir(parents=True, exist_ok=True)
    res.to_csv(M2 / "results" / "e545" / f"e545_seed{args.seed}{tag}.csv", index=False)
    print(
        f"\n545 에세이 결과 (정답 = 채점자 3명 평균, 학습 {(time.time() - start) / 60:.1f}분):\n{res.to_string(index=False)}"
    )


if __name__ == "__main__":
    main()
