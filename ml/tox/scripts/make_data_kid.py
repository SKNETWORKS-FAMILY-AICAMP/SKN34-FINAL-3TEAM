"""아이 말투 재학습용 데이터 만들기(#690 후속, 11/18 실험·11/19 최종 모델).

`prepare_data.py`가 만든 `data/processed`(학습 86,095줄)에서 시작한다.
- p_orig: 원래 학습 그대로
- p_kid : 원래 + 직접 지은 아이 문장 ×3 ← 최종 모델
  (`kid_data.py`, `eval_sets/kid_train.json` 691줄, 11/18 놀림말·욕 정책)
- p_cont: 이어 학습 실험용(아이 691줄 ×1 + 원래에서 무작위 10,000줄, 시드 42)
valid·test·apeach는 그대로 복사한다(글 순서가 같아야 단어 목록 결과 `wordlist_flags.json`과 맞음).

    uv run python scripts/make_data_kid.py            # ml/tox에서 실행
"""

import argparse
import json
import pathlib
import random
import shutil
import subprocess
import sys

BASE_ROWS = 86095


def write(src: pathlib.Path, out: pathlib.Path, rows: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "train.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    for f in ("valid.jsonl", "test.jsonl", "apeach.jsonl"):
        shutil.copy(src / f, out / f)
    print(out.name, len(rows))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=pathlib.Path("data/processed"), type=pathlib.Path)
    ap.add_argument("--data", default=pathlib.Path("data"), type=pathlib.Path)
    a = ap.parse_args(argv)
    base = (a.src / "train.jsonl").read_text(encoding="utf-8").splitlines()[:BASE_ROWS]
    if len(base) != BASE_ROWS or any('"kid-written"' in x for x in base):
        raise ValueError(f"원래 학습 {BASE_ROWS}줄(아이 문장 없음)이 아님")
    write(a.src, a.data / "p_orig", base)
    script = pathlib.Path(__file__).with_name("kid_data.py")
    subprocess.run(
        [
            sys.executable,
            "-I",
            str(script),
            "--data",
            str(a.data / "p_orig"),
            "--out",
            str(a.data / "p_kid"),
        ],
        check=True,
    )
    stats = json.loads((a.data / "p_kid" / "kid_stats.json").read_text(encoding="utf-8"))
    kid_all = (
        (a.data / "p_kid" / "train.jsonl").read_text(encoding="utf-8").splitlines()[BASE_ROWS:]
    )
    kid = kid_all[: stats["kidRows"]]
    if len(kid_all) != stats["kidRows"] * stats["repeat"] or not all(
        '"kid-written"' in x for x in kid
    ):
        raise ValueError("아이 문장 줄 수가 kid_stats.json과 다름")
    write(a.src, a.data / "p_cont", kid + random.Random(42).sample(base, 10000))


if __name__ == "__main__":
    main()
