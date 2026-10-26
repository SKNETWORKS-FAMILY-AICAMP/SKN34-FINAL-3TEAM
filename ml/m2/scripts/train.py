"""roberta 계열 모델 파인튜닝 (M2 항목 점수).

입력: [학년] + [지시문] + [학생 글]  (서비스 API도 {prompt, text, grade}를 넘김)
출력: 9개 점수 (총점 + 8개 항목). 점수를 숫자로 맞히는 회귀로 학습하고 반올림한다
      (기준선에서 Ridge 회귀가 대체로 나았고, QWK는 점수 순서를 중요하게 봄)
정답: 두 전문가 평균 (반올림 전, 예: 3.5)

- 장치: GPU(CUDA)가 있으면 GPU, 없으면 CPU를 자동으로 고른다 (--device로 강제 가능)
- 검증용(valid)으로 매 에폭 QWK를 재서 가장 좋은 에폭의 가중치만 저장한다
- 평가용(test) 성적은 학습이 끝난 뒤 한 번만 낸다 (baseline.py와 같은 형식)
- 가중치는 checkpoints/에 저장 (커밋 금지)

로컬에서 동작 확인 (CPU, 몇 분):
    uv run python scripts/train.py --model klue/roberta-base --limit 200 --epochs 1
RunPod (GPU):
    uv run python scripts/train.py --model klue/roberta-base
    uv run python scripts/train.py --model xlm-roberta-base
"""

import argparse
import json
import random
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from baseline import DATASETS, ITEMS, evaluate, score_table, top_score
from torch.utils.data import DataLoader
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

M2_DIR = Path(__file__).resolve().parent.parent
# 작은 그룹(학년별 등)에서 없는 점수를 예측하면 sklearn이 경고를 냄. 결과에는 영향 없음
warnings.filterwarnings("ignore", message="y_pred contains classes not in y_true")


def pick_device(name: str) -> torch.device:
    if name == "auto":
        name = "cuda" if torch.cuda.is_available() else "cpu"
    return torch.device(name)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def load(args: argparse.Namespace) -> pd.DataFrame:
    answer_file, prompt_file = DATASETS[args.dataset]
    df = pd.read_csv(args.data_dir / answer_file)
    prompts = pd.read_csv(args.data_dir / prompt_file)
    split = pd.read_csv(args.split_dir / f"{args.dataset}_split_seed{args.seed}.csv")
    df = df.merge(prompts[["prompt_id", "prompt", "keyword"]], on="prompt_id")
    return df.merge(split[["prompt_id", "split_new"]], on="prompt_id")


def targets(df: pd.DataFrame) -> np.ndarray:
    cols = [(df[f"{it}_r1"] + df[f"{it}_r2"]) / 2 for it in ITEMS]
    return np.stack(cols, axis=1).astype("float32")


def make_loader(df, tokenizer, max_length, batch_size, shuffle):
    # 지시문이 길어도 학생 글이 잘리도록 두 번째 문장(글)만 자름
    first = ("[학년] " + df["grade"] + " [지시문] " + df["prompt"]).tolist()
    enc = tokenizer(
        first,
        df["text"].tolist(),
        truncation="only_second",
        max_length=max_length,
        padding="max_length",
        return_tensors="pt",
    )
    y = torch.tensor(targets(df))
    rows = [
        {
            "input_ids": enc["input_ids"][i],
            "attention_mask": enc["attention_mask"][i],
            "labels": y[i],
        }
        for i in range(len(df))
    ]
    return DataLoader(rows, batch_size=batch_size, shuffle=shuffle)


@torch.no_grad()
def predict(model, loader, device) -> np.ndarray:
    model.eval()
    outs = []
    for batch in loader:
        out = model(
            input_ids=batch["input_ids"].to(device),
            attention_mask=batch["attention_mask"].to(device),
        )
        outs.append(out.logits.float().cpu().numpy())
    return np.concatenate(outs)


def to_scores(raw: np.ndarray) -> dict:
    # 숫자 → 반올림 → 항목별 점수 범위로 자르기
    return {
        it: np.clip(np.floor(raw[:, i] + 0.5), 1, top_score(it)).astype(int)
        for i, it in enumerate(ITEMS)
    }


def mean_qwk(df: pd.DataFrame, raw: np.ndarray) -> float:
    scores = to_scores(raw)
    return float(np.mean([evaluate(df, it, scores[it])["qwk"] for it in ITEMS]))


def main() -> None:
    parser = argparse.ArgumentParser(description="M2 roberta 파인튜닝")
    parser.add_argument("--model", default="klue/roberta-base")
    parser.add_argument("--dataset", choices=list(DATASETS), default="descriptive")
    parser.add_argument("--data-dir", type=Path, default=M2_DIR / "data")
    parser.add_argument("--split-dir", type=Path, default=M2_DIR / "splits")
    parser.add_argument("--out-dir", type=Path, default=M2_DIR / "checkpoints")
    parser.add_argument("--result-dir", type=Path, default=M2_DIR / "results")
    parser.add_argument("--device", default="auto", help="auto / cpu / cuda")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--limit", type=int, default=0, help="세트마다 답 N개만 (동작 확인용)"
    )
    args = parser.parse_args()

    set_seed(args.seed)
    device = pick_device(args.device)
    # 허브 이름(klue/roberta-base)이면 klue_roberta-base, 로컬 폴더면 폴더 이름
    model_name = (
        Path(args.model).name
        if Path(args.model).exists()
        else args.model.replace("/", "_")
    )
    run_name = f"{model_name}_{args.dataset}_seed{args.seed}"
    print(f"장치: {device} / 모델: {args.model} / 데이터: {args.dataset}")

    df = load(args)
    sets = {}
    for name in ["train", "valid", "test"]:
        part = df[df["split_new"] == name].reset_index(drop=True)
        if args.limit:
            part = part.sample(n=min(args.limit, len(part)), random_state=args.seed)
            part = part.reset_index(drop=True)
        sets[name] = part
    print({k: len(v) for k, v in sets.items()})

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model,
        num_labels=len(ITEMS),
        problem_type="regression",
        ignore_mismatched_sizes=True,  # 출력 칸(9개 점수)은 새로 만듦
    ).to(device)

    # 점수 칸의 시작값을 공부용 평균 점수(3점 언저리)로 맞춤.
    # 0에서 시작하면 3점까지 올라오는 데만 학습을 꽤 써서, 짧게 돌리면 전부 1점이 나옴
    head = [m for m in model.modules() if isinstance(m, torch.nn.Linear)][-1]
    with torch.no_grad():
        head.bias.copy_(torch.tensor(targets(sets["train"]).mean(axis=0)))

    loaders = {
        name: make_loader(
            part, tokenizer, args.max_length, args.batch_size, name == "train"
        )
        for name, part in sets.items()
    }

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total_steps = len(loaders["train"]) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer, int(total_steps * 0.1), total_steps
    )
    use_amp = device.type == "cuda"  # GPU에서는 16비트 계산으로 빠르게

    best_qwk, best_epoch = -1.0, 0
    ckpt_dir = args.out_dir / run_name
    start = time.time()
    for epoch in range(1, args.epochs + 1):
        model.train()
        for step, batch in enumerate(loaders["train"], 1):
            batch = {k: v.to(device) for k, v in batch.items()}
            with torch.autocast(
                device_type=device.type, dtype=torch.float16, enabled=use_amp
            ):
                loss = model(**batch).loss  # 회귀라서 MSE
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            if step % 100 == 0:
                print(
                    f"  에폭 {epoch} 스텝 {step}/{len(loaders['train'])} loss {loss.item():.3f}"
                )

        q = mean_qwk(sets["valid"], predict(model, loaders["valid"], device))
        print(
            f"에폭 {epoch} 검증 평균 QWK {q:.3f} ({(time.time() - start) / 60:.1f}분)"
        )
        if q > best_qwk:
            best_qwk, best_epoch = q, epoch
            model.save_pretrained(ckpt_dir)
            tokenizer.save_pretrained(ckpt_dir)

    # 검증 기준 가장 좋았던 에폭의 가중치로 평가용 성적을 한 번만 낸다
    model = AutoModelForSequenceClassification.from_pretrained(ckpt_dir).to(device)
    preds = {
        (run_name, it): s
        for it, s in to_scores(predict(model, loaders["test"], device)).items()
    }
    test = sets["test"]
    group_cols = ["grade"] + (["essay_type"] if "essay_type" in test else [])
    table = score_table(test, preds, group_cols)
    args.result_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.result_dir / f"train_{run_name}.csv", index=False)

    info = {
        **{k: str(v) for k, v in vars(args).items()},
        "best_epoch": best_epoch,
        "best_valid_qwk": round(best_qwk, 3),
        "device": str(device),
        "minutes": round((time.time() - start) / 60, 1),
    }
    (ckpt_dir / "train_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    overall = table[table["group_by"] == "all"].set_index("item")["qwk"].reindex(ITEMS)
    print(f"\n평가용 QWK (가장 좋은 에폭 {best_epoch}):\n{overall.to_string()}")


if __name__ == "__main__":
    main()
