"""새 문항 보정 곡선: 선생님이 새 문항의 답 k개를 채점해 주면 성능이 얼마나 오르나.

처음 보는 지시문(평가용 문항)마다 아래를 따로 한다.
  1. 그 문항 답 중 max(k)개를 "선생님이 채점한 답"으로 뽑는다 (점수대를 고르게, 16 ⊂ 32 ⊂ 64 ⊂ 128)
  2. 나머지 답 = 평가용. 모든 k가 같은 평가용 답으로 비교된다
  3. k=0: 이미 학습된 모델(기준)을 그대로 평가
  4. k>0: 기준 모델을 처음부터 다시 불러 그 문항 답 k개로만 추가 학습 → 평가
문항마다 모델을 따로 보정한다 (선생님 한 명이 자기 문항 하나를 채점하는 상황).

주의
- 보정 학습은 에폭·학습률을 고정한다. 평가용 답으로 에폭을 고르면 누수라서.
  설정을 고르고 싶으면 --split valid 로 검증용 문항에서 같은 실험을 돌려 정하고, 그 설정으로 test를 한 번만 돌린다
- 보고할 때 "학습 답 k개 = 선생님 채점량 k개"다 (검증용 답은 따로 쓰지 않음)
- 연구 조사 6-2: 다른 연구의 개선폭을 우리 기대치로 쓰지 않는다. 이 실험이 그 숫자를 우리 데이터로 재는 것

실행 (RunPod):
    uv run python scripts/calibrate.py --dataset descriptive --with-keyword \
        --model /workspace/models/m2-klue-narrative/2.0
    uv run python scripts/calibrate.py --dataset essay --model /workspace/models/m2-klue-essay/2.0
동작 확인 (PC CPU, 1~3분):
    uv run python scripts/calibrate.py --dataset descriptive --with-keyword \
        --model <2.0 폴더> --limit-prompts 1 --ks 16 --epochs 1 --eval-limit 40
결과: results/calibrate/calib_<이름>.csv (k별·항목별 지표), calib_<이름>_summary.csv, preds_<이름>.npz (커밋 금지)
"""

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from baseline import DATASETS, ITEMS, gold
from report_table import expert_rows, model_rows
from train import M2_DIR, load, make_loader, pick_device, predict, set_seed
from transformers import AutoModelForSequenceClassification, AutoTokenizer


def balanced_pool(part: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """점수대(총점 반올림)마다 돌아가며 하나씩 뽑는다. 앞에서 k개를 잘라도 점수대가 고르게 섞인다."""
    rng = np.random.RandomState(seed)
    g = gold(part, "hol")
    groups = [list(rng.permutation(np.where(g == s)[0])) for s in sorted(set(g))]
    picked = []
    while len(picked) < min(n, len(part)):
        for grp in groups:
            if grp and len(picked) < n:
                picked.append(grp.pop())
    return part.iloc[picked]


def train_on(model, loader, device, epochs, lr, amp_dtype):
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    for _ in range(epochs):
        for batch in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            with torch.autocast(
                device_type=device.type,
                dtype=amp_dtype or torch.float32,
                enabled=amp_dtype is not None,
            ):
                logits = model(
                    input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]
                ).logits
            loss = torch.nn.functional.mse_loss(logits.float(), batch["labels"])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            opt.zero_grad()


def main() -> None:
    p = argparse.ArgumentParser(description="M2 새 문항 보정 곡선")
    p.add_argument("--dataset", choices=list(DATASETS), default="descriptive")
    p.add_argument(
        "--model",
        required=True,
        help="기준 모델 폴더 (예: models/m2-klue-narrative/2.0)",
    )
    p.add_argument("--with-keyword", action="store_true")
    p.add_argument(
        "--split",
        choices=["test", "valid"],
        default="test",
        help="valid로 설정(에폭·학습률)을 먼저 고르고 test는 한 번만",
    )
    p.add_argument("--ks", type=int, nargs="+", default=[16, 32, 64, 128])
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--eval-batch-size", type=int, default=64)
    p.add_argument("--max-length", type=int, default=512)
    p.add_argument("--seed", type=int, default=42, help="채점할 답 뽑기·학습 시드")
    p.add_argument("--split-seed", type=int, default=42)
    p.add_argument(
        "--limit-prompts", type=int, default=0, help="문항 N개만 (동작 확인용)"
    )
    p.add_argument(
        "--eval-limit", type=int, default=0, help="문항마다 평가 답 N개만 (동작 확인용)"
    )
    p.add_argument("--device", default="auto")
    p.add_argument("--data-dir", type=Path, default=M2_DIR / "data")
    p.add_argument("--split-dir", type=Path, default=M2_DIR / "splits")
    p.add_argument("--result-dir", type=Path, default=M2_DIR / "results" / "calibrate")
    args = p.parse_args()
    args.extra_adult = False  # train.load 가 쓰는 옵션

    set_seed(args.seed)
    device = pick_device(args.device)
    amp_dtype = None
    if device.type == "cuda":
        amp_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else None
        torch.backends.cuda.matmul.allow_tf32 = True
    ks = sorted(set(args.ks))
    input_opts = {"with_keyword": args.with_keyword}
    tokenizer = AutoTokenizer.from_pretrained(args.model)

    df = load(args)
    target = df[df["split_new"] == args.split]
    prompt_ids = sorted(target["prompt_id"].unique())
    if args.limit_prompts:
        prompt_ids = prompt_ids[: args.limit_prompts]
    print(
        f"{args.dataset} {args.split} 문항 {len(prompt_ids)}개, k = {ks}, 에폭 {args.epochs}, lr {args.lr}"
    )

    eval_parts, preds = [], {k: [] for k in [0] + ks}
    start = time.time()
    for n, pid in enumerate(prompt_ids, 1):
        part = target[target["prompt_id"] == pid].reset_index(drop=True)
        pool = balanced_pool(part, max(ks), args.seed)
        ev = part.drop(index=pool.index).reset_index(drop=True)
        if args.eval_limit:
            ev = ev.sample(
                n=min(args.eval_limit, len(ev)), random_state=args.seed
            ).reset_index(drop=True)
        if len(ev) < 20:
            print(f"  {pid}: 평가 답 {len(ev)}개뿐이라 건너뜀")
            continue
        ev_loader = make_loader(
            ev,
            tokenizer,
            args.max_length,
            args.eval_batch_size,
            False,
            "reg",
            **input_opts,
        )
        for k in [0] + ks:
            model = AutoModelForSequenceClassification.from_pretrained(args.model).to(
                device
            )
            if k:
                tr = pool.iloc[:k]
                loader = make_loader(
                    tr,
                    tokenizer,
                    args.max_length,
                    args.batch_size,
                    True,
                    "reg",
                    **input_opts,
                )
                train_on(model, loader, device, args.epochs, args.lr, amp_dtype)
            with torch.no_grad():
                preds[k].append(predict(model, ev_loader, device))
            del model
            if device.type == "cuda":
                torch.cuda.empty_cache()
        eval_parts.append(ev)
        print(
            f"  [{n}/{len(prompt_ids)}] {pid}: 채점 풀 {len(pool)}개, 평가 {len(ev)}개 ({(time.time() - start) / 60:.1f}분)"
        )

    ev_all = pd.concat(eval_parts, ignore_index=True)
    name = f"{args.dataset}_{args.split}_s{args.seed}_ep{args.epochs}_lr{args.lr:g}"
    rows = []
    for k in [0] + ks:
        raw = np.concatenate(preds[k])
        for r in model_rows(ev_all, raw, f"k{k}"):
            rows.append({"k": k, **r})
    for r in expert_rows(ev_all):
        rows.append({"k": "expert", **r})
    table = pd.DataFrame(rows).round(3)

    # 문항별 총점 상관 평균 (문항 안에서 순서를 잘 세우나)
    per_prompt = []
    for k in [0] + ks:
        raw = np.concatenate(preds[k])[:, 0]
        g = ((ev_all["hol_r1"] + ev_all["hol_r2"]) / 2).to_numpy()
        rs = [
            np.corrcoef(
                raw[(ev_all["prompt_id"] == pid).to_numpy()],
                g[(ev_all["prompt_id"] == pid).to_numpy()],
            )[0, 1]
            for pid in ev_all["prompt_id"].unique()
        ]
        per_prompt.append(
            {"k": k, "per_prompt_hol_pearson_mean": round(float(np.nanmean(rs)), 3)}
        )

    # 활성화 기준 (사람 대비 저하 ≤ 0.10) 통과 항목 수, QWK·Pearson 각각
    exp = table[table["k"] == "expert"].set_index("item")
    summary = []
    for k in [0] + ks:
        m = table[table["k"] == k].set_index("item")
        summary.append(
            {
                "k": k,
                "hol_pearson": m.loc["hol", "pearson"],
                "hol_mae": m.loc["hol", "mae"],
                "hol_qwk": m.loc["hol", "qwk"],
                "pass_qwk": int(((exp["qwk"] - m["qwk"]) <= 0.10).sum()),
                "pass_pearson": int(((exp["pearson"] - m["pearson"]) <= 0.10).sum()),
                **next(x for x in per_prompt if x["k"] == k),
            }
        )
    summary = pd.DataFrame(summary)

    args.result_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.result_dir / f"calib_{name}.csv", index=False)
    summary.to_csv(args.result_dir / f"calib_{name}_summary.csv", index=False)
    np.savez(
        args.result_dir / f"preds_{name}.npz",
        ids=ev_all["answer_id"].to_numpy(dtype=str),
        **{f"k{k}": np.concatenate(preds[k]) for k in [0] + ks},
    )
    print(
        f"\n평가 답 {len(ev_all)}개 (문항 {ev_all['prompt_id'].nunique()}개). 전문가끼리 총점 Pearson {exp.loc['hol', 'pearson']}"
    )
    print(summary.to_string(index=False))
    print(f"\n저장: {args.result_dir / f'calib_{name}.csv'}")


if __name__ == "__main__":
    main()
