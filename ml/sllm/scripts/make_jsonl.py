"""AI Hub 71818 서술형·71819 논술형 → 설명 sLLM 학습용 JSONL.

한 줄 = 답 1개. 입력은 (글 종류·학년·주제·학생 글·항목 점수), 출력은 항목별 전문가 이유 문장.
"N점" 같은 점수 표현이 들어간 문장, 너무 짧은 문장은 그 항목만 뺀다(입력 점수 목록에서도 같이 뺌).

RunPod 안에서만 돌린다. 화면에는 숫자(개수)만 찍고 글·문장 내용은 찍지 않는다.

실행:
    python make_jsonl.py --data-dir /workspace/data/feedback --out-dir /workspace/data/jsonl
"""

import argparse
import json
import math
import random
import re
from pathlib import Path

import pandas as pd

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
# 추론 때도 이 이름 그대로 써야 한다
LABELS = {
    "hol": "종합",
    "task_1": "과제 수행",
    "content_1": "내용 1",
    "content_2": "내용 2",
    "content_3": "내용 3",
    "organization_1": "조직 1",
    "organization_2": "조직 2",
    "expression_1": "표현 1",
    "expression_2": "표현 2",
}
SOURCES = {
    "서술형": ("서술형_답안.csv", "서술형_이유.csv.gz"),
    "논술형": ("논술형_답안.csv.gz", "논술형_이유.csv.gz"),
}
SCORE_PAT = re.compile(r"[0-9０-９]\s*점")
# 학부모에게 보일 문장이라 점수·채점 이야기를 하는 문장은 숫자가 없어도 뺀다
GRADING_PAT = re.compile(r"점수|감점|가점|배점|만점|부여|채점|높은 점|낮은 점")
QUOTE = re.compile(r"[\"“”'‘’]([^\"“”'‘’]{2,80})[\"“”'‘’]")
INSTRUCTION = (
    "아래 학생 글을 항목별 점수에 맞게 설명하세요. "
    "점수 숫자는 쓰지 말고, 글에서 근거를 찾아 항목마다 한두 문장으로 씁니다. "
    "주어진 항목만, 주어진 순서대로 '- 항목: 설명' 형식으로 씁니다."
)


def bare(text: str) -> str:
    # 띄어쓰기·문장부호를 빼고 비교 (전문가가 띄어쓰기만 고쳐 옮긴 인용은 살림)
    return re.sub(r"[\s.,!?·~…\-]", "", text)


def bad_quote(feedback: str, essay_bare: str) -> bool:
    return any(bare(q) and bare(q) not in essay_bare for q in QUOTE.findall(feedback))


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def usable(feedback: str, min_len: int) -> bool:
    return len(feedback) >= min_len and not SCORE_PAT.search(feedback)


def score_of(r1, r2) -> int | None:
    vals = [v for v in (r1, r2) if pd.notna(v)]
    if not vals:
        return None
    # 두 전문가 평균을 사사오입 (파이썬 round는 2.5→2라서 쓰지 않음)
    return int(math.floor(sum(vals) / len(vals) + 0.5))


def build_prompt(kind: str, row, scored: list[tuple[str, int]]) -> str:
    lines = [INSTRUCTION, "", f"[글 종류] {kind}"]
    if isinstance(row.get("essay_type"), str):
        lines.append(f"[세부 종류] {row['essay_type']}")
    lines += [
        f"[학년] {row['grade']}",
        f"[주제] {row['subject']}",
        "[글]",
        clean(row["text"]),
        "",
        "[항목 점수 (1~5)]",
    ]
    lines += [f"- {LABELS[item]}: {score}" for item, score in scored]
    return "\n".join(lines)


def records(data_dir: Path, kind: str, min_len: int, min_items: int):
    answer_file, reason_file = SOURCES[kind]
    answers = pd.read_csv(data_dir / answer_file).drop_duplicates("answer_id")
    reasons = pd.read_csv(data_dir / reason_file).drop_duplicates(["answer_id", "item"])
    answers["answer_id"] = answers["answer_id"].astype(str)
    reasons["answer_id"] = reasons["answer_id"].astype(str)
    reasons["feedback"] = reasons["feedback"].fillna("").map(clean)
    by_answer = {k: g.set_index("item") for k, g in reasons.groupby("answer_id")}
    stats = {
        "답": 0, "항목 칸": 0, "점수 표현으로 뺌": 0, "채점 이야기로 뺌": 0,
        "원문에 없는 인용으로 뺌": 0, "짧아서 뺌": 0, "항목 부족으로 뺀 답": 0,
    }
    for row in answers.to_dict("records"):
        group = by_answer.get(row["answer_id"])
        if group is None or not isinstance(row.get("text"), str):
            continue
        scored, outputs = [], []
        essay_bare = bare(clean(row["text"]))
        for item in ITEMS:
            if item not in group.index:
                continue
            r = group.loc[item]
            stats["항목 칸"] += 1
            score = score_of(r["r1"], r["r2"])
            fb = r["feedback"]
            if score is None or not fb:
                continue
            if SCORE_PAT.search(fb):
                stats["점수 표현으로 뺌"] += 1
                continue
            if GRADING_PAT.search(fb):
                stats["채점 이야기로 뺌"] += 1
                continue
            if bad_quote(fb, essay_bare):
                stats["원문에 없는 인용으로 뺌"] += 1
                continue
            if len(fb) < min_len:
                stats["짧아서 뺌"] += 1
                continue
            scored.append((item, score))
            outputs.append(f"- {LABELS[item]}: {fb}")
        if len(scored) < min_items:
            stats["항목 부족으로 뺀 답"] += 1
            continue
        stats["답"] += 1
        yield row["split"], {
            "id": f"{kind}:{row['answer_id']}",
            "kind": kind,
            "len_syllable": row.get("len_syllable"),
            "messages": [
                {"role": "user", "content": build_prompt(kind, row, scored)},
                {"role": "assistant", "content": "\n".join(outputs)},
            ],
        }
    print(f"{kind}: " + ", ".join(f"{k} {v:,}" for k, v in stats.items()))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, default=Path("/workspace/data/feedback"))
    p.add_argument("--out-dir", type=Path, default=Path("/workspace/data/jsonl"))
    p.add_argument("--max-train", type=int, default=8000, help="학습 답 수 (종류별 반씩)")
    p.add_argument("--max-valid", type=int, default=200, help="검증 답 수 (종류별 반씩)")
    p.add_argument("--max-syllable", type=int, default=1500, help="이보다 긴 글은 뺌")
    p.add_argument("--min-len", type=int, default=15, help="이유 문장 최소 글자 수")
    p.add_argument("--min-items", type=int, default=5, help="답마다 최소 항목 수")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    rng = random.Random(args.seed)
    pools = {"train": {}, "valid": {}}
    for kind in SOURCES:
        for split, rec in records(args.data_dir, kind, args.min_len, args.min_items):
            n = rec.pop("len_syllable")
            if pd.notna(n) and n > args.max_syllable:
                continue
            pools["valid" if split == "valid" else "train"].setdefault(kind, []).append(rec)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for split, limit in (("train", args.max_train), ("valid", args.max_valid)):
        chosen = []
        for kind, recs in pools[split].items():
            rng.shuffle(recs)
            chosen += recs[: limit // len(pools[split])]
        rng.shuffle(chosen)
        out = args.out_dir / f"{split}.jsonl"
        with out.open("w", encoding="utf-8") as f:
            for rec in chosen:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        counts = {k: sum(r["kind"] == k for r in chosen) for k in SOURCES}
        print(f"저장 {out}: {len(chosen):,}개 {counts}")


if __name__ == "__main__":
    main()
