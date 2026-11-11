"""지식 관계 확인 파일(#464 계약 C4) 읽기·쓰기·검증·비교·집계 (#468).

표준 라이브러리만 쓴다(CI ci-contracts는 PyYAML·jsonschema만 설치).

    python scripts/knowledge/review_relations.py validate FILE [--records R] [--final]
    python scripts/knowledge/review_relations.py compare FIRST CROSS
    python scripts/knowledge/review_relations.py stats FILE [--records R]
    python scripts/knowledge/review_relations.py coverage FILE [--records R] [--semesters 3-1,3-2,4-1,4-2]

확인 절차(docs/report/learning.md 29절): 후보 CSV(relation_candidates.py) → 담당자 1차 파일과 팀원 교차
파일을 따로 채움 → compare로 판단이 다른 행을 찾아 합의 → 1차 파일을 고쳐 차이 0 → validate --final → #466 적재.

evidence(C4 보충): 부분을 " | "로 잇는다. "문장: "·"해설: "로 시작하는 부분은 그 성취기준 문장·해설을
글자 그대로 옮긴 인용이라 validate가 부분 문자열인지 검사한다.
"""

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORDS = ROOT / "scripts/knowledge/samples/curriculum.sample.jsonl"
COLUMNS = ["relationType", "standardCode", "standardStatement", "target", "targetText", "evidence",
           "similarity", "candidateSource", "decision", "modifiedTarget", "reason", "reviewer",
           "reviewedAt", "datasetVersion"]
RELATION_TYPES = ("FITS", "PREREQUISITE", "COVERS")
THINKING_TYPES = ("ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT")
SOURCES = ("LLM", "EMBEDDING", "MANUAL")
DECISIONS = ("", "ACCEPT", "REJECT", "MODIFY")
ACCEPTED = ("ACCEPT", "MODIFY")
DEFAULT_SEMESTERS = ("3-1", "3-2", "4-1", "4-2")  # 1차 범위(초3·초4)
SAMPLE_REVIEWER = "SAMPLE"
SEPARATOR = " | "
STANDARD_CODE = re.compile(r"^[0-9][가-힣]+[0-9]{2}-[0-9]{2}$")
CONTENT_ID = re.compile(r":[KPV]:[0-9a-f]{8}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VERSION = re.compile(r"^kn-\d{8}-\d{2}$")
SIMILARITY = re.compile(r"^$|^(0(\.[0-9]+)?|1(\.0+)?)$")
QUOTE = re.compile(r"^(문장|해설): (.+)$", re.DOTALL)


@dataclass(frozen=True)
class Records:
    standards: dict  # 코드 → standard 레코드
    contents: dict  # id → content 레코드
    thinking_types: dict  # 유형 코드 → thinking_type 레코드

    def type_name(self, code):
        record = self.thinking_types.get(code)
        return record["name"] if record else code


def load_records(path=DEFAULT_RECORDS):
    """C1 JSONL에서 관계에 쓰는 세 종류만 모은다."""
    standards, contents, thinking_types = {}, {}, {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record["kind"] == "standard":
            standards[record["code"]] = record
        elif record["kind"] == "content":
            contents[record["id"]] = record
        elif record["kind"] == "thinking_type":
            thinking_types[record["type"]] = record
    return Records(standards, contents, thinking_types)


def semester_key(semester):
    grade, term = semester.split("-")
    return int(grade), int(term)


def is_earlier(prerequisite, standard):
    """선수 성취기준의 마지막 학기가 이 성취기준의 첫 학기보다 앞서면 참. 학기 정보가 없으면 거짓."""
    if not prerequisite["semesters"] or not standard["semesters"]:
        return False
    return max(map(semester_key, prerequisite["semesters"])) < min(map(semester_key, standard["semesters"]))


def target_text(relation_type, target, records):
    """확인하는 사람이 보는 대상 글(C4 targetText)."""
    if relation_type == "FITS":
        return records.type_name(target)
    if relation_type == "PREREQUISITE":
        return records.standards[target]["statement"]
    return records.contents[target]["text"]


def effective_target(row):
    return row["modifiedTarget"] if row["decision"] == "MODIFY" else row["target"]


def read_review_csv(path):
    """머리행이 C4 순서와 다르면 ValueError. 엑셀이 붙이는 BOM은 허용."""
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"{path}: 머리행이 C4 칸 순서와 다름 {reader.fieldnames}")
        return [{key: value or "" for key, value in row.items()} for row in reader]


def write_review_csv(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _check_evidence(row, standard):
    errors = []
    for part in row["evidence"].split(SEPARATOR):
        quote = QUOTE.match(part)
        if not quote:
            continue
        source = standard["statement"] if quote[1] == "문장" else standard["explanation"] or ""
        if quote[2] not in source:
            errors.append(f"evidence 인용이 성취기준 {quote[1]}에 없음: {quote[2]}")
    return errors


def _check_target(relation_type, target, standard, records):
    if relation_type == "FITS":
        return [] if target in THINKING_TYPES else [f"FITS 대상은 유형 코드: {target}"]
    if relation_type == "PREREQUISITE":
        if not STANDARD_CODE.match(target) or target not in records.standards:
            return [f"선수 성취기준이 레코드에 없음: {target}"]
        if target == standard["code"]:
            return ["선수가 자기 자신"]
        if records.standards[target]["subject"] != standard["subject"]:
            return [f"선수가 다른 교과: {target}"]
        return []
    if not CONTENT_ID.search(target) or target not in records.contents:
        return [f"내용 요소가 레코드에 없음: {target}"]
    content = records.contents[target]
    if (content["subject"], content["noticeGradeBand"]) != (standard["subject"], standard["noticeGradeBand"]):
        return [f"내용 요소가 다른 교과·학년군: {target}"]
    return []


def _check_row(row, records, final):
    errors = []
    relation_type, decision = row["relationType"], row["decision"]
    if relation_type not in RELATION_TYPES:
        return [f"relationType 값: {relation_type}"]
    standard = records.standards.get(row["standardCode"])
    if standard is None:
        return [f"성취기준이 레코드에 없음: {row['standardCode']}"]
    if row["standardStatement"] != standard["statement"]:
        errors.append("standardStatement가 레코드 문장과 다름")
    if not VERSION.match(row["datasetVersion"]):
        errors.append(f"datasetVersion 모양: {row['datasetVersion']}")
    if row["candidateSource"] not in SOURCES:
        errors.append(f"candidateSource 값: {row['candidateSource']}")
    if not row["evidence"].strip():
        errors.append("evidence 빈 칸")
    errors += _check_evidence(row, standard)
    if not SIMILARITY.match(row["similarity"]):
        errors.append(f"similarity 모양: {row['similarity']}")
    if relation_type != "COVERS" and row["similarity"]:
        errors.append("similarity는 COVERS만")
    if decision not in DECISIONS:
        return errors + [f"decision 값: {decision}"]
    if decision == "":
        if row["modifiedTarget"] or row["reviewer"] or row["reviewedAt"]:
            errors.append("확인 전 행에 modifiedTarget·reviewer·reviewedAt이 있음")
        if final:
            errors.append("확인하지 않은 행")
    else:
        if not row["reviewer"].strip():
            errors.append("reviewer 빈 칸")
        if not DATE.match(row["reviewedAt"]):
            errors.append(f"reviewedAt은 YYYY-MM-DD: {row['reviewedAt']}")
        if final and row["reviewer"] == SAMPLE_REVIEWER:
            errors.append("샘플 확인자(SAMPLE)는 최종 파일에 쓸 수 없음")
    if decision in ("REJECT", "MODIFY") and not row["reason"].strip():
        errors.append(f"{decision}은 reason 필수")
    if decision == "MODIFY" and not row["modifiedTarget"]:
        errors.append("MODIFY는 modifiedTarget 필수")
    if decision != "MODIFY" and row["modifiedTarget"]:
        errors.append("modifiedTarget은 MODIFY만")
    targets = [row["target"]] + ([row["modifiedTarget"]] if decision == "MODIFY" and row["modifiedTarget"] else [])
    for target in targets:
        errors += _check_target(relation_type, target, standard, records)
    if not errors and row["targetText"] != target_text(relation_type, row["target"], records):
        errors.append("targetText가 대상 글과 다름")
    if (not errors and decision in ACCEPTED and relation_type == "PREREQUISITE"
            and not is_earlier(records.standards[effective_target(row)], standard)):
        errors.append(f"선수가 앞 학기가 아님: {effective_target(row)}")
    return errors


def validate(rows, records, final=False):
    """오류 목록(빈 목록이면 통과). 행 번호는 CSV 줄 번호(머리행 = 1)."""
    errors = []
    candidates, accepted = set(), set()
    for line, row in enumerate(rows, start=2):
        errors += [f"{line}행: {message}" for message in _check_row(row, records, final)]
        key = (row["relationType"], row["standardCode"], row["target"])
        if key in candidates:
            errors.append(f"{line}행: 같은 후보가 또 있음 {key}")
        candidates.add(key)
        if row["decision"] in ACCEPTED:
            key = (row["relationType"], row["standardCode"], effective_target(row))
            if key in accepted:
                errors.append(f"{line}행: 같은 관계를 두 번 수락 {key}")
            accepted.add(key)
    versions = {row["datasetVersion"] for row in rows}
    if len(versions) > 1:
        errors.append(f"판이 여러 개: {sorted(versions)}")
    return errors


def compare(first, cross):
    """1차·교차 파일에서 판단(decision·modifiedTarget)이 다른 행과 한쪽에만 있는 행."""
    def keyed(rows):
        return {(r["relationType"], r["standardCode"], r["target"]): r for r in rows}

    a, b = keyed(first), keyed(cross)
    differences = []
    for key in list(a) + [k for k in b if k not in a]:
        if key not in b:
            differences.append(f"{key}: 교차 파일에 없음")
        elif key not in a:
            differences.append(f"{key}: 1차 파일에 없음")
        elif (a[key]["decision"], a[key]["modifiedTarget"]) != (b[key]["decision"], b[key]["modifiedTarget"]):
            differences.append(
                f"{key}: 1차 {a[key]['decision'] or '미확인'} {a[key]['modifiedTarget']}".rstrip()
                + f" / 교차 {b[key]['decision'] or '미확인'} {b[key]['modifiedTarget']}".rstrip()
            )
    return differences


def _rate_row(label, counter):
    decided = counter["ACCEPT"] + counter["MODIFY"] + counter["REJECT"]
    accepted = counter["ACCEPT"] + counter["MODIFY"]
    rate = f"{accepted / decided:.0%}" if decided else "-"
    return f"| {label} | {decided} | {accepted} | {counter['MODIFY']} | {counter['REJECT']} | {counter['']} | {rate} |"


def _rate_table(title, groups):
    lines = [f"#### {title}", "", "| 묶음 | 확인 | 수락(수정 포함) | 수정 | 거절 | 미확인 | 수락률 |",
             "|---|---|---|---|---|---|---|"]
    lines += [_rate_row(label, counter) for label, counter in groups.items()]
    return lines + [""]


def stats(rows, records):
    """수락률(수락+수정 / 확인한 행) 관계 종류별·FITS 유형별·교과별 표와 거절 사유(마크다운)."""
    by_relation, by_type, by_subject = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    for row in rows:
        by_relation[row["relationType"]][row["decision"]] += 1
        if row["relationType"] == "FITS":
            by_type[records.type_name(row["target"])][row["decision"]] += 1
        subject = records.standards[row["standardCode"]]["subject"]
        by_subject[f"{subject} {row['relationType']}"][row["decision"]] += 1
    lines = _rate_table("관계 종류별", dict(sorted(by_relation.items())))
    lines += _rate_table("FITS 후보 유형별", dict(sorted(by_type.items())))
    lines += _rate_table("교과·관계 종류별", dict(sorted(by_subject.items())))
    lines += ["#### 거절·수정 사유", ""]
    reasons = [f"- {r['decision']} {r['relationType']} {r['standardCode']} → {r['target']}"
               + (f" ⇒ {r['modifiedTarget']}" if r["modifiedTarget"] else "") + f": {r['reason']}"
               for r in rows if r["decision"] in ("REJECT", "MODIFY")]
    return "\n".join(lines + (reasons or ["- 없음"])) + "\n"


def coverage(rows, records, semesters=DEFAULT_SEMESTERS):
    """학년·학기 × 유형마다 수락된 FITS 성취기준 수, 빈 칸 목록, 수락 COVERS가 없는 성취기준(마크다운)."""
    fits, covered = defaultdict(set), set()
    for row in rows:
        if row["decision"] not in ACCEPTED:
            continue
        if row["relationType"] == "FITS":
            fits[row["standardCode"]].add(effective_target(row))
        elif row["relationType"] == "COVERS":
            covered.add(row["standardCode"])
    names = [records.type_name(t) for t in THINKING_TYPES]
    lines = ["#### 학년·학기 × 유형 (수락된 맞는 생각 유형 성취기준 수)", "",
             "| 학기 | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    empty = []
    in_scope = [s for s in records.standards.values() if set(s["semesters"]) & set(semesters)]
    for semester in semesters:
        cells = []
        for thinking_type in THINKING_TYPES:
            codes = sorted(s["code"] for s in in_scope
                           if semester in s["semesters"] and thinking_type in fits[s["code"]])
            cells.append(str(len(codes)))
            if not codes:
                empty.append(f"- {semester} {records.type_name(thinking_type)}")
        lines.append(f"| {semester} | " + " | ".join(cells) + " |")
    lines += ["", "#### 빈 칸", ""] + (empty or ["- 없음"])
    missing = sorted(s["code"] for s in in_scope if s["code"] not in covered)
    lines += ["", "#### 수락된 내용 요소가 없는 성취기준", ""] + ([f"- {code}" for code in missing] or ["- 없음"])
    return "\n".join(lines) + "\n"


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):  # Windows 콘솔(cp949)에서 한글 출력
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "stats", "coverage"):
        command = commands.add_parser(name)
        command.add_argument("file", type=Path)
        command.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
        if name == "validate":
            command.add_argument("--final", action="store_true", help="미확인 행·샘플 확인자 거부(#466에 넘기기 전)")
        if name == "coverage":
            command.add_argument("--semesters", default=",".join(DEFAULT_SEMESTERS))
    command = commands.add_parser("compare")
    command.add_argument("first", type=Path)
    command.add_argument("cross", type=Path)
    args = parser.parse_args(argv)

    if args.command == "compare":
        differences = compare(read_review_csv(args.first), read_review_csv(args.cross))
        print("\n".join(differences) if differences else "차이 없음")
        return 1 if differences else 0
    rows, records = read_review_csv(args.file), load_records(args.records)
    if args.command == "validate":
        errors = validate(rows, records, final=args.final)
        print("\n".join(errors) if errors else f"통과: {len(rows)}행")
        return 1 if errors else 0
    if args.command == "stats":
        print(stats(rows, records), end="")
        return 0
    print(coverage(rows, records, tuple(args.semesters.split(","))), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
