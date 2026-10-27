"""기준선 모델 평가.

klue/roberta가 넘어야 할 바닥(기준선)과 천장(전문가 간 일치도)을 잰다.
모든 성적은 평가용(test) 문항으로만 내고, 학습은 공부용(train) 문항으로만 한다.

기준선
- majority: 공부용에서 제일 흔한 점수로 전부 찍기 (QWK는 항상 0)
- rule: 핵심어 개수 → 핵심어 항목(content_3) 점수. 서술형만 (논술형은 핵심어 없음)
- tfidf_logistic: 글자 2~4글자 조각 TF-IDF + 로지스틱 회귀 (점수를 이름표로)
- tfidf_ridge: 같은 TF-IDF + Ridge 회귀 (점수를 숫자로, 반올림)
- expert: 전문가1 vs 전문가2 (천장)
※ 학습 없는 LLM 기준선은 AI Hub 데이터를 외부 LLM에 보내지 않기로 해서 제외

지표
- QWK: 모델 vs 전문가1, 모델 vs 전문가2의 평균. 천장(전문가1 vs 2)과 같은 조건으로 비교하려고
- 균형정확도·과대·과소: 정답 = 두 전문가 평균 반올림(3.5 → 4)

실행: python scripts/baseline.py
출력: results/baseline_{dataset}.csv (전체 + 학년별 + 글종류별, 숫자만)
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import balanced_accuracy_score, cohen_kappa_score

M2_DIR = Path(__file__).resolve().parent.parent
ITEMS = [
    "hol",
    "task_1",
    "content_1",
    "content_2",
    "content_3",
    "organization_1",
    "organization_2",
    "expression_1",
    "expression_2",
]
DATASETS = {
    "descriptive": ("서술형_답안.csv", "서술형_문항.csv"),
    "essay": ("논술형_답안.csv.gz", "논술형_문항.csv"),
}


def top_score(item: str) -> int:
    # 총점(hol)은 데이터에 1~4점만 있음
    return 4 if item == "hol" else 5


def gold(data: pd.DataFrame, item: str) -> np.ndarray:
    avg = (data[f"{item}_r1"] + data[f"{item}_r2"]) / 2
    return np.floor(avg + 0.5).astype(int).to_numpy()


def evaluate(data: pd.DataFrame, item: str, pred: np.ndarray) -> dict:
    q1 = cohen_kappa_score(data[f"{item}_r1"], pred, weights="quadratic")
    q2 = cohen_kappa_score(data[f"{item}_r2"], pred, weights="quadratic")
    g = gold(data, item)
    return {
        "qwk": (q1 + q2) / 2,
        "balanced_acc": balanced_accuracy_score(g, pred),
        "over": float((pred > g).mean()),
        "under": float((pred < g).mean()),
    }


def count_keywords(text: str, keyword: str) -> int:
    words = [w.strip() for w in str(keyword).split(",") if w.strip()]
    return sum(w in text for w in words)


def predict_all(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """{(기준선 이름, 항목): 평가용 예측 점수}"""
    preds = {}

    # 한국어는 조사가 붙어서 단어 대신 글자 조각으로 자름. 공부용으로만 fit (평가용 커닝 방지)
    vec = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        min_df=3,
        sublinear_tf=True,
        max_features=200_000,
    )
    x_train = vec.fit_transform(train["text"])
    x_test = vec.transform(test["text"])

    for item in ITEMS:
        most = pd.Series(gold(train, item)).mode()[0]
        preds[("majority", item)] = np.full(len(test), most)

        clf = LogisticRegression(max_iter=2000)
        clf.fit(x_train, gold(train, item))
        preds[("tfidf_logistic", item)] = clf.predict(x_test)

        reg = Ridge(alpha=1.0)
        reg.fit(x_train, (train[f"{item}_r1"] + train[f"{item}_r2"]) / 2)
        raw = np.floor(reg.predict(x_test) + 0.5)
        preds[("tfidf_ridge", item)] = np.clip(raw, 1, top_score(item)).astype(int)

        preds[("expert", item)] = test[f"{item}_r2"].to_numpy()  # 아래에서 r1과 비교

    if test["keyword"].notna().all():
        # 채점 기준표: 핵심어 4개 이상 5점, 3개 4점, 2개 3점, 1개 2점, 없음 1점
        n = [count_keywords(t, k) for t, k in zip(test["text"], test["keyword"])]
        preds[("rule", "content_3")] = np.clip(np.array(n), 0, 4) + 1

    return preds


def score_table(test: pd.DataFrame, preds: dict, group_cols: list[str]) -> pd.DataFrame:
    rows = []
    groups = [("all", "all", test)]
    for col in group_cols:
        groups += [(col, value, part) for value, part in test.groupby(col)]

    for group_by, value, part in groups:
        idx = test.index.get_indexer(part.index)
        for (baseline, item), pred in preds.items():
            p = pred[idx]
            if baseline == "expert":
                q = cohen_kappa_score(part[f"{item}_r1"], p, weights="quadratic")
                metrics = {"qwk": q}
            else:
                metrics = evaluate(part, item, p)
            rows.append(
                {
                    "group_by": group_by,
                    "group": value,
                    "n": len(part),
                    "baseline": baseline,
                    "item": item,
                    **metrics,
                }
            )
    return pd.DataFrame(rows).round(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="M2 기준선 평가")
    parser.add_argument("--data-dir", type=Path, default=M2_DIR / "data")
    parser.add_argument("--split-dir", type=Path, default=M2_DIR / "splits")
    parser.add_argument("--out-dir", type=Path, default=M2_DIR / "results")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for name, (answer_file, prompt_file) in DATASETS.items():
        df = pd.read_csv(args.data_dir / answer_file)
        prompts = pd.read_csv(args.data_dir / prompt_file)
        split = pd.read_csv(args.split_dir / f"{name}_split_seed{args.seed}.csv")
        df = df.merge(prompts[["prompt_id", "keyword"]], on="prompt_id")
        df = df.merge(split[["prompt_id", "split_new"]], on="prompt_id")

        train = df[df["split_new"] == "train"].reset_index(drop=True)
        test = df[df["split_new"] == "test"].reset_index(drop=True)
        print(f"[{name}] 공부용 {len(train):,} / 평가용 {len(test):,} 답")
        if test.empty:
            raise SystemExit(f"[{name}] 평가용 답이 없음. 분할 파일을 확인하세요")

        preds = predict_all(train, test)
        group_cols = ["grade"] + (["essay_type"] if "essay_type" in test else [])
        table = score_table(test, preds, group_cols)
        table.to_csv(args.out_dir / f"baseline_{name}.csv", index=False)

        overall = table[table["group_by"] == "all"].pivot(
            index="item", columns="baseline", values="qwk"
        )
        print(overall.reindex(ITEMS).to_string(), "\n")


if __name__ == "__main__":
    main()
