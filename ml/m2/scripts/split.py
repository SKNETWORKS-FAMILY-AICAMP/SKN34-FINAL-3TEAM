"""문항 단위로 학습/검증/평가 세트를 나눈다.

같은 문항(prompt_id)의 답이 두 세트에 섞이면 점수가 부풀려지므로(데이터 누수)
답이 아니라 문항을 나눈다.

- 서술형: 학년×과목 20칸에 칸마다 3문항. 칸마다 1문항을 빼고,
  뺀 20문항을 바둑판 모양으로 검증 10 / 평가 10으로 나눈다.
- 논술형: 칸마다 문항 수가 들쭉날쭉하고, 글 종류(설명·주장·정서)에 따라
  채점 항목 뜻이 바뀐다. 글종류×학년 칸마다 앞 20% 평가, 다음 20% 검증.

실행: python scripts/split.py
출력: splits/descriptive_split_seed42.csv, splits/essay_split_seed42.csv
      (이미 있으면 덮어쓰지 않고 같은지만 비교한다)
"""

import argparse
from pathlib import Path

import pandas as pd

M2_DIR = Path(__file__).resolve().parent.parent


# 서술형 나누기
def split_descriptive(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    # 노트북 01: 문항 표 → 칸마다 1개 뽑기 → 바둑판
    prompts = df[["prompt_id", "grade", "subject"]].drop_duplicates()
    held = prompts.groupby(["grade", "subject"]).sample(n=1, random_state=seed)

    g = held["grade"].rank(method="dense").astype(int)
    s = held["subject"].rank(method="dense").astype(int)
    is_valid = (g + s) % 2 == 0

    prompts["split_new"] = "train"
    prompts.loc[held[is_valid].index, "split_new"] = "valid"
    prompts.loc[held[~is_valid].index, "split_new"] = "test"
    return prompts


# 논술형 나누기
def split_essay(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    # 노트북 02: 섞기 → 칸 안 위치 비율 → 앞 20% 평가, 다음 20% 검증
    keys = ["essay_type", "grade"]
    prompts = df[["prompt_id", "grade", "subject", "essay_type"]].drop_duplicates()
    prompts = prompts.sample(frac=1, random_state=seed)

    pos = prompts.groupby(keys).cumcount()
    n = prompts.groupby(keys)["prompt_id"].transform("count")
    ratio = (pos + 0.5) / n

    prompts["split_new"] = "train"
    prompts.loc[ratio < 0.4, "split_new"] = "valid"
    prompts.loc[ratio < 0.2, "split_new"] = "test"
    return prompts


def check_and_save(df: pd.DataFrame, prompts: pd.DataFrame, path: Path) -> None:
    # 누수 검사: 한 문항이 두 세트에 걸치면 멈춘다
    merged = df.merge(prompts[["prompt_id", "split_new"]], on="prompt_id")
    assert merged.groupby("prompt_id")["split_new"].nunique().max() == 1, (
        "누수: 한 문항이 두 세트에 있음"
    )

    print(f"[{path.name}]")
    print("  문항 수:", prompts["split_new"].value_counts().to_dict())
    print(
        "  답 비율:",
        merged["split_new"].value_counts(normalize=True).round(3).to_dict(),
    )

    now = prompts.sort_values("prompt_id").reset_index(drop=True)
    if path.exists():
        saved = pd.read_csv(path)
        print("  저장된 목록과 같은가?", saved.equals(now))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        now.to_csv(path, index=False)
        print("  처음이라 저장함")


def main() -> None:
    parser = argparse.ArgumentParser(description="문항 단위 학습/검증/평가 분할")
    parser.add_argument("--data-dir", type=Path, default=M2_DIR / "data")
    parser.add_argument("--out-dir", type=Path, default=M2_DIR / "splits")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    desc = pd.read_csv(args.data_dir / "서술형_답안.csv")
    check_and_save(
        desc,
        split_descriptive(desc, args.seed),
        args.out_dir / f"descriptive_split_seed{args.seed}.csv",
    )

    essay = pd.read_csv(args.data_dir / "논술형_답안.csv.gz")
    check_and_save(
        essay,
        split_essay(essay, args.seed),
        args.out_dir / f"essay_split_seed{args.seed}.csv",
    )


if __name__ == "__main__":
    main()
