"""71716 손글씨풀이 라벨링 데이터 구조 확인 (zip을 풀지 않고 바로 읽음).

실행 예:
  uv run python scripts/eda.py "<110.수학 과목 자동 풀이 데이터 폴더>"
  (인자를 안 주면 .env의 AIHUB_71716_DIR, 그것도 없으면 data/71716)
결과: work/reports/eda_71716.md (예시 절에 AI Hub 원문이 있어 커밋하지 않음, NFR-DAT-03)
"""

import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from common import EDA_REPORT_DIR as REPORT_DIR
from common import GRADE_NAMES, RAW_DIR, iter_items, latex_to_text, sources, to_record


def _dist(cnt):
    total = sum(cnt.values()) or 1
    return ", ".join(
        f"{k}={v} ({v / total:.0%})" for k, v in sorted(cnt.items(), key=lambda x: str(x[0]))
    )


def main(root=RAW_DIR):
    zips, loose = sources(root)
    if not zips and not loose:
        print(f"읽을 데이터가 없어요: {root}")
        print("TL_3.손글씨풀이_*.zip / VL_3.손글씨풀이_*.zip 이 들어 있는 폴더를 가리켜 주세요.")
        return 1
    print(f"zip {len(zips)}개, 풀어 둔 JSON {len(loose)}개 읽는 중…")

    n_rec = n_bad = n_skip = 0
    by_split_grade = Counter()
    labels = defaultdict(Counter)
    by_grade_correct = defaultdict(Counter)
    ox_check = Counter()
    groups = defaultdict(set)
    questions = defaultdict(set)
    raw_len, txt_len = [], []
    samples = []
    rng = random.Random(0)

    for i, (src, split, obj) in enumerate(iter_items(root)):
        if isinstance(obj, Exception):
            n_bad += 1
            continue
        r = to_record(obj, src, split)
        if r is None:
            n_skip += 1
            continue
        n_rec += 1
        by_split_grade[(r["aihub_split"], r["grade"])] += 1
        for k in (
            "is_correct",
            "has_required_error",
            "required_errors",
            "calc_accuracy",
            "difficulty",
        ):
            labels[k][r[k]] += 1
        by_grade_correct[r["grade"]][r["is_correct"]] += 1
        if r["filename_ox"]:
            ox_check[(r["filename_ox"], r["is_correct"])] += 1
        groups[r["aihub_split"]].add(r["group_id"])
        questions[r["aihub_split"]].add(r["question_id"])
        raw_len.append(len(r["solution"]))
        txt_len.append(len(latex_to_text(r["solution"])))
        if len(samples) < 6 and rng.random() < 0.002:
            samples.append(r)
        if (i + 1) % 20000 == 0:
            print(f"  {i + 1}건 읽음")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "eda_71716.md"
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0  # noqa: E731
    L = [
        "# 71716 EDA (손글씨풀이 라벨링)",
        "",
        f"- 읽은 zip: {', '.join(z.name for z in zips) or '없음'}",
        f"- 풀이 레코드 {n_rec}건 · 읽기 실패 {n_bad} · 풀이/라벨 없음 {n_skip}",
        f"- 풀이 길이(원문 LaTeX) 중앙값 {med(raw_len)}자 → 평문화 후 {med(txt_len)}자",
        "",
        "## AI Hub 분할 × 학년",
        "",
        "| 분할 | 학년 | 풀이 수 |",
        "|---|---|---|",
    ]
    for (sp, g), n in sorted(by_split_grade.items()):
        L.append(f"| {sp or '-'} | {GRADE_NAMES.get(g, g)} | {n} |")
    L += ["", "## 라벨 분포", ""]
    names = {
        "is_correct": "정답 여부 (1=정답)",
        "has_required_error": "필수 과정 실수 있음 (1=있음)",
        "required_errors": "필수 과정 실수 개수",
        "calc_accuracy": "계산 정확도 (0 없음/0.5 과정 생략/1 실수)",
        "difficulty": "풀이 난이도",
    }
    for k, cnt in labels.items():
        L.append(f"- **{names[k]}**: {_dist(cnt)}")
    L += ["", "## 학년별 정답 비율", ""]
    for g, cnt in sorted(by_grade_correct.items()):
        L.append(
            f"- {GRADE_NAMES.get(g, g)}: 정답 {cnt[1]} / 오답 {cnt[0]} "
            f"(정답 {cnt[1] / max(sum(cnt.values()), 1):.0%})"
        )
    L += [
        "",
        "## 점검",
        "",
        f"- 파일명 _O/_X 와 explanation_correct 일치: "
        f"{'모두 일치' if all((o == 'O') == bool(c) for (o, c) in ox_check) else '불일치 있음 ' + str(dict(ox_check))}",  # noqa: E501
    ]
    if "Training" in groups and "Validation" in groups:
        gt, gv = groups["Training"], groups["Validation"]
        qt, qv = questions["Training"], questions["Validation"]
        L += [
            f"- 문항 id 겹침 (Training∩Validation): {len(qt & qv)} / {len(qv)}",
            f"- 그룹 id 겹침 (Training∩Validation): {len(gt & gv)} / {len(gv)} "
            "→ 겹치면 숫자만 바꾼 쌍둥이 문항이 학습·평가에 섞인다. "
            "prepare.py는 그룹 단위로 다시 나눈다.",
        ]
    L += ["", "## 예시 (원문 → 평문화)", ""]
    for r in samples:
        L += [
            f"- `{r['question_id']}` {GRADE_NAMES.get(r['grade'], r['grade'])} · "
            f"정답 {r['is_correct']} · "
            f"필수실수 {r['required_errors']} · 계산 {r['calc_accuracy']}",
            f"  - 문제: {latex_to_text(r['question'])[:120]}",
            f"  - 정답: {latex_to_text(r['reference_answer'])[:60]}",
            f"  - 풀이 원문: `{r['solution'][:120]}`",
            f"  - 풀이 평문: {latex_to_text(r['solution'])[:120]}",
        ]
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[:60]))
    print(f"\n전체 결과: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else RAW_DIR))
