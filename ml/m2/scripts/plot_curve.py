"""학습 곡선 그리기: train.py가 남긴 history.csv → PNG.

위 그래프: 학습 loss와 검증 loss (MSE). 학습 loss만 계속 내려가고 검증 loss가 다시 오르면 과적합.
아래 그래프: 검증 평균 상관과 총점 상관 (Pearson, 소수 점수). 가장 높은 에폭에 점선 (그 에폭의 가중치를 저장함).

사용법 (matplotlib 필요: uv add matplotlib):
    uv run python scripts/plot_curve.py results/history_klue_roberta-base_descriptive_seed42_kw.csv
    uv run python scripts/plot_curve.py results/history_*.csv     # 여러 개면 총점 상관을 한 그래프에 겹쳐 그림
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

# 한글 라벨이 네모로 깨지지 않게 (윈도우 맑은 고딕, 리눅스는 나눔 계열이 있으면 사용)
plt.rcParams["font.family"] = ["Malgun Gothic", "NanumGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def label(path: Path) -> str:
    return path.stem.removeprefix("history_")


def plot_one(path: Path) -> Path:
    h = pd.read_csv(path)
    best = h.loc[h["valid_mean_pearson"].idxmax(), "epoch"]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 6), sharex=True)
    ax1.plot(h["epoch"], h["train_loss"], marker="o", label="학습 loss")
    ax1.plot(h["epoch"], h["valid_loss"], marker="o", label="검증 loss")
    ax1.set_ylabel("loss (MSE)")
    ax1.legend()
    ax2.plot(
        h["epoch"],
        h["valid_mean_pearson"],
        marker="o",
        label="검증 평균 상관 (소수 점수, early stop 기준)",
    )
    ax2.plot(h["epoch"], h["valid_hol_pearson"], marker="o", label="검증 총점 상관")
    ax2.set_xlabel("에폭")
    ax2.set_ylabel("상관 (Pearson)")
    ax2.legend()
    for ax in (ax1, ax2):
        ax.axvline(best, color="gray", linestyle="--", linewidth=1)
        ax.grid(alpha=0.3)
    fig.suptitle(
        f"{label(path)} (가장 좋은 에폭 {best}, {h['minutes'].iloc[-1]:.1f}분)"
    )
    fig.tight_layout()
    out = path.with_suffix(".png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def plot_many(paths: list[Path]) -> Path:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for p in paths:
        h = pd.read_csv(p)
        ax.plot(h["epoch"], h["valid_hol_pearson"], marker="o", label=label(p))
    ax.set_xlabel("에폭")
    ax.set_ylabel("검증 총점 상관")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = paths[0].parent / "history_compare.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


if __name__ == "__main__":
    files = [Path(a) for a in sys.argv[1:]]
    if not files:
        print(__doc__)
        sys.exit(1)
    for f in files:
        print("저장:", plot_one(f))
    if len(files) > 1:
        print("비교 그래프:", plot_many(files))
