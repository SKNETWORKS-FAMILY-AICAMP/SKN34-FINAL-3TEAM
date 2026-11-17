"""답변 표현 분류(#690) 학습 데이터 정리.

공개 데이터 라벨을 2분류(1 = 막을 글, 0 = 정상)로 통일하고 나눈다.

쓰는 자료(라이선스 확인 11/16, learning.md 16장 분류 모델 단계)
- K-MHaS(CC BY-SA 4.0): `kmhas_{train,valid,test}.txt`(document·label)
  라벨 0~7 혐오 범주, 8 = not_hate → 8만 있으면 0, 그 밖의 라벨이 하나라도 있으면 1
- Korean HateSpeech BEEP!(CC BY-SA 4.0): `labeled/{train,dev}.tsv`(comments·hate)
  → hate·offensive = 1, none = 0
- APEACH(CC BY-SA 4.0, 평가 전용): 선택. `text`·`class` 칸 CSV(1 = 혐오) → 따로 시험셋으로만

나누기: 학습 = K-MHaS train + BEEP! train, 검증 = K-MHaS valid + BEEP! dev,
시험 = K-MHaS test, 외부 시험 = APEACH.
같은 글(공백 정리 뒤)이 검증·시험에 있으면 학습에서 빼고,
같은 나누기 안 중복은 하나만 둔다(라벨이 다르면 둘 다 뺌).
원자료·결과는 `data/`(gitignore)에만 둔다. 외부 API로 보내지 않는다. 표준 라이브러리만 쓴다.

    python -I scripts/prepare_data.py --kmhas <K-MHaS/data 폴더> \
        --beep <korean-hate-speech/labeled 폴더> [--apeach <APEACH csv>] --out data/processed
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys
from collections import Counter

KMHAS_NOT_HATE = "8"
BEEP_BLOCK = {"hate", "offensive"}
BEEP_OK = {"none"}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def kmhas_label(raw: str) -> int:
    labels = {x.strip() for x in raw.split(",") if x.strip()}
    if not labels or not labels <= set("012345678"):
        raise ValueError(f"K-MHaS 라벨 형식 오류: {raw!r}")
    return 0 if labels == {KMHAS_NOT_HATE} else 1


def beep_label(raw: str) -> int:
    v = raw.strip()
    if v in BEEP_BLOCK:
        return 1
    if v in BEEP_OK:
        return 0
    raise ValueError(f"BEEP! 라벨 형식 오류: {raw!r}")


def read_kmhas(path: pathlib.Path, source: str) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f, delimiter="\t")
        return [
            {"text": norm(x["document"]), "label": kmhas_label(x["label"]), "source": source}
            for x in r
        ]


def read_beep(path: pathlib.Path, source: str) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f, delimiter="\t")
        return [
            {"text": norm(x["comments"]), "label": beep_label(x["hate"]), "source": source}
            for x in r
        ]


def read_apeach(path: pathlib.Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return [{"text": norm(x["text"]), "label": int(x["class"]), "source": "apeach"} for x in r]


def dedup(rows: list[dict]) -> tuple[list[dict], int]:
    """같은 글은 하나만, 라벨이 갈리면 모두 뺌. 뺀 줄 수를 같이 돌려줌."""
    by: dict[str, set[int]] = {}
    for x in rows:
        if x["text"]:
            by.setdefault(x["text"], set()).add(x["label"])
    seen, out = set(), []
    for x in rows:
        t = x["text"]
        if not t or len(by[t]) > 1 or t in seen:
            continue
        seen.add(t)
        out.append(x)
    return out, len(rows) - len(out)


def build(kmhas: pathlib.Path, beep: pathlib.Path, apeach: pathlib.Path | None = None) -> dict:
    splits = {
        "train": read_kmhas(kmhas / "kmhas_train.txt", "kmhas")
        + read_beep(beep / "train.tsv", "beep"),
        "valid": read_kmhas(kmhas / "kmhas_valid.txt", "kmhas")
        + read_beep(beep / "dev.tsv", "beep"),
        "test": read_kmhas(kmhas / "kmhas_test.txt", "kmhas"),
    }
    if apeach:
        splits["apeach"] = read_apeach(apeach)
    removed = {}
    for k in splits:
        splits[k], removed[k] = dedup(splits[k])
    held = {x["text"] for k in splits if k != "train" for x in splits[k]}
    before = len(splits["train"])
    splits["train"] = [x for x in splits["train"] if x["text"] not in held]
    removed["trainOverlap"] = before - len(splits["train"])
    return {"splits": splits, "removed": removed}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kmhas", required=True, type=pathlib.Path)
    ap.add_argument("--beep", required=True, type=pathlib.Path)
    ap.add_argument("--apeach", type=pathlib.Path)
    ap.add_argument("--out", default=pathlib.Path("data/processed"), type=pathlib.Path)
    args = ap.parse_args(argv)
    result = build(args.kmhas, args.beep, args.apeach)
    args.out.mkdir(parents=True, exist_ok=True)
    stats = {"removed": result["removed"], "splits": {}}
    for name, rows in result["splits"].items():
        with (args.out / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for x in rows:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        c = Counter(x["label"] for x in rows)
        stats["splits"][name] = {
            "n": len(rows),
            "block": c[1],
            "ok": c[0],
            "bySource": dict(Counter(x["source"] for x in rows)),
        }
        print(f"{name}: {len(rows)}개 (막을 글 {c[1]} · 정상 {c[0]})")
    print(f"뺀 줄: {result['removed']}")
    (args.out / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    sys.exit(main())
