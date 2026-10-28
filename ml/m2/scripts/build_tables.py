"""AI Hub 라벨 zip을 풀지 않고 읽어서 학습용 표(CSV)를 만든다.

원본 zip 구조 (zip 안에 zip이 들어 있음):
    25.서술형 글쓰기 평가 데이터.zip
      └ .../Training/02.라벨링데이터/TL_1. 초5_1. 국어.zip   ← 라벨 zip
            └ 14-1-E5-N-0A-0014.json                       ← 학생 답 1개
      └ .../Training/01.원천데이터/TS_....zip              ← 원천(안 씀)

라벨 JSON 하나 = 학생 답 하나:
    essay_question  문항 (id, 과목, 학년, 지시문, 핵심어)
    essay_answer    학생 답 (id, 글)
    score.personal  전문가 2인 점수 (holistic 총점, analytic 8개 항목)
    rubric          항목 이름 (논술형은 글 종류에 따라 이름이 다름)

이름이 TL_/VL_로 시작하는 라벨 zip만 읽고, 원천 데이터(TS_/VS_)는 쓰지 않는다.
학생 개인정보(지역·성별)는 표에 넣지 않는다.

실행:
    python scripts/build_tables.py \
        --descriptive-zip "<25.서술형 글쓰기 평가 데이터.zip 경로>" \
        --essay-zip "<26.논술형 글쓰기 평가 데이터.zip 경로>"
출력 (data/):
    서술형_답안.csv, 서술형_문항.csv, 논술형_답안.csv.gz, 논술형_문항.csv

71817 주제별 글쓰기(성인)도 같은 구조라 같이 만들 수 있다 (학습에만 추가하는 용도):
    python scripts/build_tables.py --adult-zip "<27.주제별 글쓰기 평가 데이터 zip 경로>"
    → 성인_답안.csv.gz, 성인_문항.csv
    - 문항 id가 71819(A01 등)와 겹쳐서 앞에 "T_"를 붙인다
    - 학년 칸은 "성인"으로 통일 (입력에 [학년] 성인으로 들어감)
    - 같은 지시문이 연령대(20~30대/40대 이상)별로 id가 달라서, 지시문이 같으면 같은 문항으로 묶는다
"""

import argparse
import io
import json
import re
import zipfile
from pathlib import Path

import pandas as pd

M2_DIR = Path(__file__).resolve().parent.parent
PROMPT_COLS = ["prompt", "topic", "level", "keyword"]


def decode_name(name: str) -> str:
    # 일부 zip은 한글 파일명을 '#Uc11c' 같은 형태로 저장한다 → 한글로 되돌림
    return re.sub(r"#U([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), name)


def iter_label_json(zip_path: Path):
    # 바깥 zip → 안쪽 라벨 zip(TL_/VL_) → JSON 순서로 하나씩 꺼낸다
    outer = zipfile.ZipFile(zip_path)
    for info in outer.infolist():
        base = decode_name(info.filename).split("/")[-1]
        if not (base.startswith(("TL_", "VL_")) and base.endswith(".zip")):
            continue
        split = "train" if base.startswith("TL_") else "valid"
        inner = zipfile.ZipFile(io.BytesIO(outer.read(info)))
        for name in inner.namelist():
            if name.endswith(".json"):
                j = json.loads(inner.read(name).decode("utf-8-sig"))
                # 여러 데이터가 한 zip에 섞여 있어도 글쓰기 평가 JSON만 쓴다 (동화 질의응답 등은 건너뜀)
                if isinstance(j, dict) and "essay_question" in j and "score" in j:
                    yield split, j


def essay_type_of(item_name: str) -> str:
    # 논술형 content_1 항목 이름으로 글 종류를 알 수 있다
    if "설명" in item_name:
        return "설명"
    if "주장" in item_name:
        return "주장"
    return "정서"


def to_row(split: str, j: dict, with_type: bool) -> dict:
    q, a, s = j["essay_question"], j["essay_answer"], j["score"]["personal"]
    row = {
        "split": split,
        "prompt_id": q["id"],
        "subject": q["subject"],
        "grade": q["grade"],
    }
    if with_type:
        row["essay_type"] = essay_type_of(j["rubric"]["analytic"]["content_1"]["name"])
    row |= {
        "level": q.get("level"),
        "topic": q.get("topic"),
        "prompt": q["prompt"],
        "keyword": q.get("keyword"),
        "answer_id": a["id"],
        "text": a["text"],
        "len_syllable": a["len_syllable"],
        "hol_r1": s["holistic"]["score"][0],
        "hol_r2": s["holistic"]["score"][1],
    }
    for item, v in s["analytic"].items():  # _r1 = 전문가 1, _r2 = 전문가 2
        row[f"{item}_r1"], row[f"{item}_r2"] = v["score"]
    return row


def build(
    zip_path: Path, with_type: bool, adult: bool = False
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = [to_row(split, j, with_type) for split, j in iter_label_json(zip_path)]
    df = pd.DataFrame(rows)
    if adult:
        # 지시문이 같으면 같은 문항 (연령대별 id 2개 → 1개). 71819 id와 안 겹치게 T_ 접두어
        first_id = df.groupby("prompt")["prompt_id"].transform("min")
        df["prompt_id"] = "T_" + first_id.astype(str)
        df["answer_id"] = "T_" + df["answer_id"].astype(str)
        df["grade"] = "성인"
    # 문항 정보는 답마다 반복되므로 문항 표로 따로 뺀다 (prompt_id로 연결)
    id_cols = ["prompt_id", "subject", "grade"] + (["essay_type"] if with_type else [])
    prompts = (
        df[id_cols + PROMPT_COLS].drop_duplicates("prompt_id").sort_values("prompt_id")
    )
    answers = df.drop(columns=PROMPT_COLS)
    return answers, prompts


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Hub 라벨 zip → 학습용 표")
    parser.add_argument("--descriptive-zip", type=Path, help="71818 서술형 zip")
    parser.add_argument("--essay-zip", type=Path, help="71819 논술형 zip")
    parser.add_argument("--adult-zip", type=Path, help="71817 주제별 글쓰기(성인) zip")
    parser.add_argument("--out-dir", type=Path, default=M2_DIR / "data")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    jobs = [
        (args.descriptive_zip, "서술형", False, ".csv", False),
        (args.essay_zip, "논술형", True, ".csv.gz", False),
        (args.adult_zip, "성인", True, ".csv.gz", True),
    ]
    if not any(j[0] for j in jobs):
        parser.error("zip 경로를 하나 이상 주세요")
    for zip_path, name, with_type, ext, adult in jobs:
        if zip_path is None:
            continue
        answers, prompts = build(zip_path, with_type, adult)
        answers.to_csv(
            args.out_dir / f"{name}_답안{ext}", index=False, encoding="utf-8-sig"
        )
        prompts.to_csv(
            args.out_dir / f"{name}_문항.csv", index=False, encoding="utf-8-sig"
        )
        print(f"{name}: 답 {len(answers):,}건, 문항 {len(prompts)}개")


if __name__ == "__main__":
    main()
