"""M1 평가: 같은 테스트 세트(학습에 안 쓴 문항 그룹)에서 기준선과 모델을 비교한다.

- 다수 클래스 기준선: 항상 가장 많은 답을 냄
- 규칙 기준선(정답 여부만): 풀이의 마지막 숫자 = 정답 숫자 / 정답 숫자가 풀이 어딘가에 있음
- M1 모델 (models/ 에 있을 때)

실행: uv run python scripts/evaluate.py   (옵션: --split val, --limit 2000, --model 다른/폴더)
결과: results/eval_m1.md
학년별 결과를 따로 적는다. 이 점수는 '71716 손글씨 OCR 풀이'에 대한 것이고,
앱에서 학생이 직접 친 풀이에 대한 정확도가 아니다 → 자체 미션 표본 평가는 따로 한다.
"""

import argparse
import csv
import random
import re
import sys
from collections import Counter, defaultdict

from common import GRADE_NAMES, MODEL_DIR, REPORT_DIR, WORK_DIR

NUM = re.compile(r"\d+(?:\.\d+)?(?:/\d+)?")


def rows(split="test", limit=0):
    with open(WORK_DIR / "records.csv", encoding="utf-8-sig") as f:
        rs = [r for r in csv.DictReader(f) if r["split"] == split]
    return random.Random(0).sample(rs, limit) if limit and len(rs) > limit else rs


def rule_is_correct(r):
    ref = r["input_a"].split("정답:")[-1] if "정답:" in r["input_a"] else ""
    ref_nums = set(NUM.findall(ref))
    sol_nums = NUM.findall(r["input_b"])
    return int(bool(ref_nums) and bool(sol_nums) and sol_nums[-1] in ref_nums)


def rule_contains(r):
    ref = r["input_a"].split("정답:")[-1] if "정답:" in r["input_a"] else ""
    ref_nums = set(NUM.findall(ref))
    return int(bool(ref_nums) and ref_nums <= set(NUM.findall(r["input_b"])))


def binary(y, p):
    """1 = 정답(또는 '있음').

    과대판정률 = 실제 0을 1로 본 비율, 과소판정률 = 실제 1을 0으로 본 비율.
    """
    y, p = list(map(int, y)), list(map(int, p))
    neg = [b for a, b in zip(y, p, strict=False) if a == 0]
    pos = [b for a, b in zip(y, p, strict=False) if a == 1]
    over = sum(b == 1 for b in neg) / max(len(neg), 1)
    under = sum(b == 0 for b in pos) / max(len(pos), 1)
    return {
        "n": len(y),
        "정확도": sum(a == b for a, b in zip(y, p, strict=False)) / max(len(y), 1),
        "균형정확도": 1 - (over + under) / 2,
        "과대판정률": over,
        "과소판정률": under,
    }


def multiclass(y, p):
    by = defaultdict(list)
    for a, b in zip(y, p, strict=False):
        by[a].append(a == b)
    return {
        "n": len(y),
        "정확도": sum(a == b for a, b in zip(y, p, strict=False)) / max(len(y), 1),
        "균형정확도": sum(sum(v) / len(v) for v in by.values()) / max(len(by), 1),
        **{f"재현율[{k}]": sum(v) / len(v) for k, v in sorted(by.items())},
    }


def fmt(m):
    return " | ".join(f"{v:.3f}" if isinstance(v, float) else str(v) for v in m.values())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default=str(MODEL_DIR))
    args = ap.parse_args(argv)
    test = rows(args.split, args.limit)
    if not test:
        print("평가할 레코드가 없어요. prepare.py를 먼저 실행하세요.")
        return 1

    y = [int(r["is_correct"]) for r in test]
    maj = Counter(y).most_common(1)[0][0]
    res = {
        "다수 클래스": binary(y, [maj] * len(y)),
        "규칙(마지막 숫자=정답)": binary(y, [rule_is_correct(r) for r in test]),
        "규칙(정답 숫자가 풀이에 있음)": binary(y, [rule_contains(r) for r in test]),
    }

    import model as rt

    preds = None
    if rt.available(args.model):
        print(f"M1 예측 중… ({len(test)}건)")
        preds = rt.predict_many([(r["input_a"], r["input_b"]) for r in test], args.model)
        res["M1"] = binary(y, [int(p["is_correct"]) for p in preds])
    else:
        print(f"{args.model} 에 모델이 없어 M1 평가는 건너뛰어요.")

    L = [
        "# M1 평가 결과",
        "",
        f"- 평가 세트: `{args.split}` {len(test)}건 (학습에 안 쓴 문항 그룹)",
        "- 데이터: 71716 손글씨 풀이 OCR 텍스트. "
        "앱에서 직접 친 풀이의 정확도는 자체 미션 표본으로 따로 잰다.",
        "",
        "## 정답 여부 (1=정답)",
        "",
        "| 방법 | n | 정확도 | 균형정확도 | 과대판정률 | 과소판정률 |",
        "|---|---|---|---|---|---|",
    ]
    L += [f"| {k} | {fmt(m)} |" for k, m in res.items()]

    if preds:
        yr = [
            (int(r["has_required_error"]), int(p["has_required_error"]))
            for r, p in zip(test, preds, strict=False)
            if r["has_required_error"] not in ("", "None")
        ]
        yk = [
            (r["calc_accuracy"], p["calc_accuracy"])
            for r, p in zip(test, preds, strict=False)
            if r["calc_accuracy"]
        ]
        if yr:
            a, b = zip(*yr, strict=False)
            mr = binary(a, b)
            L += [
                "",
                "## 필수 과정 실수 있음 (1=있음)",
                "",
                "| 방법 | n | 정확도 | 균형정확도 | 과대판정률 | 과소판정률 |",
                "|---|---|---|---|---|---|",
                f"| 다수 클래스 | {fmt(binary(a, [Counter(a).most_common(1)[0][0]] * len(a)))} |",
                f"| M1 | {fmt(mr)} |",
                "",
                "여기서 과대판정률 = 실수가 없는데 있다고 본 비율, "
                "과소판정률 = 실수가 있는데 놓친 비율.",
            ]
        if yk:
            a, b = zip(*yk, strict=False)
            mk = multiclass(a, b)
            L += [
                "",
                "## 계산 정확도 클래스",
                "",
                "| 방법 | " + " | ".join(mk.keys()) + " |",
                "|---" * (len(mk) + 1) + "|",
                "| 다수 클래스 | "
                f"{fmt(multiclass(a, [Counter(a).most_common(1)[0][0]] * len(a)))} |",
                f"| M1 | {fmt(mk)} |",
            ]
        th = 0.8
        conf = [p for p in preds if min(p["p_correct"], p["p_required"], p["p_calc"]) >= th]
        L += [
            "",
            f"## 확신도 {th} 이상만 판정할 때",
            "",
            f"- 판정 비율 {len(conf) / len(preds):.1%} (나머지는 보류)",
        ]
        sel = [(yy, int(p["is_correct"])) for yy, p in zip(y, preds, strict=False) if p in conf]
        if sel:
            a, b = zip(*sel, strict=False)
            m = binary(a, b)
            L.append(
                f"- 판정한 것의 정답 여부 정확도 {m['정확도']:.3f} · "
                f"과대판정률 {m['과대판정률']:.3f} · 과소판정률 {m['과소판정률']:.3f}"
            )

        L += [
            "",
            "## 학년별 정답 여부 (M1)",
            "",
            "| 학년 | n | 정확도 | 균형정확도 | 과대판정률 | 과소판정률 |",
            "|---|---|---|---|---|---|",
        ]
        by = defaultdict(lambda: ([], []))
        for r, p in zip(test, preds, strict=False):
            by[r["grade"]][0].append(int(r["is_correct"]))
            by[r["grade"]][1].append(int(p["is_correct"]))
        for g, (a, b) in sorted(by.items()):
            L.append(f"| {GRADE_NAMES.get(g, g)} | {fmt(binary(a, b))} |")
    L += [
        "",
        "허용 기준(예: 과대판정률 상한)은 평가 전에 팀이 정하고, "
        "통과해도 '71716 기준'이라고만 적는다.",
    ]

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "eval_m1.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\n저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
