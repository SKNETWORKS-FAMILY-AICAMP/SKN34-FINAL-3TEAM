"""여러 모델의 예측 점수를 평균해서(앙상블) 평가한다. GPU 필요 없음.

train.py --save-preds 로 저장한 preds.npz 를 2개 이상 받는다.
점수 경계는 train.py와 같게 검증용 평균 예측으로 찾고, 평가용에는 적용만 한다.

실행:
    uv run python scripts/ensemble.py --dataset descriptive \
        --preds checkpoints/ens/klue_roberta-base_descriptive_seed42_kw/preds.npz \
                checkpoints/ens/klue_roberta-large_descriptive_seed42_kw/preds.npz
"""

import argparse
import json
from pathlib import Path

import numpy as np
from baseline import DATASETS, ITEMS, score_table
from train import M2_DIR, apply_cuts, fit_cuts, load


def main() -> None:
    parser = argparse.ArgumentParser(description="M2 앙상블 평가")
    parser.add_argument("--dataset", choices=list(DATASETS), default="descriptive")
    parser.add_argument("--preds", type=Path, nargs="+", required=True)
    parser.add_argument("--weights", type=float, nargs="+", help="모델별 가중치 (기본: 같게)")
    parser.add_argument("--data-dir", type=Path, default=M2_DIR / "data")
    parser.add_argument("--split-dir", type=Path, default=M2_DIR / "splits")
    parser.add_argument("--result-dir", type=Path, default=M2_DIR / "results" / "ensemble")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    df = load(args)
    sets = {
        name: df[df["split_new"] == name].reset_index(drop=True)
        for name in ["valid", "test"]
    }

    names, valids, tests = [], [], []
    for path in args.preds:
        z = np.load(path)
        # 답안 순서가 같아야 섞을 수 있음
        for name in ["valid", "test"]:
            ids = sets[name]["answer_id"].to_numpy(dtype=str)
            if not np.array_equal(z[f"{name}_id"], ids):
                raise SystemExit(f"{path}: {name} 답안 순서가 다름 (같은 분할·시드로 학습했는지 확인)")
        names.append(path.parent.name)
        valids.append(z["valid"])
        tests.append(z["test"])

    w = np.array(args.weights or [1.0] * len(names))
    w = w / w.sum()
    raw_valid = np.tensordot(w, np.stack(valids), axes=1)
    raw_test = np.tensordot(w, np.stack(tests), axes=1)

    preds = {}
    for name, v, t in zip(names + ["ensemble"], valids + [raw_valid], tests + [raw_test]):
        for i, it in enumerate(ITEMS):
            cuts = fit_cuts(sets["valid"], it, v[:, i])
            preds[(name, it)] = apply_cuts(t[:, i], cuts)

    test = sets["test"]
    group_cols = ["grade"] + (["essay_type"] if "essay_type" in test else [])
    table = score_table(test, preds, group_cols)
    args.result_dir.mkdir(parents=True, exist_ok=True)
    out = args.result_dir / f"ensemble_{args.dataset}.csv"
    table.to_csv(out, index=False)
    (args.result_dir / f"ensemble_{args.dataset}.json").write_text(
        json.dumps({"preds": [str(p) for p in args.preds], "weights": w.tolist()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    overall = table[table["group_by"] == "all"].pivot(index="item", columns="baseline", values="qwk")
    print(f"평가용 QWK (경계 조정, 가중치 {np.round(w, 2).tolist()}):")
    print(overall.reindex(ITEMS)[names + ["ensemble"]].to_string())
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
