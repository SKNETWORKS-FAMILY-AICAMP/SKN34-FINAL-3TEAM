"""roberta 계열 모델 파인튜닝 (M2 항목 점수).

입력: [학년] + [지시문] + [학생 글]  (서비스 API도 {prompt, text, grade}를 넘김)
출력: 9개 점수 (총점 + 8개 항목)
  --head reg (기본): 점수를 소수 그대로 맞히는 회귀 (예: 3.4점). 정답은 두 전문가 평균 (예: 3.5)
      소수 그대로 RMSE·MAE·상관으로 잰다. QWK는 정수가 필요해서 반올림한 값으로 참고만
  --head cls: 1~5점 중 하나를 고르는 분류 (비교 실험용). 정답은 두 전문가 점수를 반씩 섞은 분포

- 장치: GPU(CUDA)가 있으면 GPU, 없으면 CPU를 자동으로 고른다 (--device로 강제 가능)
- 검증용(valid)으로 매 에폭 평균 상관을 재서 가장 좋은 에폭의 가중치만 저장한다
- 평가용(test) 성적은 학습이 끝난 뒤 한 번만 낸다 (baseline.py와 같은 형식)
- 가중치는 checkpoints/에 저장 (커밋 금지)

- 에폭은 길게(기본 20) 두고, 검증 9항목 평균 상관(Pearson)이 --patience 에폭 연속 안 오르면 멈춘다 (early stop)
- 에폭마다 학습 loss·검증 loss·검증 상관을 history.csv에 남긴다 → scripts/plot_curve.py로 그래프
- 배치마다 그 배치에서 가장 긴 글 길이로만 채운다 (512로 다 채우지 않아 짧은 서술형이 빨라짐)

로컬에서 동작 확인 (CPU, 몇 분):
    uv run python scripts/train.py --model klue/roberta-base --limit 200 --epochs 1
RunPod (GPU):
    uv run python scripts/train.py --model klue/roberta-base --with-keyword
    uv run python scripts/train.py --model klue/roberta-base --dataset essay --with-purpose
    uv run python scripts/train.py --model klue/roberta-base --with-keyword --with-exemplar
    uv run python scripts/train.py --dataset essay --extra-adult      # 성인 글 추가 (공부용만)
"""

import argparse
import json
import math
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
    DataCollatorWithPadding,
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
    df = df.merge(split[["prompt_id", "split_new"]], on="prompt_id")
    if args.extra_adult:
        # 71817 성인 글을 공부용에만 더함 (검증·평가는 그대로 학생 글만). build_tables.py --adult-zip로 만든 표
        adult = pd.read_csv(args.data_dir / "성인_답안.csv.gz")
        adult_p = pd.read_csv(args.data_dir / "성인_문항.csv")
        adult = adult.merge(adult_p[["prompt_id", "prompt", "keyword"]], on="prompt_id")
        adult["split_new"] = "train"
        adult["answer_id"] = adult["answer_id"].astype(str)
        df["answer_id"] = df["answer_id"].astype(str)
        print(
            f"성인 글 {len(adult):,}건 (문항 {adult['prompt_id'].nunique()}개)을 공부용에 추가"
        )
        df = pd.concat(
            [df, adult[df.columns.intersection(adult.columns)]], ignore_index=True
        )
    return df


N_CLASS = 5  # 1~5점


def targets(df: pd.DataFrame) -> np.ndarray:
    cols = [(df[f"{it}_r1"] + df[f"{it}_r2"]) / 2 for it in ITEMS]
    return np.stack(cols, axis=1).astype("float32")


def soft_targets(df: pd.DataFrame) -> np.ndarray:
    """(답안 수, 9항목, 5점) 분포. 전문가 2명의 점수에 0.5씩."""
    out = np.zeros((len(df), len(ITEMS), N_CLASS), dtype="float32")
    rows = np.arange(len(df))
    for j, it in enumerate(ITEMS):
        for r in ("r1", "r2"):
            out[rows, j, df[f"{it}_{r}"].to_numpy(int) - 1] += 0.5
    return out


def cls_loss(logits: torch.Tensor, soft: torch.Tensor) -> torch.Tensor:
    logp = torch.log_softmax(logits.float().view(-1, len(ITEMS), N_CLASS), dim=-1)
    return -(soft.view_as(logp) * logp).sum(-1).mean()


def pick_exemplars(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """문항마다 '예시 답안' 1개를 고른다 (모범 답안 필드가 없어서 고득점 학생 답으로 대신).

    고르는 기준: 두 전문가 총점 평균이 가장 높고, 같으면 8개 항목 평균이 높은 답.
    서비스에서 '선생님이 좋은 답 예시 하나를 같이 입력'하는 상황을 흉내 낸다.
    고른 답은 그 문항의 다른 답 입력에 붙이고, 학습·평가 대상에서는 뺀다 (자기 자신을 보고 채점하면 커닝).
    """
    hol = (df["hol_r1"] + df["hol_r2"]) / 2
    rest = np.mean([(df[f"{it}_r1"] + df[f"{it}_r2"]) / 2 for it in ITEMS[1:]], axis=0)
    tie = np.random.RandomState(seed).rand(len(df))  # 완전 동점이면 시드로 하나
    order = df.assign(_hol=hol, _rest=rest, _tie=tie).sort_values(
        ["prompt_id", "_hol", "_rest", "_tie"], ascending=[True, False, False, False]
    )
    best = order.groupby("prompt_id").head(1)
    return best[["prompt_id", "answer_id", "text"]].rename(columns={"text": "exemplar"})


def first_segment(df, with_keyword=False, with_purpose=False, exemplar_chars=0):
    first = "[학년] " + df["grade"] + " [지시문] " + df["prompt"]
    if with_purpose:
        # 논술형 글 목적(설명/주장/정서). 루브릭이 글 목적별로 3가지라 '어느 기준으로 채점되는지' 알려줌
        first = first + " [글 목적] " + df["essay_type"].astype(str)
    if with_keyword:
        # 문항 핵심어(채점 기준)를 같이 보여줌. 서술형만 핵심어가 있음
        first = first + " [핵심어] " + df["keyword"].fillna("").astype(str)
    if exemplar_chars:
        # 예시 답안은 앞부분만 (학생 글이 512토큰 안에 들어갈 자리를 남기려고)
        first = (
            first + " [예시 답안] " + df["exemplar"].astype(str).str[:exemplar_chars]
        )
    return first.tolist()


def make_loader(
    df, tokenizer, max_length, batch_size, shuffle, head="cls", **input_opts
):
    # 지시문·예시가 길어도 학생 글만 잘리도록 두 번째 문장(글)만 자름
    enc = tokenizer(
        first_segment(df, **input_opts),
        df["text"].tolist(),
        truncation="only_second",
        max_length=max_length,
    )
    # 분류면 (9항목 x 5점) 분포를 45칸으로 펴서, 회귀면 9개 평균 점수
    y = soft_targets(df).reshape(len(df), -1) if head == "cls" else targets(df)
    rows = [
        {
            "input_ids": enc["input_ids"][i],
            "attention_mask": enc["attention_mask"][i],
            "labels": y[i].tolist(),
        }
        for i in range(len(df))
    ]
    if not shuffle:
        # 평가할 때는 길이순으로 묶어서 빈칸 채우기를 줄임 (순서는 predict에서 되돌림)
        order = np.argsort([len(r["input_ids"]) for r in rows], kind="stable")
        rows = [rows[i] for i in order]
    else:
        order = None
    # 배치 안에서 가장 긴 글 길이까지만 채움 (예전엔 항상 512까지 채워 짧은 글도 느렸음)
    collate = DataCollatorWithPadding(tokenizer, pad_to_multiple_of=8)
    loader = DataLoader(
        rows, batch_size=batch_size, shuffle=shuffle, collate_fn=collate
    )
    loader.order = order
    return loader


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
    raw = np.concatenate(outs)
    order = getattr(loader, "order", None)
    if order is not None:  # 길이순으로 섞었던 걸 원래 답안 순서로 되돌림
        back = np.empty_like(raw)
        back[order] = raw
        raw = back
    return raw


def to_scores(raw: np.ndarray) -> dict:
    if raw.shape[1] == len(ITEMS) * N_CLASS:
        # 분류: 항목마다 가장 확률 높은 점수 (총점은 1~4점 안에서 고름)
        prob = raw.reshape(len(raw), len(ITEMS), N_CLASS)
        return {
            it: prob[:, i, : top_score(it)].argmax(-1) + 1 for i, it in enumerate(ITEMS)
        }
    # 회귀: 숫자 → 반올림 → 항목별 점수 범위로 자르기
    return {
        it: np.clip(np.floor(raw[:, i] + 0.5), 1, top_score(it)).astype(int)
        for i, it in enumerate(ITEMS)
    }


def default_cuts(item: str) -> list[float]:
    # 반올림과 같은 기준: 1.5 넘으면 2점, 2.5 넘으면 3점 ...
    return [k + 0.5 for k in range(1, top_score(item))]


def apply_cuts(raw_col: np.ndarray, cuts: list[float]) -> np.ndarray:
    return np.digitize(raw_col, cuts) + 1


def fit_cuts(df: pd.DataFrame, item: str, raw_col: np.ndarray) -> list[float]:
    """검증용에서 QWK가 가장 높아지는 점수 경계를 찾는다.

    모델은 3.4 같은 숫자를 내는데, 반올림(3.5 기준)하면 실제보다 낮게 주는 경우가 많았다
    (10/26 과소 판정 37~62%). 경계를 하나씩 앞뒤로 옮겨 보며 검증용 QWK가 오르는 쪽으로 고정한다.
    평가용은 쓰지 않는다.
    """
    cuts = default_cuts(item)
    best = evaluate(df, item, apply_cuts(raw_col, cuts))["qwk"]
    for _ in range(3):  # 경계끼리 영향을 주므로 몇 바퀴 반복
        for j in range(len(cuts)):
            low = cuts[j - 1] + 0.05 if j > 0 else 0.5
            high = cuts[j + 1] - 0.05 if j + 1 < len(cuts) else top_score(item) + 0.5
            for c in np.arange(cuts[j] - 0.5, cuts[j] + 0.51, 0.05):
                if not low <= c <= high:
                    continue
                trial = cuts.copy()
                trial[j] = round(float(c), 2)
                q = evaluate(df, item, apply_cuts(raw_col, trial))["qwk"]
                if q > best + 1e-6:
                    best, cuts = q, trial
    return cuts


def cont_scores(raw: np.ndarray) -> np.ndarray:
    """소수 점수 (답안 수, 9). 회귀는 그대로, 분류는 확률로 낸 기댓값 (예: 3점 60% 4점 40% → 3.4)."""
    if raw.shape[1] == len(ITEMS) * N_CLASS:
        z = raw.reshape(len(raw), len(ITEMS), N_CLASS)
        p = np.exp(z - z.max(-1, keepdims=True))
        p /= p.sum(-1, keepdims=True)
        return (p * np.arange(1, N_CLASS + 1)).sum(-1)
    return raw


def cont_metrics(df: pd.DataFrame, raw: np.ndarray) -> pd.DataFrame:
    """반올림 없이 소수 점수 그대로 잰 성적. 정답 = 두 전문가 평균."""
    pred, gold = cont_scores(raw), targets(df)
    rows = []
    for i, it in enumerate(ITEMS):
        err = pred[:, i] - gold[:, i]
        rows.append(
            {
                "item": it,
                "rmse": round(float(np.sqrt(np.mean(err**2))), 3),
                "mae": round(float(np.mean(np.abs(err))), 3),
                "pearson": round(float(np.corrcoef(pred[:, i], gold[:, i])[0, 1]), 3),
                "spearman": round(
                    float(
                        pd.Series(pred[:, i]).corr(
                            pd.Series(gold[:, i]), method="spearman"
                        )
                    ),
                    3,
                ),
            }
        )
    return pd.DataFrame(rows)


def mean_qwk(df: pd.DataFrame, raw: np.ndarray) -> float:
    scores = to_scores(raw)
    return float(np.mean([evaluate(df, it, scores[it])["qwk"] for it in ITEMS]))


def main() -> None:
    parser = argparse.ArgumentParser(description="M2 roberta 파인튜닝")
    parser.add_argument("--model", default="klue/roberta-base")
    parser.add_argument(
        "--head",
        choices=["reg", "cls"],
        default="reg",
        help="reg: 소수 점수 회귀 (기본) / cls: 1~5점 분류",
    )
    parser.add_argument("--dataset", choices=list(DATASETS), default="descriptive")
    parser.add_argument("--data-dir", type=Path, default=M2_DIR / "data")
    parser.add_argument("--split-dir", type=Path, default=M2_DIR / "splits")
    parser.add_argument("--out-dir", type=Path, default=M2_DIR / "checkpoints")
    parser.add_argument("--result-dir", type=Path, default=M2_DIR / "results")
    parser.add_argument("--device", default="auto", help="auto / cpu / cuda")
    parser.add_argument(
        "--epochs",
        type=int,
        default=20,
        help="최대 에폭 (early stop으로 보통 더 일찍 끝남)",
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=3,
        help="검증 평균 상관이 N 에폭 연속 안 오르면 멈춤 (0이면 끝까지)",
    )
    parser.add_argument("--eval-batch-size", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--limit", type=int, default=0, help="세트마다 답 N개만 (동작 확인용)"
    )
    parser.add_argument(
        "--with-keyword", action="store_true", help="입력에 문항 핵심어 추가 (서술형만)"
    )
    parser.add_argument(
        "--with-purpose",
        action="store_true",
        help="입력에 글 목적(설명/주장/정서) 추가 (논술형만)",
    )
    parser.add_argument(
        "--with-exemplar",
        action="store_true",
        help="문항마다 고득점 답 1개를 예시 답안으로 입력에 붙임 (그 답은 학습·평가에서 뺌)",
    )
    parser.add_argument(
        "--exemplar-chars",
        type=int,
        default=300,
        help="예시 답안을 앞에서 몇 글자까지 붙일지",
    )
    parser.add_argument(
        "--extra-adult",
        action="store_true",
        help="71817 성인 글(data/성인_답안.csv.gz)을 공부용에만 추가 (논술형만, 평가는 학생 글 그대로)",
    )
    parser.add_argument(
        "--train-prompts",
        type=int,
        default=0,
        help="공부용 문항을 N개만 씀 (문항 수에 따른 성적 확인용, 0이면 전부)",
    )
    parser.add_argument(
        "--save-preds",
        action="store_true",
        help="답안별 예측 점수를 preds.npz로 저장 (앙상블용, 커밋 금지)",
    )
    args = parser.parse_args()
    if args.with_keyword and args.dataset != "descriptive":
        parser.error(
            "--with-keyword는 서술형(descriptive)만 가능 (논술형은 핵심어 없음)"
        )
    if args.extra_adult and args.dataset != "essay":
        parser.error(
            "--extra-adult는 논술형(essay)만 (성인 글은 논술형과 같은 루브릭, 핵심어 없음)"
        )
    if args.with_purpose and args.dataset != "essay":
        parser.error(
            "--with-purpose는 논술형(essay)만 가능 (서술형은 글 목적 구분 없음)"
        )

    set_seed(args.seed)
    device = pick_device(args.device)
    # 허브 이름(klue/roberta-base)이면 klue_roberta-base, 로컬 폴더면 폴더 이름
    model_name = (
        Path(args.model).name
        if Path(args.model).exists()
        else args.model.replace("/", "_")
    )
    run_name = f"{model_name}_{args.dataset}_seed{args.seed}"
    if args.head == "cls":
        run_name += "_cls"
    if args.with_keyword:
        run_name += "_kw"
    if args.with_purpose:
        run_name += "_purpose"
    if args.with_exemplar:
        run_name += f"_ex{args.exemplar_chars}"
    if args.extra_adult:
        run_name += "_adult"
    if args.train_prompts:
        run_name += f"_p{args.train_prompts}"
    print(f"장치: {device} / 모델: {args.model} / 데이터: {args.dataset}")

    df = load(args)
    if args.with_exemplar:
        ex = pick_exemplars(df, args.seed)
        df = df[
            ~df["answer_id"].isin(ex["answer_id"])
        ]  # 예시로 쓴 답은 채점 대상에서 뺌
        df = df.merge(ex[["prompt_id", "exemplar"]], on="prompt_id")
        print(f"예시 답안 {len(ex)}개 (문항당 1개)를 학습·평가에서 빼고 입력에 붙임")
    input_opts = {
        "with_keyword": args.with_keyword,
        "with_purpose": args.with_purpose,
        "exemplar_chars": args.exemplar_chars if args.with_exemplar else 0,
    }
    sets = {}
    for name in ["train", "valid", "test"]:
        part = df[df["split_new"] == name].reset_index(drop=True)
        if args.limit:
            part = part.sample(n=min(args.limit, len(part)), random_state=args.seed)
            part = part.reset_index(drop=True)
        sets[name] = part
    if args.train_prompts:
        # 문항 순서를 시드로 한 번 섞고 앞에서 N개만 씀 (10개 ⊂ 20개 ⊂ 30개)
        ids = np.sort(sets["train"]["prompt_id"].unique())
        keep = np.random.RandomState(args.seed).permutation(ids)[: args.train_prompts]
        sets["train"] = sets["train"][sets["train"]["prompt_id"].isin(keep)]
        sets["train"] = sets["train"].reset_index(drop=True)
        print(f"공부용 문항 {len(keep)}개만 사용")
    print({k: len(v) for k, v in sets.items()})

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    n_out = len(ITEMS) * N_CLASS if args.head == "cls" else len(ITEMS)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model,
        num_labels=n_out,
        problem_type="regression",  # loss는 아래에서 직접 계산 (cls는 분포 교차 엔트로피)
        ignore_mismatched_sizes=True,  # 출력 칸은 새로 만듦
    ).to(device)

    # 점수 칸의 시작값을 공부용 평균 점수(3점 언저리)로 맞춤.
    # 0에서 시작하면 3점까지 올라오는 데만 학습을 꽤 써서, 짧게 돌리면 전부 1점이 나옴
    # 출력이 9칸인 Linear를 찾음. "맨 마지막 Linear"로 찾으면 xlm-roberta는 부품 순서가 달라서
    # 엉뚱한 층(768칸)을 잡음 (10/26 RunPod에서 에러)
    head = [
        m
        for m in model.modules()
        if isinstance(m, torch.nn.Linear) and m.out_features == n_out
    ][-1]
    with torch.no_grad():
        if args.head == "cls":
            # 시작값 = 공부용 점수 비율의 log (처음부터 '흔한 점수'를 많이 고르게)
            prior = soft_targets(sets["train"]).mean(axis=0) + 1e-4
            head.bias.copy_(
                torch.tensor(np.log(prior / prior.sum(-1, keepdims=True))).view(-1)
            )
        else:
            head.bias.copy_(torch.tensor(targets(sets["train"]).mean(axis=0)))

    loaders = {
        name: make_loader(
            part,
            tokenizer,
            args.max_length,
            args.batch_size if name == "train" else args.eval_batch_size,
            name == "train",
            head=args.head,
            **input_opts,
        )
        for name, part in sets.items()
    }
    if device.type == "cuda":
        torch.backends.cuda.matmul.allow_tf32 = (
            True  # 정확도 영향 거의 없이 행렬곱이 빨라짐
        )
        torch.backends.cudnn.allow_tf32 = True

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total_steps = len(loaders["train"]) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer, int(total_steps * 0.1), total_steps
    )
    # GPU에서는 16비트 계산으로 빠르게. bf16을 지원하면(RTX 30·40, A100 등) bf16,
    # 아니면(T4 등) fp16 + GradScaler (fp16은 작은 기울기가 0으로 사라질 수 있어서)
    amp_dtype = None
    if device.type == "cuda":
        bf16_ok = torch.cuda.is_bf16_supported(including_emulation=False)
        amp_dtype = torch.bfloat16 if bf16_ok else torch.float16
    scaler = torch.amp.GradScaler("cuda", enabled=amp_dtype == torch.float16)
    print(f"16비트 계산: {amp_dtype}")

    best_qwk, best_epoch = -1.0, 0
    ckpt_dir = args.out_dir / run_name
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    history = []
    y_valid = targets(sets["valid"])
    soft_valid = torch.tensor(soft_targets(sets["valid"]))
    start = time.time()
    for epoch in range(1, args.epochs + 1):
        model.train()
        train_losses = []
        for step, batch in enumerate(loaders["train"], 1):
            batch = {k: v.to(device) for k, v in batch.items()}
            with torch.autocast(
                device_type=device.type,
                dtype=amp_dtype or torch.float32,
                enabled=amp_dtype is not None,
            ):
                logits = model(
                    input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]
                ).logits
                if args.head == "cls":
                    loss = cls_loss(logits, batch["labels"])
                else:
                    loss = torch.nn.functional.mse_loss(logits.float(), batch["labels"])
            scaler.scale(loss).backward()  # GradScaler가 꺼져 있으면 그냥 backward
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            optimizer.zero_grad()
            train_losses.append(loss.item())
            if step % 100 == 0:
                print(
                    f"  에폭 {epoch} 스텝 {step}/{len(loaders['train'])} loss {loss.item():.3f}"
                )

        raw_v = predict(model, loaders["valid"], device)
        q = mean_qwk(sets["valid"], raw_v)
        if args.head == "cls":
            valid_loss = float(cls_loss(torch.tensor(raw_v), soft_valid))
        else:
            valid_loss = float(np.mean((raw_v - y_valid) ** 2))
        hol_q = evaluate(sets["valid"], "hol", to_scores(raw_v)["hol"])["qwk"]
        cm = cont_metrics(sets["valid"], raw_v).set_index("item")
        # early stop 기준: 소수 점수 그대로의 9개 항목 평균 상관 (반올림 영향 없음)
        stop_score = float(cm["pearson"].mean())
        print(
            f"에폭 {epoch} 학습 loss {np.mean(train_losses):.3f} / 검증 loss {valid_loss:.3f}"
            f" / 검증 평균 상관 {stop_score:.3f} (참고 QWK {q:.3f}, 총점 {hol_q:.3f})"
            f" ({(time.time() - start) / 60:.1f}분)"
        )
        if math.isnan(q):
            # 예측이 전부 같은 점수 등으로 QWK를 못 구하면 NaN. 가장 낮은 점수로 취급
            print("  검증 QWK가 NaN이라 -1로 취급")
            q = -1.0
        history.append(
            {
                "epoch": epoch,
                "train_loss": round(float(np.mean(train_losses)), 4),
                "valid_loss": round(valid_loss, 4),
                "valid_mean_qwk": round(q, 4),
                "valid_hol_qwk": round(float(hol_q), 4),
                "valid_hol_rmse": cm.loc["hol", "rmse"],
                "valid_hol_pearson": cm.loc["hol", "pearson"],
                "valid_mean_pearson": round(float(cm["pearson"].mean()), 4),
                "minutes": round((time.time() - start) / 60, 2),
            }
        )
        pd.DataFrame(history).to_csv(ckpt_dir / "history.csv", index=False)
        # 첫 에폭은 무조건 저장 (그래야 마지막에 불러올 체크포인트가 항상 있음)
        if math.isnan(stop_score):
            stop_score = -1.0
        if best_epoch == 0 or stop_score > best_qwk:
            best_qwk, best_epoch = stop_score, epoch
            model.save_pretrained(ckpt_dir)
            tokenizer.save_pretrained(ckpt_dir)
        elif args.patience and epoch - best_epoch >= args.patience:
            print(
                f"검증 상관이 {args.patience}에폭 연속 안 올라서 멈춤 (가장 좋은 에폭 {best_epoch})"
            )
            break

    # 검증 기준 가장 좋았던 에폭의 가중치로 평가용 성적을 한 번만 낸다
    model = AutoModelForSequenceClassification.from_pretrained(ckpt_dir).to(device)
    raw_valid = predict(model, loaders["valid"], device)
    raw_test = predict(model, loaders["test"], device)
    if args.save_preds:
        # 답안별 예측 (학생 글은 없음). AI Hub 데이터에서 나온 값이라 커밋하지 않음
        np.savez(
            ckpt_dir / "preds.npz",
            valid=raw_valid,
            test=raw_test,
            valid_id=sets["valid"]["answer_id"].to_numpy(dtype=str),
            test_id=sets["test"]["answer_id"].to_numpy(dtype=str),
        )

    preds = {(run_name, it): s for it, s in to_scores(raw_test).items()}
    cuts = {}
    if args.head == "reg":
        # 회귀일 때만: 점수 경계는 검증용으로만 찾고, 평가용엔 적용만 한다 (참고용)
        cuts = {
            it: fit_cuts(sets["valid"], it, raw_valid[:, i])
            for i, it in enumerate(ITEMS)
        }
        (ckpt_dir / "score_cuts.json").write_text(
            json.dumps(cuts, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for i, it in enumerate(ITEMS):
            preds[(f"{run_name}_cut", it)] = apply_cuts(raw_test[:, i], cuts[it])
    test = sets["test"]
    group_cols = ["grade"] + (["essay_type"] if "essay_type" in test else [])
    table = score_table(test, preds, group_cols)
    args.result_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.result_dir / f"train_{run_name}.csv", index=False)
    pd.DataFrame(history).to_csv(
        args.result_dir / f"history_{run_name}.csv", index=False
    )
    cont = cont_metrics(test, raw_test)
    cont.to_csv(args.result_dir / f"cont_{run_name}.csv", index=False)
    print(
        f"\n평가용 소수 점수 성적 (반올림 없음, 정답=두 전문가 평균):\n{cont.to_string(index=False)}"
    )

    info = {
        **{k: str(v) for k, v in vars(args).items()},
        "best_epoch": best_epoch,
        "stopped_epoch": len(history),
        "best_valid_mean_pearson": round(best_qwk, 3),
        "device": str(device),
        "amp_dtype": str(amp_dtype),
        "score_cuts": cuts,
        "minutes": round((time.time() - start) / 60, 1),
    }
    (ckpt_dir / "train_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    overall = table[table["group_by"] == "all"].pivot(
        index="item", columns="baseline", values="qwk"
    )
    names = {
        run_name: "분류" if args.head == "cls" else "반올림",
        f"{run_name}_cut": "경계 조정",
    }
    overall.columns = [names[c] for c in overall.columns]
    print(
        f"\n평가용 QWK (가장 좋은 에폭 {best_epoch}):\n{overall.reindex(ITEMS).to_string()}"
    )


if __name__ == "__main__":
    main()
