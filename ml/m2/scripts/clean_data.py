"""학습용 표 정제 → data/clean/ (원래 data/ 표는 그대로 둠, 커밋 금지: 데이터)

10/30 품질 점검(scripts/_check_quality.py) 결과로 수빈 님이 정한 처리만 한다.
  1. 글 정리 (맞춤법·띄어쓰기는 고치지 않음 — 표현·맞춤법 항목이 그 실수를 채점하므로)
     - 유니코드 NFC 통일, 제어 문자 삭제, 연속 공백·탭을 공백 하나로 (줄바꿈은 남김)
     - `#@...#` 표시 (10/30 11:07 개수 확인: 세 데이터 모두 100% `#@`로 열고 `#`로 닫힘, 5~9자)
       · 서술·71819: 가림 표시로 보임(뒤에 조사가 바로 붙는 비율 87~88%, 모양 15종) → "○○"로 바꿈 (문장 유지)
       · 545: 구분 기호로 보임(한 편에 약 10개, 모양 8종, 전부 7자) → 지움
       · 성격은 추정. 데이터 설명서로 확정 후 --marker-pattern·바꿀 말 조정
  2. 중복 (C ①): 정리한 글이 완전히 같은 답은 1건만 남김 (평가 쪽(AI Hub VL) 것을 우선)
     - 545: 채점자별 점수를 묶음 평균 (점수가 원래 소수)
     - 서술·71819: 남긴 1건의 점수 그대로 (정수여야 QWK 계산이 됨, 묶음 2·19개뿐)
  3. 채점자 차이 큰 칸 (D)은 여기서 빼지 않음 → 학습 때 --mask-disagree 옵션으로 학습에서만 제외
  4. 문단 경계(B)는 이번엔 그대로 (--keep-paragraph는 아직 없음, 545는 원본 zip에서 다시 만들어야 함)
  5. 기타 잡음(HTML 태그·가림 표시·이모지 등, E)은 종류 확인 전이라 건드리지 않음

화면에는 처리 건수만 낸다 (글 내용 출력 X).
실행: uv run python scripts/clean_data.py
학습: train.py --data-dir data/clean / train_545.py --data-dir data/clean
"""

import argparse
import re
import shutil
import unicodedata
from pathlib import Path

import pandas as pd

M2 = Path(__file__).resolve().parent.parent
# "#@"로 열고 "#"로 닫히는 표시 (공백 없이 20자 이내). 10/30 확인: 세 데이터 모두 이 모양 100%
DEFAULT_MARKER = r"#@[^\s#]{1,20}#"
CTRL = r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"

# (원본 파일, 문항 파일, 평가 쪽 split 값, 표시를 바꿀 말)
JOBS = {
    "서술": ("서술형_답안.csv", "서술형_문항.csv", "valid", "○○"),
    "논술71819": ("논술형_답안.csv.gz", "논술형_문항.csv", "valid", "○○"),
    "545": ("에세이545_답안.csv.gz", None, "VL", " "),
}


def clean_text(s: pd.Series, marker: str, repl: str) -> tuple[pd.Series, dict]:
    t = s.fillna("").map(lambda x: unicodedata.normalize("NFC", x))
    n_marker = int(t.str.contains(marker, regex=True).sum())
    n_ctrl = int(t.str.contains(CTRL, regex=True).sum())
    before = t.str.len()
    t = t.str.replace(marker, repl, regex=True)
    t = t.str.replace(CTRL, "", regex=True)
    t = t.str.replace(r"[ \t 　]+", " ", regex=True)  # 줄바꿈은 남김
    t = t.str.replace(r" *\n *", "\n", regex=True).str.strip()
    removed = (before - t.str.len()).clip(lower=0)
    stats = {
        "표시 바꾼·지운 답": n_marker,
        "제어 문자 지운 답": n_ctrl,
        "줄어든 글자 수 평균(표시 있던 답)": round(
            float(removed[s.fillna("").str.contains(marker, regex=True)].mean()), 1
        )
        if n_marker
        else 0.0,
        "정리 후 빈 답": int((t.str.len() == 0).sum()),
    }
    return t, stats


def dedupe(
    df: pd.DataFrame, eval_value: str, average: bool
) -> tuple[pd.DataFrame, dict]:
    score_cols = [c for c in df.columns if re.search(r"_r[123]$", c)]
    key = df["text"].str.replace(r"\s+", " ", regex=True)
    df = df.assign(_k=key, _eval=(df["split"] == eval_value).astype(int))
    size = df.groupby("_k")["_k"].transform("size")
    n_group = int(df.loc[size > 1, "_k"].nunique())
    n_dup = int((size > 1).sum())
    if average:
        # 묶음 안 점수 평균 → 남길 1건(평가 쪽 우선)에 넣음 (545: 점수가 원래 소수)
        df[score_cols] = df.groupby("_k")[score_cols].transform("mean")
    # 서술·71819는 채점자 점수가 정수여야 QWK 계산이 됨(baseline.evaluate) → 남긴 1건의 점수 그대로
    df = df.sort_values(["_k", "_eval"], ascending=[True, False], kind="stable")
    kept = df.drop_duplicates("_k", keep="first").sort_index()
    stats = {
        "중복 묶음": n_group,
        "중복에 속한 답": n_dup,
        "뺀 답": n_dup - n_group,
    }
    return kept.drop(columns=["_k", "_eval"]), stats


def main():
    ap = argparse.ArgumentParser(description="학습용 표 정제 → data/clean/")
    ap.add_argument("--data-dir", type=Path, default=M2 / "data")
    ap.add_argument("--out-dir", type=Path, default=M2 / "data" / "clean")
    ap.add_argument(
        "--marker-pattern",
        default=DEFAULT_MARKER,
        help=f"표시 정규식 (기본 {DEFAULT_MARKER})",
    )
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    print(f"표시 규칙: {args.marker_pattern}")
    rows = []
    for name, (f, prompt_f, eval_value, repl) in JOBS.items():
        src = args.data_dir / f
        if not src.exists():
            print(f"{name}: {f} 없음, 건너뜀")
            continue
        df = pd.read_csv(src)
        n0 = len(df)
        df["text"], s1 = clean_text(df["text"], args.marker_pattern, repl)
        df, s2 = dedupe(df, eval_value, average=(name == "545"))
        df.to_csv(args.out_dir / f, index=False, encoding="utf-8-sig")
        if prompt_f:
            shutil.copy(args.data_dir / prompt_f, args.out_dir / prompt_f)
        rows.append({"데이터": name, "원래 답": n0, **s1, **s2, "정제 후 답": len(df)})
    print(pd.DataFrame(rows).set_index("데이터").T.to_string())
    print(f"저장: {args.out_dir}")


if __name__ == "__main__":
    main()
