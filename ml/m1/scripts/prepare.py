"""71716 → 학습용 표 + 그룹 단위 분할.

실행 예:
  uv run python scripts/prepare.py "<110.수학 과목 자동 풀이 데이터 폴더>"
결과: work/records.csv (split 열: train / val / test)

분할 원칙
- AI Hub의 Training/Validation을 그대로 쓰지 않는다:
  문항은 다르지만 '그룹'(숫자만 바꾼 쌍둥이 문항)이
  양쪽에 겹쳐서 평가 점수가 부풀려진다.
- 그래서 Training+Validation을 합친 뒤 그룹 id 해시로 train 80 / val 10 / test 10 으로 다시 나눈다.
  같은 그룹의 모든 풀이는 반드시 한쪽에만 들어간다.
"""

import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path

from common import RAW_DIR, WORK_DIR, iter_items, model_input, to_record

SPLIT = (0.8, 0.1, 0.1)
FIELDS = [
    "question_id",
    "group_id",
    "grade",
    "unit",
    "topic_name",
    "input_a",
    "input_b",
    "is_correct",
    "has_required_error",
    "required_errors",
    "required_num",
    "calc_accuracy",
    "difficulty",
    "aihub_split",
    "split",
    "source",
]


def split_of(group_id):
    h = int(hashlib.md5(str(group_id).encode("utf-8")).hexdigest(), 16) % 1000 / 1000
    if h < SPLIT[0]:
        return "train"
    return "val" if h < SPLIT[0] + SPLIT[1] else "test"


def main(root=RAW_DIR):
    rows, bad, skipped = [], 0, 0
    for i, (src, aihub_split, obj) in enumerate(iter_items(root)):
        if isinstance(obj, Exception):
            bad += 1
            continue
        r = to_record(obj, src, aihub_split)
        if r is None:
            skipped += 1
            continue
        a, b = model_input(r["question"], r["reference_answer"], r["solution"])
        if not b:
            skipped += 1
            continue
        r.update(input_a=a, input_b=b, split=split_of(r["group_id"]))
        rows.append({k: r.get(k, "") for k in FIELDS})
        if (i + 1) % 20000 == 0:
            print(f"  {i + 1}건 처리")
    if not rows:
        print(f"레코드가 없어요: {root}  (TL_3/VL_3 손글씨풀이 라벨링 zip이 있는 폴더인지 확인)")
        return 1
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    out = WORK_DIR / "records.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    by_split = Counter(r["split"] for r in rows)
    groups = {s: {r["group_id"] for r in rows if r["split"] == s} for s in by_split}
    leak = groups.get("train", set()) & (groups.get("val", set()) | groups.get("test", set()))
    print(f"레코드 {len(rows)}개 저장 (읽기 실패 {bad}, 건너뜀 {skipped}) → {out}")
    print(
        "분할(그룹 단위): "
        + ", ".join(
            f"{s} {by_split[s]}건/{len(groups[s])}그룹"
            for s in ("train", "val", "test")
            if s in by_split
        )
    )
    print(f"train과 val/test에 함께 있는 그룹: {len(leak)}개 (0이어야 함)")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else RAW_DIR))
