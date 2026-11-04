"""평가자 표시지(xlsx) 2개 → 판정 평가 자료 cases.jsonl (#199).

기준표 요소(코드·이름·설명·점수·goodThought·judgeVerified)는 데모 미션 시드
(`backend/learning-service/db/seed/demo_missions.sql`)에서 읽어 서비스와 같게 맞춘다.
FINAL_ANSWER는 규칙 판정이라 LLM 판정 평가에서 뺀다.

실행 (저장소 루트):
  uv run --with openpyxl python evaluation/datasets/judgment/build_cases.py \
    --r1 <평가자1.xlsx> --r2 <평가자2.xlsx> \
    --out evaluation/datasets/judgment/cases.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SEED = ROOT / "backend" / "learning-service" / "db" / "seed" / "demo_missions.sql"

# 표시지 답안 번호 앞부분 → 데모 미션 번호 (초5 사고 유형별 1개)
PREFIX_MISSION = {"ana": 11, "eva": 12, "cre": 13, "sol": 14, "ref": 15}
GRADE = 5
MARK = {"O": True, "X": False}
EXCLUDED_ELEMENTS = {"FINAL_ANSWER"}  # 정답 키 규칙 판정 (LLM 판정 아님)


def _uuid(prefix: str, n: int) -> str:
    return f"{prefix}000000-0000-4000-8000-{n:012d}"


def load_missions(seed: Path) -> dict[int, dict]:
    sql = seed.read_text(encoding="utf-8")
    missions = {}
    for n in PREFIX_MISSION.values():
        code = re.search(rf"\('{_uuid('d1', n)}', '([A-Z0-9-]+)'", sql)
        version = re.search(
            rf"\('{_uuid('d2', n)}', '{_uuid('d1', n)}', (\d+), '[^']*', '[^']*', \d+, \d+, "
            r"'[A-Z]+', [^,]+, '([A-Z_]+)'",
            sql,
        )
        if not code or not version:
            raise ValueError(f"시드에서 미션 {n} 정보를 못 찾음")
        rubric_id = _uuid("d3", n)
        elements = []
        for m in re.finditer(
            rf"\('d4[0-9a-f-]+', '{rubric_id}', '([A-Za-z0-9_]+)', '([^']*)', '([^']*)', (\d+), "
            r"[^,]+, (true|false), (true|false), (\d+)\)",
            sql,
        ):
            eid, label, desc, points, good, verified, _ = m.groups()
            if eid in EXCLUDED_ELEMENTS:
                continue
            element = {
                "elementId": eid,
                "label": label,
                "description": desc,
                "points": int(points),
                "judgeVerified": verified == "true",
            }
            if good == "true":
                element["goodThought"] = True
            elements.append(element)
        if not elements:
            raise ValueError(f"시드에서 미션 {n} 기준표 요소를 못 찾음")
        missions[n] = {
            "missionId": code.group(1),
            "missionVersion": int(version.group(1)),
            "rubricVersion": f"{rubric_id}@1",
            "inputType": version.group(2),
            "elements": elements,
        }
    return missions


def read_sheet(path: Path, element_ids: dict[int, list[str]]) -> dict[str, dict]:
    """caseId → {answerText, marks{elementId: bool}}. 빈칸·O/X 외 값은 거부."""
    from openpyxl import load_workbook

    out = {}
    for ws in load_workbook(path, data_only=True).worksheets[1:]:  # 0번 탭 = 안내
        for no, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
            if row[0] is None and row[1] is None:
                continue
            case_id, answer = str(row[0]).strip(), str(row[1] or "").strip()
            n = PREFIX_MISSION.get(case_id.split("-")[0])
            if n is None or not answer:
                raise ValueError(f"{path.name} {ws.title} {no}행: 번호·답안 확인 ({case_id})")
            ids = element_ids[n]
            marks = {}
            for eid, value in zip(ids, row[2 : 2 + len(ids)], strict=True):
                v = str(value or "").strip().upper()
                if v not in MARK:
                    raise ValueError(
                        f"{path.name} {ws.title} {case_id} {eid}: O/X 아님 ({value!r})"
                    )
                marks[eid] = MARK[v]
            out[case_id] = {"answerText": answer, "marks": marks, "mission": n}
    return out


def build(r1: Path, r2: Path, seed: Path = SEED) -> list[dict]:
    missions = load_missions(seed)
    ids = {n: [e["elementId"] for e in m["elements"]] for n, m in missions.items()}
    a, b = read_sheet(r1, ids), read_sheet(r2, ids)
    if a.keys() != b.keys():
        raise ValueError(f"두 표시지의 답안 번호가 다름: {sorted(a.keys() ^ b.keys())}")
    cases = []
    for case_id in sorted(a, key=lambda k: (a[k]["mission"], k)):
        if a[case_id]["answerText"] != b[case_id]["answerText"]:
            raise ValueError(f"{case_id}: 두 표시지의 답안 원문이 다름")
        m = missions[a[case_id]["mission"]]
        cases.append(
            {
                "caseId": case_id,
                "missionId": m["missionId"],
                "rubricVersion": m["rubricVersion"],
                "inputType": m["inputType"],
                "grade": GRADE,
                "answerText": a[case_id]["answerText"],
                "rubric": {"elements": m["elements"]},
                "raters": {"r1": a[case_id]["marks"], "r2": b[case_id]["marks"]},
            }
        )
    return cases


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--r1", type=Path, required=True, help="평가자 1 표시지 xlsx")
    ap.add_argument("--r2", type=Path, required=True, help="평가자 2 표시지 xlsx")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    cases = build(args.r1, args.r2)
    args.out.write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8"
    )
    same = sum(
        c["raters"]["r1"][e] == c["raters"]["r2"][e] for c in cases for e in c["raters"]["r1"]
    )
    total = sum(len(c["raters"]["r1"]) for c in cases)
    print(f"{args.out}: 사례 {len(cases)}개, 평가자끼리 요소 일치 {same}/{total}")


if __name__ == "__main__":
    main()
