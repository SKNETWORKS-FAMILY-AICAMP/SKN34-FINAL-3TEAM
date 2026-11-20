"""아이 시험 문장(`eval_sets/kid_test.json`)을 모양만 바꾼 시험을 만든다(#690, 2026-11-19).

같은 뜻인데 모양이 바뀌면 모델이 놓치는지(말 모양만 외웠는지) 본다.
학습 문장이 아니라 시험 문장에서 만들므로 학습과 겹치지 않는다.
바꿀 수 없는 문장은 그 모양에서 뺀다(어순은 "너는·넌·쟤는·걔는"으로 시작할 때,
물음 어미는 상대에게 하는 말일 때만).

    python scripts/kid_variants.py --out eval_sets/kid_test_variants.json
"""

from __future__ import annotations

import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parents[1]
TEST = HERE / "eval_sets/kid_test.json"
SUBJECTS = ("너는 ", "넌 ", "쟤는 ", "걔는 ")  # 어순 바꾸기: 주어가 확실한 것만
YOU = (
    "너는 ",
    "넌 ",
    "너 ",
    "니가 ",
    "네가 ",
)  # 물음 어미: 상대에게 하는 말만(집단 비하를 물음으로 바꾸면 뜻이 달라짐)


def strip_end(t: str) -> str:
    return t.rstrip(".!?~ ")


def no_space(t: str) -> str:
    return "".join(t.split())


def no_period(t: str) -> str | None:
    s = strip_end(t)
    return s if s != t else None


def invert(t: str) -> str | None:
    for s in SUBJECTS:
        if t.startswith(s):
            return f"{strip_end(t[len(s) :])} {s.strip()}"
    return None


def laugh(t: str) -> str:
    return f"{strip_end(t)} ㅋㅋ"


def question(t: str) -> str | None:
    if not t.startswith(YOU):
        return None
    s = strip_end(t)
    for end, new in (("이야", "이냐"), ("야", "냐"), ("해", "하냐"), ("어", "냐"), ("다", "냐")):
        if s.endswith(end):
            return s[: -len(end)] + new + "?"
    return None


VARIANTS = {
    "original": lambda t: t,
    "noSpace": no_space,
    "noPeriod": no_period,
    "invert": invert,
    "laugh": laugh,
    "question": question,
}


def build(test: dict) -> dict:
    out = {"block": [], "pass": [], "parts": {}}
    for name, fn in VARIANTS.items():
        b = [v for v in (fn(t) for t in test["block"]) if v]
        p = [v for v in (fn(t) for t in test["pass"]) if v]
        out["block"] += b
        out["pass"] += p
        out["parts"][name] = {"block": len(b), "pass": len(p)}
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=HERE / "eval_sets/kid_test_variants.json", type=pathlib.Path)
    a = ap.parse_args(argv)
    out = build(json.loads(TEST.read_text(encoding="utf-8")))
    out = {
        "note": "kid_test.json(직접 지은 문장)을 모양만 바꾼 시험, kid_variants.py가 만듦",
        **out,
    }
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out["parts"])


if __name__ == "__main__":
    main()
