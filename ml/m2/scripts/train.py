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
    split = pd.read_csv(
        args.split_dir / f"{args.dataset}_split_seed{args.split_seed}.csv"
    )
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


def aihub_split(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """AI Hub 원래 구분으로 다시 나눈다 (같은 지시문으로 학습·평가하는 AI Hub 공식 조건 비교용).

    AI Hub VL(Validation 4,000건) → 평가용(test), 딱 한 번만 채점
    AI Hub TL → 답안 10%를 무작위로 떼어 검증용(early stop 판단), 나머지 학습용
    VL을 early stop에도 쓰면 누수라서 검증용은 TL 안에서 따로 뗀다.
    """
    df = df.copy()
    is_tl = df["split"] == "train"
    pick = np.random.RandomState(seed).rand(len(df)) < 0.1
    df["split_new"] = np.where(~is_tl, "test", np.where(pick, "valid", "train"))
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


def corr_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """배치 안에서 항목마다 (1 - Pearson 상관)의 평균. 점수 크기가 아니라 '순서'를 직접 가르친다.

    MSE만 쓰면 애매한 글을 전부 3점 근처로 몰아도 손해가 적어서(10/28 확인: 예측 퍼짐이 정답의 6할),
    좋은 글과 나쁜 글의 순서를 맞히는 항을 더한다 (R2BERT의 회귀 + 순위 학습과 같은 생각).
    배치 안에서 정답이 전부 같은 항목은 상관을 못 구하니 뺀다.
    """
    p = pred - pred.mean(0, keepdim=True)
    t = target - target.mean(0, keepdim=True)
    denom = p.norm(dim=0) * t.norm(dim=0)
    ok = t.norm(dim=0) > 1e-6
    if not ok.any():
        return pred.sum() * 0.0
    r = (p * t).sum(0)[ok] / (denom[ok] + 1e-8)
    return (1 - r).mean()


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


def first_segment(
    df, with_keyword=False, with_purpose=False, exemplar_chars=0, no_prompt=False
):
    # --no-prompt: 지시문 문장을 빼서 모델이 문장을 외우지 못하게 함 (10/29 바꾼 문장 시험에서 서술형이 문장을 외운 것 확인)
    first = "[학년] " + df["grade"] + ("" if no_prompt else " [지시문] " + df["prompt"])
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


def build_model(args, n_out, tokenizer):
    """학습 시작용 모델. --lora면 LLM(Kanana 등) 위에 LoRA만 학습 (나머지 가중치 고정)."""
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model,
        num_labels=n_out,
        problem_type="regression",  # loss는 아래에서 직접 계산 (cls는 분포 교차 엔트로피)
        ignore_mismatched_sizes=True,  # 출력 칸은 새로 만듦
    )
    if not args.lora:
        return model
    from peft import LoraConfig, get_peft_model

    # transformers 5는 LLM을 bf16으로 불러옴 → 새 점수 칸(fp32)과 섞이면 평가 때 에러. 학습 계산은 autocast bf16 그대로
    model = model.float()
    # LLM은 pad 토큰이 없는 경우가 많음. 분류 모델이 "마지막 진짜 토큰"을 찾을 때 씀
    model.config.pad_token_id = tokenizer.pad_token_id
    # LLM 점수 칸(score)은 bias가 없어서 시작값(평균 점수)을 못 넣음 → bias 있는 칸으로 바꿈
    if model.score.bias is None:
        old = model.score
        model.score = torch.nn.Linear(old.in_features, old.out_features, bias=True)
        with torch.no_grad():
            model.score.weight.copy_(old.weight)
    if args.grad_ckpt:
        model.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={"use_reentrant": False}
        )
        model.enable_input_require_grads()
    cfg = LoraConfig(
        r=args.lora,
        lora_alpha=2 * args.lora,
        lora_dropout=0.05,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        modules_to_save=["score"],
        task_type="SEQ_CLS",
    )
    model = get_peft_model(model, cfg)
    model.print_trainable_parameters()
    return model


def load_trained(args, ckpt_dir, n_out, tokenizer):
    """저장한 모델 불러오기. --lora면 원래 LLM + 저장한 LoRA."""
    if not args.lora:
        return AutoModelForSequenceClassification.from_pretrained(ckpt_dir)
    from peft import PeftModel

    args_g, args.grad_ckpt = args.grad_ckpt, False
    lora, args.lora = args.lora, 0
    base = build_model(args, n_out, tokenizer).float()
    args.grad_ckpt, args.lora = args_g, lora
    base.config.pad_token_id = tokenizer.pad_token_id
    if base.score.bias is None:
        base.score = torch.nn.Linear(
            base.score.in_features, base.score.out_features, bias=True
        )
    return PeftModel.from_pretrained(base, ckpt_dir)


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


def load_override(path: Path, df: pd.DataFrame) -> pd.DataFrame:
    """--prompt-override CSV(prompt_id, prompt)를 읽고 검사한다. 문장 내용은 출력하지 않음."""
    ov = pd.read_csv(path, dtype={"prompt_id": str})
    if not {"prompt_id", "prompt"} <= set(ov.columns):
        raise SystemExit(
            f"{path}: prompt_id, prompt 열이 필요함 (지금 {list(ov.columns)})"
        )
    ov["prompt_id"] = ov["prompt_id"].str.strip()
    ov["prompt"] = ov["prompt"].astype(str).str.strip()
    ov = ov[ov["prompt"].ne("") & ov["prompt"].ne("nan")]
    if ov["prompt_id"].duplicated().any():
        raise SystemExit(
            f"{path}: prompt_id 중복 {ov.loc[ov['prompt_id'].duplicated(), 'prompt_id'].tolist()}"
        )
    unknown = sorted(set(ov["prompt_id"]) - set(df["prompt_id"]))
    if unknown:
        raise SystemExit(f"{path}: 데이터에 없는 prompt_id {unknown}")
    same = ov.merge(
        df[["prompt_id", "prompt"]].drop_duplicates("prompt_id"), on="prompt_id"
    )
    n_same = int((same["prompt_x"] == same["prompt_y"]).sum())
    if n_same:
        print(f"  주의: 원래 문장과 똑같은 지시문 {n_same}개 (비교 의미 없음)")
    return ov[["prompt_id", "prompt"]].reset_index(drop=True)


def override_eval(model, tokenizer, test, ov, args, device, input_opts, run_name):
    """같은 모델·같은 답으로 원래 지시문 vs 바꾼 지시문 성적을 짝지어 비교 (평가할 때만 교체)."""
    sub = test[test["prompt_id"].isin(ov["prompt_id"])].reset_index(drop=True)
    missing = sorted(set(ov["prompt_id"]) - set(sub["prompt_id"]))
    if missing:
        print(f"  주의: 평가용에 답이 없는 문항 {missing} (비교에서 빠짐)")
    if sub.empty:
        print("  바꾼 지시문 문항이 평가용에 하나도 없어서 비교 생략")
        return
    new = sub.copy()
    new["prompt"] = sub["prompt_id"].map(dict(zip(ov["prompt_id"], ov["prompt"])))
    raws = {}
    rows = []
    for cond, part in [("original", sub), ("override", new)]:
        loader = make_loader(
            part,
            tokenizer,
            args.max_length,
            args.eval_batch_size,
            False,
            head=args.head,
            **input_opts,
        )
        raws[cond] = predict(model, loader, device)
        cm = cont_metrics(part, raws[cond])
        scores = to_scores(raws[cond])
        cm["qwk"] = [
            round(float(evaluate(part, it, scores[it])["qwk"]), 3) for it in cm["item"]
        ]
        cm.insert(0, "condition", cond)
        rows.append(cm)
    out = pd.concat(rows, ignore_index=True)
    # 두 조건 예측이 답마다 얼마나 달라졌는지 (0에 가까우면 모델이 지시문 문장을 거의 안 봄)
    shift = np.abs(cont_scores(raws["override"]) - cont_scores(raws["original"])).mean(
        0
    )
    # 총점 Pearson 차이의 짝 부트스트랩 95% 구간 (같은 답을 뽑아 두 조건을 함께 계산)
    gold = targets(sub)[:, ITEMS.index("hol")]
    po = cont_scores(raws["original"])[:, ITEMS.index("hol")]
    pn = cont_scores(raws["override"])[:, ITEMS.index("hol")]
    rs = np.random.RandomState(args.seed)
    diffs = []
    for _ in range(2000):
        i = rs.randint(0, len(sub), len(sub))
        diffs.append(
            np.corrcoef(pn[i], gold[i])[0, 1] - np.corrcoef(po[i], gold[i])[0, 1]
        )
    lo, hi = np.nanpercentile(diffs, [2.5, 97.5])
    piv = out.pivot(index="item", columns="condition", values="pearson").reindex(ITEMS)
    piv["diff"] = (piv["override"] - piv["original"]).round(3)
    piv["pred_shift_mae"] = np.round(shift, 3)
    args.result_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.result_dir / f"override_{run_name}.csv", index=False)
    piv.to_csv(args.result_dir / f"override_{run_name}_diff.csv")
    print(
        f"\n지시문 교체 비교 (문항 {sub['prompt_id'].nunique()}개, 답 {len(sub):,}개, 소수 Pearson):\n"
        f"{piv.to_string()}\n총점 차이(바꾼-원래) 95% 구간: [{lo:.3f}, {hi:.3f}]"
    )


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
        "--corr-loss",
        type=float,
        default=0.0,
        help="회귀 손실에 (1 - 배치 상관) x 이 값을 더함. 0이면 MSE만 (순서 학습 실험용, 예: 1.0)",
    )
    parser.add_argument(
        "--merge-valid",
        action="store_true",
        help="검증 문항도 학습에 합침. early stop 판단이 불가능해서 --epochs로 정한 에폭까지 학습하고 마지막 에폭을 씀",
    )
    parser.add_argument(
        "--aihub-split",
        action="store_true",
        help="AI Hub 원래 구분으로 학습·평가 (TL 90%% 학습, TL 10%% 검증, VL 평가). 같은 지시문 조건 비교용",
    )
    parser.add_argument(
        "--split-seed",
        type=int,
        default=42,
        help="문항 분할 파일의 시드 (--seed만 바꾸면 같은 분할에서 초기값·순서만 달라짐)",
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="세트마다 답 N개만 (동작 확인용)"
    )
    parser.add_argument(
        "--with-keyword", action="store_true", help="입력에 문항 핵심어 추가 (서술형만)"
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="입력에서 지시문 문장을 뺌 (학년 + 핵심어 + 학생 글)",
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
        "--lora",
        type=int,
        default=0,
        help="LoRA rank (예: 16). LLM(kakaocorp/kanana-1.5-2.1b-base 등)을 LoRA로 학습. 0이면 끔 (roberta 전체 학습)",
    )
    parser.add_argument(
        "--grad-ckpt",
        action="store_true",
        help="gradient checkpointing (--lora에서 메모리 절약, 대신 느려짐)",
    )
    parser.add_argument(
        "--train-answers",
        type=int,
        default=0,
        help="공부용 답을 전체 N개로 무작위로 줄임 (--train-prompts와 같이: 답 수를 고정하고 문항 수만 바꾸는 대조 실험, 0이면 전부)",
    )
    parser.add_argument(
        "--prompt-override",
        type=Path,
        default=None,
        help="CSV(prompt_id, prompt). 학습은 원래 지시문, 평가 때만 이 문장으로 바꿔 원래 문장과 비교 (--aihub-split와 같이)",
    )
    parser.add_argument(
        "--eval-only",
        action="store_true",
        help="학습 없이 --out-dir/<run 이름>에 저장된 모델로 평가만 (같은 옵션으로 먼저 학습해 둔 모델). 보통 --prompt-override와 같이",
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
    if args.aihub_split and args.extra_adult:
        parser.error(
            "--aihub-split와 --extra-adult는 같이 못 씀 (성인 글 VL이 평가용에 섞임)"
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
    if args.no_prompt:
        run_name += "_noprompt"
    if args.with_purpose:
        run_name += "_purpose"
    if args.with_exemplar:
        run_name += f"_ex{args.exemplar_chars}"
    if args.extra_adult:
        run_name += "_adult"
    if args.aihub_split:
        run_name += "_aihub"
    if args.corr_loss:
        run_name += f"_corr{args.corr_loss:g}"
    if args.merge_valid:
        run_name += f"_mergevalid_ep{args.epochs}"
    if args.train_prompts:
        run_name += f"_p{args.train_prompts}"
    if args.train_answers:
        run_name += f"_a{args.train_answers}"
    if args.lora:
        run_name += f"_lora{args.lora}"
    print(f"장치: {device} / 모델: {args.model} / 데이터: {args.dataset}")

    df = load(args)
    override = load_override(args.prompt_override, df) if args.prompt_override else None
    if override is not None:
        print(f"지시문 교체 {len(override)}개 (평가 때만)")
        if not args.aihub_split:
            print("  주의: --aihub-split 없이 쓰면 평가 문항이 학습에 없던 지시문임")
    if args.aihub_split:
        df = aihub_split(df, args.split_seed)
        print("AI Hub 구분 사용:", df["split_new"].value_counts().to_dict())
    if args.with_exemplar:
        ex = pick_exemplars(df, args.seed)
        df = df[
            ~df["answer_id"].isin(ex["answer_id"])
        ]  # 예시로 쓴 답은 채점 대상에서 뺌
        df = df.merge(ex[["prompt_id", "exemplar"]], on="prompt_id")
        print(f"예시 답안 {len(ex)}개 (문항당 1개)를 학습·평가에서 빼고 입력에 붙임")
    input_opts = {
        "with_keyword": args.with_keyword,
        "no_prompt": args.no_prompt,
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
    if args.train_answers and len(sets["train"]) > args.train_answers:
        sets["train"] = (
            sets["train"]
            .sample(n=args.train_answers, random_state=args.seed)
            .reset_index(drop=True)
        )
        print(
            f"공부용 답 {args.train_answers}개로 줄임 (문항 {sets['train']['prompt_id'].nunique()}개)"
        )
    if args.merge_valid:
        sets["train"] = pd.concat([sets["train"], sets["valid"]], ignore_index=True)
        print(
            f"검증 문항도 학습에 합침 (에폭 {args.epochs} 고정, 검증 점수는 학습에 쓴 글이라 참고만)"
        )
    print({k: len(v) for k, v in sets.items()})

    if args.eval_only:
        # 저장된 모델을 불러와 평가용 성적 + (있으면) 지시문 교체 비교만. 학습 결과 파일은 건드리지 않음
        ckpt_dir = args.out_dir / run_name
        if not any(
            (ckpt_dir / f).exists() for f in ("config.json", "adapter_config.json")
        ):
            raise SystemExit(
                f"--eval-only: 저장된 모델이 없음 ({ckpt_dir}). 같은 옵션으로 먼저 학습"
            )
        print(f"--eval-only: {ckpt_dir} 불러옴 (학습 안 함)")
        if device.type == "cuda":  # 학습 후 평가와 같은 계산 설정 (TF32)
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
        tokenizer = AutoTokenizer.from_pretrained(ckpt_dir)
        n_out = len(ITEMS) * N_CLASS if args.head == "cls" else len(ITEMS)
        model = load_trained(args, ckpt_dir, n_out, tokenizer).to(device)
        test = sets["test"]
        loader = make_loader(
            test,
            tokenizer,
            args.max_length,
            args.eval_batch_size,
            False,
            head=args.head,
            **input_opts,
        )
        cont = cont_metrics(test, predict(model, loader, device))
        print(
            f"\n평가용 소수 점수 성적 (학습 때 cont_{run_name}.csv와 같아야 함):\n{cont.to_string(index=False)}"
        )
        if override is not None:
            override_eval(
                model, tokenizer, test, override, args, device, input_opts, run_name
            )
        else:
            print("  --prompt-override가 없어서 지시문 교체 비교는 생략")
        return

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token is None:  # LLM 토크나이저는 pad가 없는 경우가 많음
        tokenizer.pad_token = tokenizer.eos_token
    n_out = len(ITEMS) * N_CLASS if args.head == "cls" else len(ITEMS)
    model = build_model(args, n_out, tokenizer).to(device)

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

    optimizer = torch.optim.AdamW(
        [p_ for p_ in model.parameters() if p_.requires_grad],
        lr=args.lr,
        weight_decay=0.01,
    )
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
                    if args.corr_loss:
                        loss = loss + args.corr_loss * corr_loss(
                            logits.float(), batch["labels"]
                        )
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
                    f" ({(time.time() - start) / 60:.1f}분)"
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
        if args.merge_valid or best_epoch == 0 or stop_score > best_qwk:
            best_qwk, best_epoch = stop_score, epoch
            model.save_pretrained(ckpt_dir)
            tokenizer.save_pretrained(ckpt_dir)
        elif (
            not args.merge_valid
            and args.patience
            and epoch - best_epoch >= args.patience
        ):
            print(
                f"검증 상관이 {args.patience}에폭 연속 안 올라서 멈춤 (가장 좋은 에폭 {best_epoch})"
            )
            break

    # 검증 기준 가장 좋았던 에폭의 가중치로 평가용 성적을 한 번만 낸다
    model = load_trained(args, ckpt_dir, n_out, tokenizer).to(device)
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

    if override is not None:
        override_eval(
            model, tokenizer, test, override, args, device, input_opts, run_name
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
