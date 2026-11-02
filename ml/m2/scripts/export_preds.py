"""모델 예측값(preds.npz)을 성욱 님 채점표용 CSV로 바꾼다 (11/1 역할 분담 형식).

- 서술: 평가 글 = AI Hub VL 4,000편 (train.py --aihub-split --save-preds 의 test)
  열 = answer_id, prompt_id, grade, <항목>_r1, <항목>_r2, <항목>_pred (9개 항목)
- 545: 평가 글 = same_topic(VL) + new_topic (train_545.py --save-preds, 시드 43 분할이면 10/30 공유
CSV와 같은 글)
  열 = eval, essay_id, split, grade, essay_type, topic, <영역>_r1~r3, <영역>_pred (구성·내용·표현)
- pred는 소수 그대로 (정수 변환·분포 맞춤은 채점표 쪽 후처리). 학생 글·지시문·이유 문장은 넣지 않음
- 10/30 공유 CSV(results/share_1030)가 있으면 같은 평가 글인지 확인해서 출력

예: uv run python scripts/export_preds.py --kind desc --preds <모델 폴더>/preds.npz --name klue-3.0
--seed 42
    uv run python scripts/export_preds.py --kind essay --preds <모델 폴더>/preds.npz --name
    qwen3-1.7b-lora16 --seed 43
"""

import argparse
import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from baseline import ITEMS

M2 = Path(__file__).resolve().parent.parent
AREAS = ["org", "cont", "exp"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["desc", "essay"], required=True)
    ap.add_argument("--preds", type=Path, required=True)
    ap.add_argument("--name", required=True, help="파일 이름에 넣을 모델 이름 (예: klue-3.0)")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--data-dir", type=Path, default=M2 / "data" / "clean")
    ap.add_argument("--out-dir", type=Path, default=M2 / "results" / "share")
    ap.add_argument("--date", default=datetime.date.today().strftime("%m%d"))
    args = ap.parse_args()
    z = np.load(args.preds)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.kind == "desc":
        d = pd.read_csv(args.data_dir / "서술형_답안.csv", dtype={"answer_id": str})
        d = d.set_index("answer_id").loc[z["test_id"]].reset_index()
        out = d[["answer_id", "prompt_id", "grade"]].copy()
        for j, it in enumerate(ITEMS):
            out[f"{it}_r1"], out[f"{it}_r2"] = d[f"{it}_r1"], d[f"{it}_r2"]
            out[f"{it}_pred"] = z["test"][:, j].round(4)
        ref, key = M2 / "results/share_1030/m2_서술_정제본_예측_VL4000.csv", "answer_id"
        path = args.out_dir / f"m2_서술_{args.name}_seed{args.seed}_{args.date}.csv"
    else:
        d = pd.read_csv(args.data_dir / "에세이545_답안.csv.gz", dtype={"essay_id": str})
        d = d.set_index("essay_id")
        parts = []
        for ev in ["same_topic", "new_topic"]:
            if ev not in z:
                continue
            p = d.loc[z[ev + "_id"]].reset_index()
            o = p[["essay_id", "split", "grade", "essay_type", "subject"]].rename(
                columns={"subject": "topic"}
            )
            o.insert(0, "eval", ev)
            for j, a in enumerate(AREAS):
                for r in (1, 2, 3):
                    o[f"{a}_r{r}"] = p[f"{a}_r{r}"]
                o[f"{a}_pred"] = z[ev][:, j].round(4)
            parts.append(o)
        out = pd.concat(parts, ignore_index=True)
        ref, key = (
            M2 / "results/share_1030/m2_논술545_정제본_예측_seed43.csv",
            "essay_id",
        )
        path = args.out_dir / f"m2_논술545_{args.name}_seed{args.seed}_{args.date}.csv"

    out.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"저장: {path} ({len(out):,}행, 열 {len(out.columns)}개)")
    if ref.exists():
        r = pd.read_csv(ref, dtype={key: str})
        same = set(r[key]) == set(out[key])
        print(
            f"10/30 공유 CSV와 같은 평가 글: {'예' if same else '아니오'} ({len(r):,} vs "
            f"{len(out):,})"
        )
    # 보고용: 총점·항목별 Pearson (채점자 평균 대비, 소수 예측 그대로)
    rows = []
    if args.kind == "desc":
        for it in ITEMS:
            g = (out[f"{it}_r1"] + out[f"{it}_r2"]) / 2
            rows.append((it, round(float(np.corrcoef(g, out[f"{it}_pred"])[0, 1]), 3)))
    else:
        for ev, o in out.groupby("eval", sort=False):
            gs = [o[[f"{a}_r{r}" for r in (1, 2, 3)]].mean(axis=1) for a in AREAS]
            ps = [o[f"{a}_pred"] for a in AREAS]
            for a, g, p in zip(AREAS, gs, ps, strict=False):
                rows.append((f"{ev}:{a}", round(float(np.corrcoef(g, p)[0, 1]), 3)))
            rows.append((f"{ev}:total", round(float(np.corrcoef(sum(gs), sum(ps))[0, 1]), 3)))
    print("Pearson (채점자 평균 대비, 소수 예측 그대로):", dict(rows))


if __name__ == "__main__":
    main()
