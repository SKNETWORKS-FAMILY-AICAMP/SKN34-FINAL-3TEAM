"""교육과정 고시 교과 별책(HWP5) → 지식 RAG 추출 레코드 JSONL (#465, 계약 C1).

두 하위 명령이 있다. 원문은 저장소에 넣지 않으므로 경로를 인자로 받는다. 원문은 신뢰하지 않는 입력이라
별도 폴더에 복사해 두고 `python -I`로 실행한다(이 파일 폴더만 import 경로에 더한다).

    python -I scripts/knowledge/extract_curriculum.py semester-map \
        --seoul-14 서울_1~4학년_평가계획_도움자료.xlsx --seoul-56 서울_5~6학년_단원_연결표.xlsx \
        --gyeonggi 정리본_성취기준_학년학기_연결표.xlsx --out scripts/knowledge/semester_map.csv

    python -I scripts/knowledge/extract_curriculum.py extract 별책5.hwp 별책6.hwp 별책7.hwp 별책8.hwp 별책9.hwp \
        --semester-map scripts/knowledge/semester_map.csv --out scripts/knowledge/data/curriculum-v1.jsonl

- 대상: 국어(별책 5)·도덕(6)·사회(7)·수학(8)·과학(9)의 공통 교육과정 중 초3·초4·초5·초6 부분
  (고시 원문은 3~4학년군·5~6학년군으로 묶여 있어 `noticeGradeBand`에 원문 학년군을 둔다)
- 고시 원문 단위: 성취기준(해설은 원문에 있는 것만), 영역(내용 체계·적용 시 고려 사항), 내용 요소,
  교과 지침(교수⋅학습 및 평가 한 장), 생각 유형(`thinking_types.md`)
- 학기 대응 자료(교육청)는 성취기준 코드↔학년·학기만 옮긴다. 평가 요소·성취수준·수업 방법 문장은 읽지 않는다
- 표준 라이브러리만 쓴다
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # python -I는 스크립트 폴더를 import 경로에 넣지 않는다
    sys.path.insert(0, str(HERE))

import hwp5  # noqa: E402

ROOT = HERE.parents[1]
SEED = ROOT / "backend/learning-service/db/seed/achievement_standards.sql"
THINKING_TYPES = HERE / "thinking_types.md"
DATASET = "curriculum-v1"
NOTICE = "교육부 고시 제2022-33호"
NOTICE_DATE = "2022-12-22"
SUBJECTS = {5: "국어", 6: "도덕", 7: "사회", 8: "수학", 9: "과학"}
SUBJECT_ORDER = ["국어", "도덕", "사회", "수학", "과학"]
BANDS = {"3~4": "초3~4", "5~6": "초5~6"}
BAND_GRADES = {"초3~4": [3, 4], "초5~6": [5, 6]}
SEMESTERS = ["3-1", "3-2", "4-1", "4-2", "5-1", "5-2", "6-1", "6-2"]
CODE = r"\d[가-힣]+\d{2}\s*[-–—‐]\s*\d{2}"
CODE_RE = re.compile(CODE)
CODE_LINE = re.compile(rf"^\[({CODE})\]\s*(.*)$", re.S)
CODE_RANGE = rf"\[{CODE}(?:\s*[~∼]\s*\d{{2}})?\]"
LEADING_CODES = re.compile(rf"^((?:{CODE_RANGE}(?:\s*(?:,|와|과|및|~|∼)\s*)?)+)")
CATEGORY = {"지식⋅이해": "knowledge", "과정⋅기능": "process", "가치⋅태도": "values"}
CATEGORY_LETTER = {"knowledge": "K", "process": "P", "values": "V"}
SCOPE_BOTH = {"국어", "수학", "도덕"}

SEOUL_14 = "서울특별시교육청 「2022 개정 교육과정 1~4학년 평가계획 도움자료」(2025-02-04)"
SEOUL_56 = "서울특별시교육청 「2022 개정 교육과정 5~6학년 단원(키워드) 연결표」(2026-01-20)"
GYEONGGI_34 = "경기도교육청 「2025학년도 초등학교 3~4학년 2학기 수업-평가 계획 예시 자료」"
GYEONGGI_56 = "경기도교육청 「2026학년도 초등학교 5~6학년 1~2학기 수업-평가 계획 예시 자료」"


# --- 공통 -----------------------------------------------------------------------------------------


def clean(text: str) -> str:
    """NFC, 줄바꿈·연속 공백을 한 칸으로. 기호·단위는 바꾸지 않는다."""
    text = unicodedata.normalize("NFC", text).replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def code_of(raw: str) -> str:
    """원문 코드(줄표·공백 섞임)를 성취기준 표 모양(붙임표)으로."""
    return re.sub(r"\s*[-–—‐]\s*", "-", raw.strip())


def loose(text: str) -> str:
    """공백·기호 차이만 무시하는 비교용 글(성취기준 표 대조)."""
    text = unicodedata.normalize("NFKC", text)
    for chars, to in (("ㆍ·⋅•∙", "⋅"), ("‘’`´", "'"), ("“”", '"'), ("–—‐−", "-"), ("∼〜", "~")):
        text = re.sub(f"[{re.escape(chars)}]", to, text)
    return re.sub(r"\s+", "", text)


def expand_codes(text: str) -> list[str]:
    """'[4과09-01∼02]'처럼 범위로 쓴 코드도 펼친다."""
    codes = []
    for match in re.finditer(rf"\[({CODE})(?:\s*[~∼]\s*(\d{{2}}))?\]", text):
        code = code_of(match[1])
        codes.append(code)
        if match[2]:
            head, last = code.rsplit("-", 1)
            codes.extend(f"{head}-{n:02d}" for n in range(int(last) + 1, int(match[2]) + 1))
    return codes


def content_hash(text: str) -> str:
    return hashlib.sha256(unicodedata.normalize("NFC", text).encode("utf-8")).hexdigest()[:8]


def load_seed(path: Path = SEED) -> dict[str, dict]:
    """성취기준 표 시드(코드 → 교과·학년군·영역·문장)."""
    pattern = re.compile(r"\('([^']+)', '([^']*)', '([^']*)', '([^']*)', '((?:[^']|'')*)', \d+, ")
    seed = {}
    for code, subject, band, area, statement in pattern.findall(path.read_text(encoding="utf-8")):
        seed[code] = {"subject": subject, "band": band, "area": area, "statement": statement.replace("''", "'")}
    return seed


def target_seed(seed: dict[str, dict]) -> dict[str, dict]:
    return {code: row for code, row in seed.items()
            if row["subject"] in SUBJECTS.values() and row["band"] in BAND_GRADES}


# --- 학기 대응(xlsx) ------------------------------------------------------------------------------

XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
           "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
           "p": "http://schemas.openxmlformats.org/package/2006/relationships"}


def read_xlsx(path: Path) -> OrderedDict[str, list[dict[str, str]]]:
    """시트 이름 → 행 목록(열 글자 → 값). 표준 라이브러리 zipfile·ElementTree만 쓴다."""
    def text_of(node) -> str:
        return "".join(t.text or "" for t in node.iter(f"{{{XLSX_NS['m']}}}t"))

    sheets: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [text_of(item) for item in root.findall("m:si", XLSX_NS)]
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {rel.get("Id"): rel.get("Target") for rel in rels.findall("p:Relationship", XLSX_NS)}
        for sheet in workbook.find("m:sheets", XLSX_NS).findall("m:sheet", XLSX_NS):
            target = targets[sheet.get(f"{{{XLSX_NS['r']}}}id")].lstrip("/")
            target = target if target.startswith("xl/") else f"xl/{target}"
            rows = []
            for row in ElementTree.fromstring(archive.read(target)).iter(f"{{{XLSX_NS['m']}}}row"):
                cells = {}
                for cell in row.findall("m:c", XLSX_NS):
                    value = cell.find("m:v", XLSX_NS)
                    if cell.get("t") == "s" and value is not None:
                        text = shared[int(value.text)]
                    elif cell.get("t") == "inlineStr":
                        text = text_of(cell)
                    else:
                        text = value.text if value is not None else ""
                    text = (text or "").strip()
                    if text:
                        cells[re.match(r"[A-Z]+", cell.get("r"))[0]] = text
                rows.append(cells)
            sheets[sheet.get("name")] = rows
    return sheets


def excel_header_semester(value: str) -> str | None:
    """머리글 칸 값 → 학기 글. 엑셀이 `3-1`을 날짜(2025-03-01, 일련번호 45717)로 바꾼 칸도 푼다."""
    value = value.strip()
    if re.fullmatch(r"[1-6]-[1-4]", value):
        return value
    if re.fullmatch(r"\d{5}", value):
        serial = int(value)
        import datetime
        day = datetime.date(1899, 12, 30) + datetime.timedelta(days=serial)
        return f"{day.month}-{day.day}"
    return None


def _row_code(cells: dict[str, str], columns: str) -> str | None:
    for column in columns:
        match = CODE_RE.search(cells.get(column, ""))
        if match:
            return code_of(match[0])
    return None


@dataclass
class SemesterSource:
    """자료 하나에서 읽은 코드 → 학기. focus는 중점(●) 학기(서울 자료만)."""
    label: str
    semesters: dict[str, list[str]] = field(default_factory=dict)
    focus: dict[str, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    from_sheet: set[str] = field(default_factory=set)  # 연결표에 없어 교과별 시트에서 옮긴 코드


def read_seoul_14(path: Path) -> SemesterSource:
    """서울 1~4학년 도움자료: `3-4성취기준 단원 연결표` 시트(E~H 칸)에서 학기, 교과별 시트로 머리글 확인."""
    sheets = read_xlsx(path)
    name = next(n for n in sheets if n.startswith("3-4") and "연결표" in n)
    rows = sheets[name]
    header_row = next(r for r in rows if sum(excel_header_semester(v) is not None for v in r.values()) >= 4)
    header = {column: excel_header_semester(value) for column, value in header_row.items()}
    source = SemesterSource(f"{SEOUL_14} 「{name}」 시트")
    columns = [c for c in "EFGH" if c in header]
    raw: dict[str, dict[str, str]] = {}
    for cells in rows:
        code = _row_code(cells, "C")
        if code:
            raw[code] = {column: cells.get(column, "") for column in columns}
    # 교과별 시트(국어·수학·도덕·사회·과학)의 `학년-학기` 칸으로 머리글을 맞춘다(평가 문장은 읽지 않음)
    evaluated: dict[str, set[str]] = {}
    for sheet_name in ("국어", "수학", "도덕", "사회", "과학"):
        for cells in sheets.get(sheet_name, []):
            semester = cells.get("A", "").strip()
            code = _row_code(cells, "BC")
            if code and re.fullmatch(r"[34]-[12]", semester):
                evaluated.setdefault(code, set()).add(semester)
    mapping = {}
    for column in columns:
        votes = Counter()
        for code, marks in raw.items():
            if "●" in marks[column]:
                votes.update(evaluated.get(code, set()))
        mapping[column] = votes.most_common(1)[0][0] if votes else header[column]
    for column in columns:
        if mapping[column] != header[column]:
            source.notes.append(f"머리글 {column}열 '{header[column]}' → 실제 '{mapping[column]}'"
                                f"(교과별 시트 학년-학기와 중점 표시 대조)")
    for code, marks in raw.items():
        source.semesters[code] = [mapping[c] for c in columns if marks[c].strip()]
        source.focus[code] = [mapping[c] for c in columns if "●" in marks[c]]
    for code in sorted(set(evaluated) - set(raw)):
        if code.startswith("4"):
            source.semesters[code] = sorted(evaluated[code])
            source.from_sheet.add(code)
            semesters = ", ".join(sorted(evaluated[code]))
            source.notes.append(f"{code}: 연결표에 행이 없어 교과별 시트의 학년-학기({semesters})로 채움")
    return source


def read_seoul_56(path: Path) -> SemesterSource:
    """서울 5~6학년 단원(키워드) 연결표: 교과 시트 D~G 칸(5-1·5-2·6-1·6-2)."""
    sheets = read_xlsx(path)
    source = SemesterSource(SEOUL_56)
    for sheet_name in ("국어", "사회", "도덕", "수학", "과학"):
        rows = sheets[sheet_name]
        header_row = next(r for r in rows if sum(excel_header_semester(v) is not None for v in r.values()) >= 4)
        header = {c: excel_header_semester(v) for c, v in header_row.items() if excel_header_semester(v)}
        for cells in rows:
            code = _row_code(cells, "B")
            if code:
                source.semesters[code] = [header[c] for c in sorted(header) if cells.get(c, "").strip()]
                source.focus[code] = [header[c] for c in sorted(header) if "●" in cells.get(c, "")]
    return source


def read_gyeonggi(path: Path) -> SemesterSource:
    """팀 정리본(경기도교육청 두 자료의 국어·수학 단원 배치를 옮긴 표): `3·4학년 연결표`·`5·6학년 연결표` E~H 칸."""
    sheets = read_xlsx(path)
    source = SemesterSource(f"{GYEONGGI_34}·{GYEONGGI_56} 국어·수학(팀 정리본 「정리본_성취기준_학년학기_연결표」)")
    for sheet_name, rows in sheets.items():
        if "연결표" not in sheet_name:
            continue
        header = {c: v for c, v in rows[0].items() if re.fullmatch(r"[3-6]-[12]", v)}
        for cells in rows[1:]:
            code = _row_code(cells, "C")
            if code:
                source.semesters[code] = [header[c] for c in sorted(header) if cells.get(c, "").strip()]
    return source


SEMESTER_COLUMNS = ["code", "subject", "noticeGradeBand", "semesters", "seoul", "gyeonggi", "seoulFocus", "basis"]


BASIS_SAME = "경기·서울 같음"
BASIS_DIFF = "경기·서울 다름(경기 기준안, 사람 확인)"
BASIS_SEOUL = "서울(경기 자료는 PDF라 표준 라이브러리로 읽지 않음)"
BASIS_MORAL = "서울(경기 자료에 도덕 없음)"
BASIS_SHEET = "서울 교과별 시트(연결표에 행이 없음)"


def build_semester_map(seed: dict[str, dict], seoul: list[SemesterSource], gyeonggi: SemesterSource | None):
    """코드 → 학기 표와 자료끼리 다른 코드 목록.

    출처.md 기준안: 국어·수학은 경기 자료(팀 정리본으로 읽음), 사회·과학·도덕은 서울 자료. 학기는 단원이 있는
    학기 모두(서울 표시로는 중점●·지속○ 모두). 두 자료가 다르면 `basis`에 적고 사람이 정한다.
    """
    rows, differences = [], []
    for code, info in sorted(target_seed(seed).items(), key=lambda item: standard_key(item[0], item[1]["subject"])):
        seoul_source = next((s for s in seoul if code in s.semesters), None)
        seoul_semesters = seoul_source.semesters[code] if seoul_source else None
        focus = seoul_source.focus.get(code, []) if seoul_source else []
        gyeonggi_semesters = gyeonggi.semesters.get(code) if gyeonggi else None
        band_semesters = [s for s in SEMESTERS if int(s[0]) in BAND_GRADES[info["band"]]]
        if info["subject"] in ("국어", "수학") and gyeonggi_semesters is not None:
            chosen = gyeonggi_semesters
            basis = BASIS_SAME if seoul_semesters in (None, gyeonggi_semesters) else BASIS_DIFF
            if basis == BASIS_DIFF:
                differences.append({"code": code, "gyeonggi": gyeonggi_semesters, "seoul": seoul_semesters})
        elif seoul_semesters is not None:
            chosen = seoul_semesters
            basis = BASIS_SHEET if code in seoul_source.from_sheet else (
                BASIS_MORAL if info["subject"] == "도덕" else BASIS_SEOUL)
        else:
            chosen, basis = [], "자료 없음"
        chosen = [s for s in chosen if s in band_semesters]
        rows.append({"code": code, "subject": info["subject"], "noticeGradeBand": info["band"],
                     "semesters": ";".join(chosen), "seoul": ";".join(seoul_semesters or []),
                     "gyeonggi": ";".join(gyeonggi_semesters or []), "seoulFocus": ";".join(focus), "basis": basis})
    return rows, differences


def standard_key(code: str, subject: str):
    """교과 순서(국어·도덕·사회·수학·과학) → 코드 순."""
    return SUBJECT_ORDER.index(subject), code


def write_semester_map(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SEMESTER_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_semester_map(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8", newline="") as file:
        return {row["code"]: row for row in csv.DictReader(file)}


# --- 고시 별책 읽기 ---------------------------------------------------------------------------------


@dataclass
class Line:
    """본문 한 줄(문단). page는 인쇄 쪽(어림)."""
    text: str
    page: int | None


def cell_lines(cell: hwp5.Cell) -> list[str]:
    out = []
    for block in cell.blocks:
        out.extend((block.text if isinstance(block, hwp5.Paragraph) else hwp5.block_text(block)).split("\n"))
    return [unicodedata.normalize("NFC", line).strip() for line in out if line.strip()]


def label_of(lines: list[str]) -> str:
    """칸 제목(여러 줄)을 한 줄로: '내용', '확인⋅추론⋅', '평가' → '내용 확인⋅추론⋅평가'."""
    text = " ".join(lines)
    text = re.sub(r"\s*⋅\s*", "⋅", text)
    text = re.sub(r"-\s+", "-", text)
    return clean(text)


def split_items(lines: list[str]) -> list[str]:
    """`⋅` 글머리 항목으로 나눈다. 글머리 없는 줄은 앞 항목에 잇는다(괄호로 시작하면 붙여서)."""
    items: list[str] = []
    for line in lines:
        parts = re.split(r"(?:^|\s+)[⋅•]\s*", line)
        head, rest = parts[0], parts[1:]
        if head.strip():
            if items:
                joiner = "" if head.lstrip().startswith("(") else " "
                items[-1] = clean(items[-1] + joiner + head)
            else:
                items.append(clean(head))
        items.extend(clean(part) for part in rest if part.strip())
    return items


def band_of_header(text: str) -> str | None:
    match = re.fullmatch(r"(?:초등학교\s*)?(\d)\s*[~∼\-]\s*(\d)\s*학년(?:군)?", clean(text))
    if match and f"{match[1]}~{match[2]}" in BANDS:
        return BANDS[f"{match[1]}~{match[2]}"]
    return None


@dataclass
class ContentArea:
    """내용 체계 표 한 영역. items: 학년군 → 범주 → [(묶음, 항목)]."""
    name: str
    core_ideas: list[str] = field(default_factory=list)
    items: dict[str, dict[str, list[tuple[str | None, str]]]] = field(default_factory=dict)
    pages: set[int] = field(default_factory=set)


def parse_content_table(table: hwp5.Table, area: ContentArea) -> None:
    grid = table.grid()
    band_columns: dict[int, str] = {}
    grade_columns: set[int] = set()  # 학년(군) 칸 전부(1~2학년·중학교 1~3학년 포함). 그 왼쪽이 범주·묶음 칸
    for row in grid:
        for column, cell in enumerate(row):
            if cell is not None and cell.col == column and cell.col_span == 1:
                label = label_of(cell_lines(cell))
                if re.fullmatch(r"(?:초등학교\s*)?\d\s*[~∼\-]\s*\d\s*학년(?:군)?|중학교", label):
                    grade_columns.add(column)
                band = band_of_header(label)
                if band:
                    band_columns[column] = band
    first_band = min(grade_columns) if band_columns else None
    rows: list[tuple[int, str, str | None]] = []  # 행 번호, 범주, 묶음
    category = None
    for index, row in enumerate(grid):
        head = row[0]
        if head is None:
            continue
        label = re.sub(r"\s+", "", label_of(cell_lines(head)))
        if label == "핵심아이디어":
            value = next((c for c in row[1:] if c is not None and c is not head), None)
            if value is not None:
                area.core_ideas.extend(i for i in split_items(cell_lines(value)) if i not in area.core_ideas)
            category = None
            continue
        category = CATEGORY.get(label, category if label not in ("범주", "구분범주") else None)
        if category is None or first_band is None:
            continue
        group = None
        if head.col_span < first_band:
            group_cell = row[head.col_span]
            if group_cell is not None and group_cell is not head:
                group = label_of(cell_lines(group_cell)) or None
        rows.append((index, category, group))
    for column, band in band_columns.items():
        seen: set[int] = set()
        for index, category, _ in rows:
            cell = grid[index][column]
            if cell is None or cell is grid[index][0] or id(cell) in seen:
                continue
            seen.add(id(cell))
            # 여러 묶음 행에 걸친 칸은 묶음 이름을 ' / '로 잇는다(한 칸이 두 묶음에 함께 속함)
            spanned = [g for i, c, g in rows if cell.row <= i < cell.row + cell.row_span and c == category]
            groups = list(dict.fromkeys(g for g in spanned if g))
            group = " / ".join(groups) or None
            bucket = area.items.setdefault(band, {}).setdefault(category, [])
            for item in split_items(cell_lines(cell)):
                if re.fullmatch(r"[-–−]", item):  # 원문 '-'는 '해당 없음' 표시
                    continue
                if all(text != item for _, text in bucket):
                    bucket.append((group, item))
    if table.page:
        area.pages.update(range(table.page, (table.page_end or table.page) + 1))


@dataclass
class Unit:
    """성취기준 단원(국어·수학·도덕은 내용 체계 영역과 같은 이름)."""
    name: str
    band: str  # 초3~4·초5~6·초등(도덕은 3~4·5~6학년군이 한 묶음)
    band_heading: str
    heading: str
    standards: list[tuple[str, str, str]] = field(default_factory=list)  # 코드, 문장, 원문 코드
    subtopics: dict[str, str] = field(default_factory=dict)
    activities: list[str] = field(default_factory=list)
    explanations: OrderedDict = field(default_factory=OrderedDict)  # 코드 → [문단]
    explanation_items: list[list[str]] = field(default_factory=list)  # 해설 항목마다 앞머리 코드
    explanation_paragraphs: int = 0  # (가) 절 문단 수(코드로 시작하지 않는 이어진 문단 포함)
    considerations: list[str] = field(default_factory=list)
    pages: set[int] = field(default_factory=set)
    explanation_pages: dict[str, set[int]] = field(default_factory=dict)
    consideration_pages: set[int] = field(default_factory=set)
    unknown: list[str] = field(default_factory=list)


@dataclass
class Notice:
    path: Path
    number: int
    subject: str
    doc: str
    areas: OrderedDict
    units: list[Unit]
    teaching: list[str]
    assessment: list[str]
    guide_pages: set[int]
    toc_check: list[tuple[str, int, int | None]]
    unknown: list[str]


def _is(text: str | None, *patterns: str) -> bool:
    if not text:
        return False
    compact = re.sub(r"\s+", "", text)
    return any(compact == re.sub(r"\s+", "", p) for p in patterns)


def _pages(block) -> set[int]:
    if block.page is None:
        return set()
    return set(range(block.page, (block.page_end or block.page) + 1))


def read_notice(path: Path) -> Notice:
    document = hwp5.read_hwp(path)
    blocks = document.blocks
    texts = [clean(b.text) if isinstance(b, hwp5.Paragraph) else None for b in blocks]
    title = next(t for t in texts if t and t.startswith("교육부 고시"))
    match = re.search(r"\[별책\s*(\d+)\]", title)
    if not match or int(match[1]) not in SUBJECTS:
        raise ValueError(f"대상 별책이 아님: {path.name} ({title})")
    number = int(match[1])
    subject = SUBJECTS[number]
    name = next(t for t in texts if t and t.endswith("교육과정") and not t.startswith("교육부"))
    doc = f"{NOTICE} [별책 {number}] {name}"

    def index_of(begin: int, pattern: str) -> int:
        return next(i for i in range(begin, len(blocks)) if _is(texts[i], pattern))

    start = index_of(0, "2. 내용 체계 및 성취기준")
    content = index_of(start, "가. 내용 체계")
    standards = index_of(content, "나. 성취기준")
    guide = index_of(standards, "3. 교수⋅학습 및 평가")
    # 공통 교육과정 교과는 다음 교과(역사·선택 과목) 제목·설계 개요·성격 앞에서 끝난다
    stops = ("1. 성격 및 목표", "교육과정 설계의 개요", "선택 중심 교육과정", "[선택 중심 교육과정]")
    end = next((i for i in range(guide + 1, len(blocks)) if _is(texts[i], *stops)), len(blocks))

    unknown: list[str] = []
    areas: OrderedDict[str, ContentArea] = OrderedDict()
    current: ContentArea | None = None
    for i in range(content + 1, standards):
        block = blocks[i]
        if isinstance(block, hwp5.Paragraph):
            heading = re.fullmatch(r"\((\d+)\)\s*(.+)", texts[i])
            if heading:
                current = areas.setdefault(clean(heading[2]), ContentArea(clean(heading[2])))
            elif texts[i]:
                unknown.append(f"내용 체계 표 밖 글: {texts[i][:60]}")
        elif current is not None:
            parse_content_table(block, current)

    units = _read_units(blocks, texts, standards + 1, guide)
    teaching, assessment, guide_pages = _read_guide(blocks, texts, guide + 1, end, unknown)
    return Notice(path, number, subject, doc, areas, units, teaching, assessment, guide_pages,
                  _toc_check(document), unknown)


def _toc_check(document: hwp5.Document) -> list[tuple[str, int, int | None]]:
    """차례 쪽수와 계산한 쪽 비교(차례 뒤에 제목 줄이 처음 나오는 블록의 쪽)."""
    titles = {title for title, _ in document.toc}
    seen: dict[str, int | None] = {}
    for block in document.blocks:
        if isinstance(block, hwp5.Paragraph) and "\t" in block.text:
            continue
        lines = block.text.split("\n") if isinstance(block, hwp5.Paragraph) else hwp5.block_text(block).split("\n")
        for line in lines:
            line = clean(line)
            if line in titles and line not in seen:
                seen[line] = block.page
    return [(title, page, seen.get(title)) for title, page in document.toc]


def _read_units(blocks, texts, start: int, end: int) -> list[Unit]:
    units: list[Unit] = []
    band: str | None = None
    band_heading = ""
    unit: Unit | None = None
    mode = None  # None(성취기준)·explanation·consideration
    codes: list[str] = []
    for i in range(start, end):
        block, text = blocks[i], texts[i]
        if isinstance(block, hwp5.Paragraph):
            band_match = re.fullmatch(r"\[(초등학교|중학교)\s*(\d\s*[~∼-]\s*\d\s*학년)?\]", text or "")
            if band_match:
                if band_match[1] == "중학교":
                    band = None
                elif band_match[2]:
                    band = band_of_header(band_match[2]) or "skip"
                else:
                    band = "초등"
                band_heading = text
                unit, mode = None, None
                continue
            if band in (None, "skip") or not text:
                continue
            heading = re.fullmatch(r"\((\d+)\)\s*(.+)", text)
            if heading:
                unit = Unit(clean(heading[2]), band, band_heading, text)
                units.append(unit)
                mode, codes = None, []
                continue
            if unit is None:
                continue
            if _is(text, "(가) 성취기준 해설"):
                mode = "explanation"
            elif _is(text, "(나) 성취기준 적용 시 고려 사항"):
                mode = "consideration"
            elif mode is None:
                _standard_lines(unit, [text], _pages(block))
            elif mode == "explanation":
                unit.explanation_paragraphs += 1
                leading = LEADING_CODES.match(text)
                if leading:
                    codes = expand_codes(leading[1])
                    unit.explanation_items.append(codes)
                    for code in codes:
                        unit.explanations.setdefault(code, []).append(text)
                elif codes:
                    for code in codes:
                        unit.explanations[code].append(text)
                else:
                    unit.unknown.append(f"해설 앞 글: {text[:60]}")
                for code in codes:
                    unit.explanation_pages.setdefault(code, set()).update(_pages(block))
            else:
                unit.considerations.append(text)
                unit.consideration_pages.update(_pages(block))
        elif band not in (None, "skip") and unit is not None:
            if mode is None:
                lines = [t for cell in sorted(block.cells, key=lambda c: (c.row, c.col)) for t in cell_lines(cell)]
                _standard_lines(unit, lines, _pages(block))
            elif mode == "consideration" and unit.considerations:
                table_text = clean(hwp5.block_text(block).replace("\n", " / "))
                unit.considerations[-1] = f"{unit.considerations[-1]}\n{table_text}"
                unit.consideration_pages.update(_pages(block))
            else:
                unit.unknown.append(f"{mode} 표: {hwp5.block_text(block)[:60]}")
    return units


def _standard_lines(unit: Unit, lines: list[str], pages: set[int]) -> None:
    activity = False
    subtopic = None
    for text in (clean(t) for t in lines):
        match = CODE_LINE.match(text)
        if match:
            code = code_of(match[1])
            unit.standards.append((code, clean(match[2]), match[1]))
            if subtopic:
                unit.subtopics[code] = subtopic
            unit.pages.update(pages)
            activity = False
        elif _is(text, "<탐구 활동>"):
            activity = True
        elif activity and re.match(r"^[•⋅]", text):
            unit.activities.append(clean(text.lstrip("•⋅ ")))
        elif re.match(r"^[①-⑳]", text):
            subtopic = clean(text[1:])
        elif text and not text.startswith("[") and len(text) <= 30:
            subtopic = text  # 원문자가 빠진 소단원 제목(수학 '무게'·'각도')
        elif text:
            unit.unknown.append(f"성취기준 칸 글: {text[:60]}")


# 교수⋅학습 및 평가 뒤에 바로 오는 다음 공통 교육과정 교과 제목(사회과 별책 7의 사회 다음 '역사').
# 제목 줄이 마지막 평가 항목과 같은 문단에 들어 있어 문단 단위 끝 판정(stops)으로는 걸리지 않음
NEXT_SUBJECT_TITLES = ("역사",)


def _read_guide(blocks, texts, start: int, end: int, unknown: list[str]):
    """3. 교수⋅학습 및 평가: (가)·(나)… 항목 하나가 한 줄. 그 아래 ①·㉠ 등은 항목에 줄바꿈으로 잇는다."""
    teaching: list[str] = []
    assessment: list[str] = []
    target = None
    pages: set[int] = set()
    for i in range(start, end):
        block = blocks[i]
        if isinstance(block, hwp5.Paragraph):
            lines = [clean(part) for part in block.text.split("\n")]
        else:
            lines = [clean(hwp5.block_text(block).replace("\n", " / "))]
        for text in filter(None, lines):
            if _is(text, *NEXT_SUBJECT_TITLES):  # 다음 교과 제목 줄에서 끝(같은 문단 안에 붙어 있음)
                return teaching, assessment, pages
            if _is(text, "가. 교수⋅학습"):
                target = teaching
            elif _is(text, "나. 평가"):
                target = assessment
            elif target is None:
                unknown.append(f"교과 지침 앞 글: {text[:60]}")
            elif re.fullmatch(r"\(\d+\)\s*\S.{0,30}", text) and not re.match(r"^\(\d+\)\s*.+[다요]\.$", text):
                continue  # (1) 교수⋅학습의 방향 같은 소제목
            else:
                item = re.match(r"^\(([가-하])\)\s*(.+)$", text)
                if item:
                    target.append(clean(item[2]))
                elif target:
                    target[-1] = f"{target[-1]}\n{text}"
                else:
                    unknown.append(f"교과 지침 첫 항목 앞 글: {text[:60]}")
                pages.update(_pages(block))
    return teaching, assessment, pages


# --- 생각 유형(thinking_types.md) ----------------------------------------------------------------

THINKING_SECTIONS = {"근거": "basis", "요소": "elements", "질문에 꼭 넣을 것": "questionMust",
                     "질문에 넣지 않을 것": "questionMustNot", "메모": "notes"}


def read_thinking_types(path: Path = THINKING_TYPES) -> list[dict]:
    """`## 레코드: CODE 이름` 아래 `### 근거` 등 목록을 생각 유형 레코드로 옮긴다.

    목록 줄 모양: 근거 `- 틀 이름 | 출처 표기`, 요소 `- CODE | 이름 | 공통 설명`, 나머지 `- 문장`.
    """
    records: list[dict] = []
    record = None
    section = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        heading = re.fullmatch(r"## 레코드: ([A-Z]+) (.+)", line)
        if heading:
            record = {"kind": "thinking_type", "type": heading[1], "name": heading[2].strip(), "basis": [],
                      "elements": [], "questionMust": [], "questionMustNot": [], "reviewed": False,
                      "source": {"doc": "scripts/knowledge/thinking_types.md, docs/design/functional-spec.md 1.5(#262)",
                                 "section": f"{heading[2].strip()} 출제 지침(팀이 쓴 기준안)"},
                      "notes": []}
            records.append(record)
            section = None
            continue
        if line.startswith("## "):
            record, section = None, None
            continue
        sub = re.fullmatch(r"### (.+)", line)
        if sub and record is not None:
            section = THINKING_SECTIONS.get(sub[1].strip())
            continue
        if record is None or section is None or not line.startswith("- "):
            continue
        body = line[2:].strip()
        if section == "basis":
            framework, attribution = (part.strip() for part in body.split("|", 1))
            record["basis"].append({"framework": framework, "attribution": attribution})
        elif section == "elements":
            code, label, description = (part.strip() for part in body.split("|", 2))
            record["elements"].append({"code": code, "label": label, "description": description,
                                       "requiredDefault": None})
        else:
            record[section].append(body)
    for record in records:
        if not record["notes"]:
            del record["notes"]
    return records


# --- 레코드 만들기 --------------------------------------------------------------------------------

def _source(doc: str, section: str, pages: set[int]) -> dict:
    if not pages:
        raise ValueError(f"쪽을 정하지 못함: {doc} {section}")
    return {"doc": doc, "notice": NOTICE, "section": section, "pages": sorted(pages)}


def _band_of_code(code: str) -> str:
    return {"4": "초3~4", "6": "초5~6"}.get(code[0], "")


def _semester_source(row: dict, band: str) -> str:
    seoul = SEOUL_14 + " 「3-4성취기준 단원 연결표」" if band == "초3~4" else SEOUL_56
    gyeonggi = GYEONGGI_34 if band == "초3~4" else GYEONGGI_56
    basis = row.get("basis", "")
    if basis in (BASIS_SAME, BASIS_DIFF):
        label = f"{gyeonggi}(팀 정리본으로 읽음), 대조: {seoul}"
    elif basis == BASIS_SHEET:
        label = SEOUL_14 + " 과학 시트"
    else:
        label = seoul
    return f"{label}(코드↔학기만 사용)"


class SubjectRecords:
    """교과 별책 한 권 → 성취기준·영역·내용 요소·교과 지침 레코드."""

    def __init__(self, notice: Notice, seed: dict[str, dict], semesters: dict[str, dict]):
        self.notice, self.seed, self.semesters = notice, seed, semesters
        self.subject, self.doc = notice.subject, notice.doc
        self.standards: list[dict] = []
        self.domains: list[dict] = []
        self.contents: list[dict] = []
        self.domain_ids: dict[tuple[str, str], str] = {}
        self.statement_diffs: list[dict] = []
        self.missing_areas: list[str] = []
        self.unit_bands = [(unit, sorted({_band_of_code(c) for c, _, _ in unit.standards})
                            if unit.band == "초등" else [unit.band]) for unit in notice.units]

    def build(self) -> None:
        for band in BAND_GRADES:
            if self.subject in SCOPE_BOTH:
                for unit, bands in self.unit_bands:
                    if band in bands:
                        area = self.notice.areas.get(unit.name)
                        if area is None:
                            self.missing_areas.append(f"{self.subject} {band} {unit.name}")
                        self.domain_ids[(band, unit.name)] = self.add_domain(band, unit.name, "BOTH", area, unit)
            else:
                for area in self.notice.areas.values():
                    if any(area.items.get(band, {}).values()):
                        self.add_domain(band, area.name, "CONTENT_SYSTEM", area, None)
                for unit, bands in self.unit_bands:
                    if band in bands:
                        self.domain_ids[(band, unit.name)] = self.add_domain(band, unit.name, "STANDARD_GROUP",
                                                                             None, unit)
        for unit, _ in self.unit_bands:
            for code, statement, raw_code in unit.standards:
                self.add_standard(unit, code, statement, raw_code)

    def _area_section(self, area: ContentArea) -> str:
        return f"2. 가. 내용 체계 ({list(self.notice.areas).index(area.name) + 1}) {area.name}"

    def add_domain(self, band: str, name: str, scope: str, area: ContentArea | None, unit: Unit | None) -> str:
        domain_id = f"{self.subject}:{band}:{name}"
        items = area.items.get(band, {}) if area else {}
        sections, pages, notes = [], set(), []
        if area is not None:
            sections.append(self._area_section(area))
            pages |= area.pages
        if unit is not None:
            sections.append(f"나. 성취기준 {unit.band_heading} {unit.heading} (나) 성취기준 적용 시 고려 사항")
            pages |= unit.consideration_pages or unit.pages
        record = {"kind": "domain", "id": domain_id, "subject": self.subject, "noticeGradeBand": band,
                  "area": name, "scope": scope, "coreIdeas": list(area.core_ideas) if area else [],
                  **{key: [{"group": g, "text": t} for g, t in items.get(key, [])] for key in CATEGORY_LETTER},
                  "considerations": list(unit.considerations) if unit else [], "reviewed": False,
                  "source": _source(self.doc, " / ".join(sections), pages)}
        if unit is not None and unit.activities:
            record["activities"] = list(unit.activities)
        if scope == "STANDARD_GROUP":
            only = "고려 사항·탐구 활동만" if self.subject == "과학" else "고려 사항만"
            particle = "은" if self.subject == "과학" else "는"
            notes.append(f"{self.subject}{particle} 내용 체계 영역과 성취기준 단원이 달라 단원 레코드에는 {only} 있음. "
                         "어느 내용 요소를 다루는지는 관계(covers)로 이음")
        if self.subject == "도덕":
            notes.append("도덕 성취기준·고려 사항은 원문에서 [초등학교] 한 묶음(3~4·5~6학년군 함께)이라 "
                         "이 고려 사항은 다른 학년군 영역과 같은 글. 내용 체계는 이 학년군 칸만 옮김")
        if notes:
            record["notes"] = notes
        self.domains.append(record)
        if area is not None:
            for key, letter in CATEGORY_LETTER.items():
                for group, text in items.get(key, []):
                    self.contents.append({
                        "kind": "content", "id": f"{domain_id}:{letter}:{content_hash(text)}", "domainId": domain_id,
                        "subject": self.subject, "noticeGradeBand": band, "area": name, "category": letter,
                        "group": group, "text": text, "reviewed": False,
                        "source": _source(self.doc, self._area_section(area), area.pages)})
        return domain_id

    def add_standard(self, unit: Unit, code: str, statement: str, raw_code: str) -> None:
        band = _band_of_code(code)
        info = self.seed.get(code)
        row = self.semesters.get(code, {})
        semester_list = [s for s in row.get("semesters", "").split(";") if s]
        explanation = "\n".join(unit.explanations.get(code, [])) or None
        notes = []
        if explanation is None:
            notes.append("원문 (가) 성취기준 해설에 이 성취기준 항목이 없음(원래 없는 것)")
        if raw_code != code:
            notes.append("원문 코드 표기는 줄표(–)이고 코드는 성취기준 표와 같은 붙임표(-)로 적음")
        if self.subject == "도덕" and band == "초5~6":
            notes.append("초5·초6 도덕 학기는 서울 5~6학년 단원(키워드) 연결표에서 옮긴 기준안(사용자 확인 전)")
        basis = row.get("basis", "자료 없음")
        if basis in (BASIS_DIFF, BASIS_SHEET, "자료 없음"):
            notes.append(f"학기 대응: {basis} "
                         f"(경기 {row.get('gyeonggi') or '없음'}, 서울 {row.get('seoul') or '없음'})")
        if info is None:
            self.statement_diffs.append({"code": code, "reason": "성취기준 표에 없는 코드"})
        elif statement != info["statement"]:
            self.statement_diffs.append({"code": code, "loose": loose(statement) == loose(info["statement"]),
                                         "source": statement, "seed": info["statement"]})
        section = f"2. 나. 성취기준 {unit.band_heading} {unit.heading}"
        if explanation:
            section += " / (가) 성취기준 해설"
        record = {"kind": "standard", "code": code, "subject": self.subject,
                  "grades": sorted({int(s[0]) for s in semester_list}) or BAND_GRADES[band],
                  "semesters": semester_list, "semesterSource": _semester_source(row, band),
                  "noticeGradeBand": band, "area": info["area"] if info else unit.name,
                  "domainId": self.domain_ids[(band, unit.name)], "statement": statement,
                  "explanation": explanation, "reviewed": False,
                  "source": _source(self.doc, section, unit.pages | unit.explanation_pages.get(code, set()))}
        if notes:
            record["notes"] = notes
        self.standards.append(record)

    def explanation_stats(self) -> dict:
        """해설: 레코드에 붙은 수와 원문 (가) 절 항목 수(앞머리 코드 기준)를 따로 센다."""
        stats = {band: Counter() for band in BAND_GRADES}
        for unit, _ in self.unit_bands:
            unit_codes = {c for c, _, _ in unit.standards}
            for codes in unit.explanation_items:
                for band in {_band_of_code(c) for c in codes}:
                    stats[band]["sourceItems"] += 1
                for code in codes:
                    stats[_band_of_code(code)]["sourceCodes"] += 1
                    stats[_band_of_code(code)]["orphanCodes"] += code not in unit_codes
            for code in unit_codes:
                stats[_band_of_code(code)]["standards"] += 1
                stats[_band_of_code(code)]["withExplanation"] += bool(unit.explanations.get(code))
        return {band: {"standards": stats[band]["standards"],
                       "standardsWithExplanation": stats[band]["withExplanation"],
                       "sourceExplanationItems": stats[band]["sourceItems"],
                       "sourceExplanationCodes": stats[band]["sourceCodes"],
                       "orphanExplanationCodes": stats[band]["orphanCodes"]} for band in BAND_GRADES}

    def guide(self) -> dict:
        return {"kind": "subject_guide", "id": f"{self.subject}:guide", "subject": self.subject,
                "teaching": self.notice.teaching, "assessment": self.notice.assessment, "reviewed": False,
                "source": _source(self.doc, "3. 교수⋅학습 및 평가 가. 교수⋅학습 (1) 방향·(2) 방법 / "
                                            "나. 평가 (1) 방향·(2) 방법", self.notice.guide_pages),
                "notes": ["항목 머리 (가)·(나) 번호는 빼고 본문만 옮김. "
                          "항목 아래 ①·㉠ 하위 항목은 줄바꿈으로 이어 붙임",
                          "교수⋅학습 및 평가는 공통 교육과정 교과 전체(초등학교~중학교)에 한 장"]}


def build_records(notices: list[Notice], seed: dict[str, dict], semesters: dict[str, dict],
                  thinking: list[dict]) -> tuple[list[dict], dict]:
    """다섯 교과 레코드를 성취기준 → 영역 → 내용 요소 → 교과 지침 → 생각 유형 순으로."""
    standards, domains, contents, guides = [], [], [], []
    report: dict = {"documents": [], "explanations": {}, "unknown": [], "statementDiffs": [],
                    "missingAreas": [], "tocCheck": {}}
    for notice in sorted(notices, key=lambda n: SUBJECT_ORDER.index(n.subject)):
        subject = SubjectRecords(notice, seed, semesters)
        subject.build()
        standards += subject.standards
        domains += subject.domains
        contents += subject.contents
        guides.append(subject.guide())
        data = notice.path.read_bytes()
        report["documents"].append({"doc": notice.doc, "bytes": len(data),
                                    "sha256": hashlib.sha256(data).hexdigest()})
        report["tocCheck"][notice.subject] = [list(item) for item in notice.toc_check]
        report["unknown"] += [f"{notice.subject}: {u}" for u in notice.unknown]
        report["unknown"] += [f"{notice.subject} {unit.heading}: {u}" for unit in notice.units for u in unit.unknown]
        report["statementDiffs"] += subject.statement_diffs
        report["missingAreas"] += subject.missing_areas
        report["explanations"][notice.subject] = subject.explanation_stats()
    return standards + domains + contents + guides + thinking, report


def summarize(records: list[dict], report: dict, differences: list[dict]) -> dict:
    by_kind = Counter(r["kind"] for r in records)
    standards = [r for r in records if r["kind"] == "standard"]
    table = {}
    for subject in SUBJECT_ORDER:
        table[subject] = {s: sum(1 for r in standards if r["subject"] == subject and s in r["semesters"])
                          for s in SEMESTERS}
        table[subject]["학기 없음"] = sum(1 for r in standards if r["subject"] == subject and not r["semesters"])
    by_grade = {f"초{g}": sum(1 for r in standards if g in r["grades"]) for g in (3, 4, 5, 6)}
    return {
        "dataset": DATASET,
        "notice": {"number": NOTICE, "date": NOTICE_DATE,
                   "documents": report["documents"]},
        "records": dict(sorted(by_kind.items())),
        "recordTotal": len(records),
        "standardsBySubjectBand": {f"{s} {b}": sum(1 for r in standards if r["subject"] == s
                                                  and r["noticeGradeBand"] == b)
                                   for s in SUBJECT_ORDER for b in BAND_GRADES},
        "standardsByGrade": by_grade,
        "standardsBySemester": table,
        "noSemester": sorted(r["code"] for r in standards if not r["semesters"]),
        "explanations": report["explanations"],
        "domainsWithoutConsiderations": sorted(r["id"] for r in records if r["kind"] == "domain"
                                               and r["scope"] != "CONTENT_SYSTEM" and not r["considerations"]),
        "domainsWithoutContent": sorted(r["id"] for r in records if r["kind"] == "domain"
                                        and r["scope"] != "STANDARD_GROUP"
                                        and not (r["knowledge"] or r["process"] or r["values"])),
        "statementDiffs": report["statementDiffs"],
        "semesterDifferences": differences,
        "tocCheck": report["tocCheck"],
        "unknownLines": report["unknown"],
        "missingAreas": report["missingAreas"],
    }


# --- 명령 -----------------------------------------------------------------------------------------


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def command_semester_map(args) -> int:
    seed = load_seed(args.seed)
    seoul = [read_seoul_14(args.seoul_14), read_seoul_56(args.seoul_56)]
    gyeonggi = read_gyeonggi(args.gyeonggi) if args.gyeonggi else None
    rows, differences = build_semester_map(seed, seoul, gyeonggi)
    write_semester_map(args.out, rows)
    print(json.dumps({"rows": len(rows), "noSemester": [r["code"] for r in rows if not r["semesters"]],
                      "differences": differences, "headerNotes": [n for s in seoul for n in s.notes],
                      "basis": Counter(r["basis"] for r in rows)}, ensure_ascii=False, indent=1))
    return 0


def command_extract(args) -> int:
    seed = load_seed(args.seed)
    semesters = read_semester_map(args.semester_map)
    notices = [read_notice(path) for path in args.sources]
    subjects = sorted(n.subject for n in notices)
    if subjects != sorted(SUBJECT_ORDER):
        raise SystemExit(f"별책 5~9 다섯 개가 필요함: {subjects}")
    records, report = build_records(notices, seed, semesters, read_thinking_types(args.thinking_types))
    differences = [{"code": r["code"], "gyeonggi": r["gyeonggi"], "seoul": r["seoul"]}
                   for r in semesters.values() if r["basis"] == BASIS_DIFF]
    summary = summarize(records, report, differences)
    write_jsonl(args.out, records)
    summary_path = args.summary or args.out.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("records", "recordTotal", "standardsBySubjectBand", "noSemester",
                                              "statementDiffs", "unknownLines", "missingAreas")},
                     ensure_ascii=False, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    semester = sub.add_parser("semester-map", help="학기 대응 자료(xlsx) → semester_map.csv")
    semester.add_argument("--seoul-14", type=Path, required=True, help="서울 1~4학년 평가계획 도움자료 xlsx")
    semester.add_argument("--seoul-56", type=Path, required=True, help="서울 5~6학년 단원(키워드) 연결표 xlsx")
    semester.add_argument("--gyeonggi", type=Path, help="경기 자료 국어·수학 팀 정리본 xlsx(대조용)")
    semester.add_argument("--seed", type=Path, default=SEED)
    semester.add_argument("--out", type=Path, default=HERE / "semester_map.csv")
    semester.set_defaults(func=command_semester_map)
    extract = sub.add_parser("extract", help="고시 별책 5~9 HWP → 추출 레코드 JSONL")
    extract.add_argument("sources", type=Path, nargs="+", help="[별책5]~[별책9] HWP 파일")
    extract.add_argument("--semester-map", type=Path, default=HERE / "semester_map.csv")
    extract.add_argument("--thinking-types", type=Path, default=THINKING_TYPES)
    extract.add_argument("--seed", type=Path, default=SEED)
    extract.add_argument("--out", type=Path, default=HERE / "data" / f"{DATASET}.jsonl")
    extract.add_argument("--summary", type=Path, help="요약 JSON(기본: 출력 이름.summary.json)")
    extract.set_defaults(func=command_extract)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
