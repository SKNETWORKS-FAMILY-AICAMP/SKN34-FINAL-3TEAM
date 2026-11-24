"""아이 말투 학습 문장을 공개 데이터 학습셋에 더한다(#690 보완, 2026-11-17).

`eval_sets/kid_train.json`의 조각으로 짝 문장을 만든다.
- 주어 × 막을 말 / 정상 말, 집단 × 비하 / 존중, 그 밖 문장
시험 문장(`eval_sets/kid_test.json`)과 겹치면 멈춘다(같은 문장, 또는 공백 뺀 8글자 이상 같은 조각).
학습에만 더하고(검증·시험은 그대로), `repeat`번 반복해 넣는다. 모두 우리가 지은 문장이다.

    python -I scripts/kid_data.py --data data/processed --out data/processed_kid
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
from difflib import SequenceMatcher

HERE = pathlib.Path(__file__).resolve().parents[1]
TRAIN = HERE / "eval_sets/kid_train.json"
TEST = HERE / "eval_sets/kid_test.json"
MAX_SHARED = 7  # 공백 뺀 같은 조각이 이보다 길면 겹침
SOURCE = "kid-written"


def build(spec: dict) -> list[dict]:
    rows = []
    for s in spec["subjects"]:
        rows += [{"text": f"{s} {p}", "label": 1} for p in spec["directBlock"]]
        rows += [{"text": f"{s} {p}", "label": 0} for p in spec["directPass"]]
    for g in spec["groups"]:
        rows += [{"text": f"{g} {p}", "label": 1} for p in spec["groupBlock"]]
        rows += [{"text": f"{g} {p}", "label": 0} for p in spec["groupPass"]]
    rows += [{"text": t, "label": 1} for t in spec["extraBlock"]]
    rows += [{"text": t, "label": 0} for t in spec["extraPass"]]
    seen, out = set(), []
    for r in rows:
        if r["text"] not in seen:
            seen.add(r["text"])
            out.append({**r, "source": SOURCE})
    return out


def squash(text: str) -> str:
    return "".join(text.split())


def longest_shared(a: str, b: str) -> int:
    a, b = squash(a), squash(b)
    return SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b)).size


def overlaps(rows: list[dict], tests: list[str], limit: int = MAX_SHARED) -> list[tuple]:
    """시험 문장과 겹치는 학습 문장: (길이, 학습, 시험). 같은 틀·다른 내용 조각은 limit 이하."""
    found = []
    pieces = {r["text"] for r in rows}
    for t in tests:
        for p in pieces:
            n = longest_shared(p, t)
            if n > limit or squash(p) == squash(t):
                found.append((n, p, t))
    return sorted(found, reverse=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=pathlib.Path("data/processed"), type=pathlib.Path)
    ap.add_argument("--out", default=pathlib.Path("data/processed_kid"), type=pathlib.Path)
    args = ap.parse_args(argv)
    spec = json.loads(TRAIN.read_text(encoding="utf-8"))
    test = json.loads(TEST.read_text(encoding="utf-8"))
    rows = build(spec)
    bad = overlaps(rows, test["block"] + test["pass"])
    if bad:
        for n, p, t in bad[:20]:
            print(f"겹침 {n}자: 학습 {p!r} ↔ 시험 {t!r}")
        raise SystemExit(f"시험 문장과 겹치는 학습 문장 {len(bad)}개")
    args.out.mkdir(parents=True, exist_ok=True)
    base = (args.data / "train.jsonl").read_text(encoding="utf-8").splitlines()
    extra = [json.dumps(r, ensure_ascii=False) for r in rows] * spec["repeat"]
    (args.out / "train.jsonl").write_text("\n".join([*base, *extra]) + "\n", encoding="utf-8")
    for name in ("valid", "test", "apeach"):
        if (args.data / f"{name}.jsonl").is_file():
            shutil.copyfile(args.data / f"{name}.jsonl", args.out / f"{name}.jsonl")
    pos = sum(r["label"] for r in rows)
    stats = {
        "kidRows": len(rows),
        "kidBlock": pos,
        "kidPass": len(rows) - pos,
        "repeat": spec["repeat"],
        "baseTrain": len(base),
        "train": len(base) + len(extra),
    }
    (args.out / "kid_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False), encoding="utf-8"
    )
    print(stats)


if __name__ == "__main__":
    main()
