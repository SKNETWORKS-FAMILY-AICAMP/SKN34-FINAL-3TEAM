"""멘토 요청: 사람 점수와 교사(생성) 점수를 구분해 기록하고, 학생 모델이 무엇과의 일치도를 높였는지 본다.

평가용(AI Hub VL) 답에서 항목별 Pearson:
  학생 vs 전문가 평균 / 학생 vs 교사 / 교사 vs 전문가 평균 / 전문가1 vs 전문가2
학생은 D①(증류 없음)과 증류 모델 두 개를 나란히 낸다. 숫자만 출력(글 내용 없음).

사용 (Pod, /workspace/m2):
  uv run python scripts/compare_targets.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

M2 = Path(__file__).resolve().parents[1]
ITEMS = ["hol", "task_1", "content_1", "content_2", "content_3",
         "organization_1", "organization_2", "expression_1", "expression_2"]
BASE = "klue_roberta-base_descriptive_seed42_kw_noprompt_aihub_clean"


def find_preds(pattern: str) -> Path:
    hits = sorted(M2.glob(f"checkpoints/**/{pattern}/preds.npz"))
    if len(hits) != 1:
        raise SystemExit(f"{pattern}: preds.npz {len(hits)}개 → {[str(h) for h in hits]}")
    return hits[0]


def load_student(path: Path) -> pd.DataFrame:
    z = np.load(path, allow_pickle=False)
    return pd.DataFrame(z["test"], columns=ITEMS).assign(answer_id=z["test_id"].astype(str))


def r(a, b) -> float:
    m = ~(np.isnan(a) | np.isnan(b))
    return float(np.corrcoef(a[m], b[m])[0, 1])


def main():
    cols = ["answer_id"] + [f"{it}_r{k}" for it in ITEMS for k in (1, 2)]
    exp = pd.read_csv(M2 / "data" / "clean" / "서술형_답안.csv", usecols=cols, dtype={"answer_id": str})
    teacher = pd.read_csv(M2 / "checkpoints" / "teacher" / "descriptive" / "teacher_preds.csv.gz",
                          dtype={"answer_id": str})
    students = {"D①(증류 없음)": load_student(find_preds(BASE))}
    distill = sorted(M2.glob(f"checkpoints/**/{BASE.replace('_clean', '')}*distill*/preds.npz"))
    for p in distill:
        students[f"증류({p.parent.name.split('distill')[1]})"] = load_student(p)

    rows = []
    for it in ITEMS:
        base = exp[["answer_id", f"{it}_r1", f"{it}_r2"]].merge(
            teacher[["answer_id", it]].rename(columns={it: "teacher"}), on="answer_id", how="left")
        avg = base[[f"{it}_r1", f"{it}_r2"]].mean(axis=1).to_numpy(float)
        row = {"item": it}
        first = True
        for name, s in students.items():
            d = base.merge(s[["answer_id", it]].rename(columns={it: "student"}), on="answer_id")
            a = d[[f"{it}_r1", f"{it}_r2"]].mean(axis=1).to_numpy(float)
            st, te = d["student"].to_numpy(float), d["teacher"].to_numpy(float)
            row[f"{name} vs 전문가"] = r(st, a)
            row[f"{name} vs 교사"] = r(st, te)
            if first:
                row["n"] = len(d)
                row["교사 vs 전문가"] = r(te, a)
                row["전문가1 vs 전문가2"] = r(d[f"{it}_r1"].to_numpy(float), d[f"{it}_r2"].to_numpy(float))
                row["교사 빈칸"] = int(np.isnan(te).sum())
                first = False
        rows.append(row)
    out = pd.DataFrame(rows)
    mean = out.drop(columns=["item"]).mean(numeric_only=True).to_dict()
    out = pd.concat([out, pd.DataFrame([{"item": "9항목 평균", **mean}])], ignore_index=True)
    dst = M2 / "results" / "teacher" / "compare_targets_descriptive.csv"
    out.round(3).to_csv(dst, index=False)
    pd.set_option("display.width", 250)
    print(out.round(3).to_string(index=False))
    print(f"\n저장: {dst}")


if __name__ == "__main__":
    main()
