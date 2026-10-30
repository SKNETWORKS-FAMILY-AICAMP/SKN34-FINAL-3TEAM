"""545 오차 분석 (10/30, 계획 밖·수빈 님 승인 12:30): 저장된 모델로 예측만 다시 뽑아 어디서 틀리는지 숫자로 본다.

checkpoints/e545_clean 는 시드 42·43이 같은 폴더를 써서 마지막(시드 43) 모델이다 → 분할도 --seed 43으로 똑같이 만든다.
보는 것: ① 512토큰 잘림 여부 ② 정답 점수 구간(가운데로 몰리는지) ③ 학년 ④ 글 종류 ⑤ 처음 보는 주제별
학생 글·지시문·주제 이름은 출력하지 않음(주제는 T01.. 번호로). 숫자만 results/e545/error_*.csv 에 저장.

사용 (Pod, /workspace/m2):  uv run python scripts/error_545.py --seed 43
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_545 import AREAS, loader, predict, target  # noqa: E402

M2 = Path(__file__).resolve().parent.parent


def summarize(df: pd.DataFrame, by: str, set_name: str) -> list[dict]:
    rows = []
    for key, g in df.groupby(by, observed=True):
        if len(g) < 30:
            continue
        row = {"eval": set_name, "by": by, "group": str(key), "n": len(g)}
        for a in AREAS + ["total"]:
            y, p = g[f"y_{a}"].to_numpy(), g[f"p_{a}"].to_numpy()
            row[f"{a}_r"] = round(float(np.corrcoef(p, y)[0, 1]), 3) if y.std() > 0 else np.nan
            row[f"{a}_mae"] = round(float(np.abs(p - y).mean()), 3)
            row[f"{a}_bias"] = round(float((p - y).mean()), 3)  # +면 높게, -면 낮게 줌
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=43)
    ap.add_argument("--data-dir", type=Path, default=M2 / "data" / "clean")
    ap.add_argument("--ckpt", type=Path, default=M2 / "checkpoints" / "e545_clean")
    ap.add_argument("--n-new", type=int, default=10)
    ap.add_argument("--max-length", type=int, default=512)
    args = ap.parse_args()

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    df = pd.read_csv(args.data_dir / "에세이545_답안.csv.gz")
    topics = np.sort(df["subject"].unique())
    code = {t: f"T{i + 1:02d}" for i, t in enumerate(topics)}
    new = set(np.random.RandomState(args.seed).permutation(topics)[: args.n_new])
    sets = {
        "same_topic": df[(df["split"] == "VL") & ~df["subject"].isin(new)].reset_index(drop=True),
        "new_topic": df[df["subject"].isin(new)].reset_index(drop=True),
    }
    tok = AutoTokenizer.from_pretrained(args.ckpt)
    model = AutoModelForSequenceClassification.from_pretrained(args.ckpt).to(dev)

    all_rows, per = [], []
    for name, s in sets.items():
        p = predict(model, loader(s, tok, 64, False, args.max_length), dev)
        y = target(s)
        first = ("[학년] " + s["grade"] + " [글 종류] " + s["essay_type"]).tolist()
        ntok = np.array([len(x) for x in tok(first, s["text"].tolist(), truncation=False)["input_ids"]])
        d = pd.DataFrame({
            "essay_id": s["essay_id"], "topic": s["subject"].map(code),
            "grade": s["grade"], "school": s["grade"].str[0], "essay_type": s["essay_type"],
            "ntok": ntok, "truncated": np.where(ntok > args.max_length, "512 넘음(잘림)", "512 이하"),
        })
        for j, a in enumerate(AREAS):
            d[f"y_{a}"], d[f"p_{a}"] = y[:, j], p[:, j]
        d["y_total"], d["p_total"] = y.mean(1), p.mean(1)
        d["score_band"] = pd.qcut(d["y_total"], 5, duplicates="drop").astype(str)  # 정답 총점 5구간 (낮은 → 높은)
        d["eval"] = name
        per.append(d)
        all_rows.append({"eval": name, "by": "전체", "group": "전체", "n": len(d),
                         **{f"{a}_r": round(float(np.corrcoef(d[f'p_{a}'], d[f'y_{a}'])[0, 1]), 3) for a in AREAS + ["total"]},
                         "pred_std/true_std": round(float(d["p_total"].std() / d["y_total"].std()), 3)})
        for by in ["truncated", "score_band", "school", "grade", "essay_type"] + (["topic"] if name == "new_topic" else []):
            all_rows += summarize(d, by, name)

    out = pd.DataFrame(all_rows)
    (M2 / "results" / "e545").mkdir(parents=True, exist_ok=True)
    dst = M2 / "results" / "e545" / f"error_seed{args.seed}_clean.csv"
    out.to_csv(dst, index=False)
    # 글별 예측(숫자만, 글 없음). AI Hub 파생이라 커밋하지 않음
    pd.concat(per).drop(columns=["essay_id"]).to_csv(args.ckpt / f"error_preds_seed{args.seed}.csv.gz", index=False)

    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 200)
    show = ["eval", "by", "group", "n", "total_r", "total_bias", "org_r", "cont_r", "exp_r", "exp_mae", "pred_std/true_std"]
    print(out[[c for c in show if c in out]].to_string(index=False))
    print(f"\n저장: {dst}")


if __name__ == "__main__":
    main()
