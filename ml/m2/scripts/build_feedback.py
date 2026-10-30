"""전문가 항목별 이유 문장(score.personal.*.feedback)을 표로 뽑는다 (교사 모델 학습용).

71818 서술형·71819 논술형 라벨 JSON에는 항목마다 전문가 이유 문장이 1개씩 있다.
(점수는 전문가 2명분, 이유 문장은 항목당 1개. 545 에세이에는 없음)

출력 (data/, 커밋 금지 — AI Hub 원문):
    서술형_이유.csv.gz / 논술형_이유.csv.gz
    칸: answer_id, item(hol·task_1 …), feedback, r1, r2
    한 줄 = 답 1개 × 항목 1개 (긴 형식)

화면에는 숫자만 낸다 (칸 수·빈칸 비율·길이·두 점수가 같은 비율). 문장 내용은 출력하지 않는다.

실행:
    uv run python scripts/build_feedback.py \
        --descriptive-zip "<25.서술형 글쓰기 평가 데이터.zip>" \
        --essay-zip "<26.논술형 글쓰기 평가 데이터.zip>"
"""

import argparse
from pathlib import Path

import pandas as pd
from baseline import ITEMS
from build_tables import iter_label_json

M2_DIR = Path(__file__).resolve().parent.parent
# "3점", "4 점", "5점 만점" 같은 숫자 점수 표현
# (한글 숫자 "세 점"은 '이점·장점' 같은 낱말과 헷갈려서 세지 않음 → 숫자 포함 비율로 같이 봄)
SCORE_PAT = r"[0-9０-９]\s*점"


def rows_of(j: dict):
    a, s = j["essay_answer"], j["score"]["personal"]
    parts = {"hol": s["holistic"], **s["analytic"]}
    for item in ITEMS:
        v = parts.get(item, {})
        score = v.get("score") or [None, None]
        yield {
            "answer_id": str(a["id"]),
            "item": item,
            "feedback": (v.get("feedback") or "").strip(),
            "r1": score[0],
            "r2": score[1],
        }


def summary(df: pd.DataFrame, name: str) -> None:
    has = df["feedback"].str.len() > 0
    n_ans = df["answer_id"].nunique()
    print(
        f"\n{name}: 답 {n_ans:,}개 × 항목 {df['item'].nunique()}개 = {len(df):,}칸, "
        f"이유 문장 있는 칸 {has.mean():.1%}"
    )
    by = df.assign(
        has=has,
        length=df["feedback"].str.len(),
        agree=df["r1"] == df["r2"],
    ).groupby("item", sort=False)
    table = pd.DataFrame(
        {
            "있음": by["has"].mean().map("{:.1%}".format),
            "길이 중앙값": by["length"].median().astype(int),
            "두 점수 같음": by["agree"].mean().map("{:.1%}".format),
            "서로 다른 문장 비율": by["feedback"].agg(
                lambda s: f"{s.nunique() / len(s):.1%}"
            ),
            # 품질 점검: 이유 문장에 점수가 적혀 있으면 교사가 문장 대신 숫자를 읽음
            "숫자 포함": by["feedback"].agg(
                lambda s: f"{s.str.contains(r'[0-9０-９]').mean():.1%}"
            ),
            "점수 표현(N점)": by["feedback"].agg(
                lambda s: f"{s.str.contains(SCORE_PAT).mean():.1%}"
            ),
            "20자 미만": by["length"].agg(lambda s: f"{(s < 20).mean():.1%}"),
        }
    )
    print(table.reindex(ITEMS).to_string())
    print(
        "※ 점수 표현(N점)이 몇 %라도 있으면 교사 학습 전에 그 표현을 지우는 처리가 필요"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Hub 라벨 zip → 이유 문장 표")
    parser.add_argument("--descriptive-zip", type=Path, help="71818 서술형 zip")
    parser.add_argument("--essay-zip", type=Path, help="71819 논술형 zip")
    parser.add_argument("--out-dir", type=Path, default=M2_DIR / "data")
    args = parser.parse_args()
    jobs = [(args.descriptive_zip, "서술형"), (args.essay_zip, "논술형")]
    if not any(z for z, _ in jobs):
        parser.error("zip 경로를 하나 이상 주세요")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for zip_path, name in jobs:
        if zip_path is None:
            continue
        df = pd.DataFrame(
            [r for _, j in iter_label_json(zip_path) for r in rows_of(j)]
        )
        out = args.out_dir / f"{name}_이유.csv.gz"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        summary(df, name)
        print(f"저장: {out}")


if __name__ == "__main__":
    main()
