"""#465 교육과정 고시 추출 시험: 추출 JSONL이 계약 C1·성취기준 표·원문 단위·학기 대응을 지킨다.

원문(고시 HWP·교육청 xlsx)은 저장소에 없으므로 기본 시험은 저장소의 추출본(`scripts/knowledge/data/`)과
요약(`curriculum-v1.summary.json`, 추출 때 원문에서 센 수)을 대조한다. 원문 폴더를 `KNOWLEDGE_SOURCE_DIR`로
주면(별책 5~9 HWP) 다시 추출해 저장소 추출본과 같은지도 본다. HWP 읽기는 합성 HWP5 파일로 시험한다.
CI(ci-contracts)는 PyYAML·jsonschema만 설치한다.
"""

import csv
import hashlib
import importlib.util
import json
import os
import re
import struct
import sys
import tempfile
import unicodedata
import unittest
import zlib
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "scripts/knowledge"
DATA = KNOWLEDGE / "data/curriculum-v1.jsonl"
SUMMARY = KNOWLEDGE / "data/curriculum-v1.summary.json"
SEMESTER_MAP = KNOWLEDGE / "semester_map.csv"
THINKING = KNOWLEDGE / "thinking_types.md"
SEED = ROOT / "backend/learning-service/db/seed/achievement_standards.sql"
SUBJECTS = ["국어", "도덕", "사회", "수학", "과학"]
BANDS = {"초3~4": (3, 4), "초5~6": (5, 6)}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hwp5 = load_module("hwp5", KNOWLEDGE / "hwp5.py")
extract = load_module("extract_curriculum", KNOWLEDGE / "extract_curriculum.py")


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def target_seed():
    return extract.target_seed(extract.load_seed(SEED))


class ExtractedDataTests(unittest.TestCase):
    """저장소 추출본(curriculum-v1)이 이슈 "검사(시험)" 항목을 지킨다."""

    @classmethod
    def setUpClass(cls):
        cls.records = load_jsonl(DATA)
        cls.summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        cls.by_kind = {}
        for record in cls.records:
            cls.by_kind.setdefault(record["kind"], []).append(record)
        cls.standards = {r["code"]: r for r in cls.by_kind["standard"]}
        cls.domains = {r["id"]: r for r in cls.by_kind["domain"]}
        cls.seed = target_seed()

    def test_records_pass_c1_schema(self):
        schema = json.loads((KNOWLEDGE / "schema/curriculum-record.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        for record in self.records:
            errors = [e.message for e in validator.iter_errors(record)]
            self.assertEqual(errors, [], record.get("id") or record.get("code") or record.get("type"))

    def test_standard_codes_equal_seed_codes(self):
        """5개 교과 초3·초4·초5·초6 코드 집합이 성취기준 표와 같다(빠진 코드·남는 코드 0)."""
        missing = sorted(set(self.seed) - set(self.standards))
        extra = sorted(set(self.standards) - set(self.seed))
        print(f"\n[성취기준 코드] 추출 {len(self.standards)}개 / 성취기준 표 {len(self.seed)}개, "
              f"빠진 코드 {missing}, 남는 코드 {extra}")
        self.assertEqual((missing, extra), ([], []))
        self.assertEqual(len(self.by_kind["standard"]), len(self.standards))  # 코드 중복 없음
        for code, record in self.standards.items():
            self.assertEqual((record["subject"], record["noticeGradeBand"]),
                             (self.seed[code]["subject"], self.seed[code]["band"]), code)
            self.assertEqual(record["area"], self.seed[code]["area"], code)

    def test_statements_equal_seed(self):
        """코드별 문장이 성취기준 표와 같다. 공백·기호 차이만 허용하고 다른 것은 목록으로 남긴다."""
        exact_diffs = []
        for code, record in sorted(self.standards.items()):
            seed = self.seed[code]["statement"]
            self.assertEqual(extract.loose(record["statement"]), extract.loose(seed), code)
            if record["statement"] != seed:
                exact_diffs.append(code)
        print(f"\n[문장] 공백·기호만 다른 코드: {exact_diffs}")
        self.assertEqual(exact_diffs, sorted(d["code"] for d in self.summary["statementDiffs"]))
        self.assertTrue(all(d["loose"] for d in self.summary["statementDiffs"]))

    def test_explanations_match_source_items(self):
        """해설이 있는 성취기준 수를 교과별로 내고, 원문 (가) 절 항목이 가리키는 코드 수와 맞춘다."""
        lines = []
        for subject in SUBJECTS:
            for band in BANDS:
                records = [r for r in self.standards.values()
                           if r["subject"] == subject and r["noticeGradeBand"] == band]
                explained = [r for r in records if r["explanation"]]
                source = self.summary["explanations"][subject][band]
                lines.append(f"{subject} {band}: 해설 {len(explained)}/{len(records)} "
                             f"(원문 항목 {source['sourceExplanationItems']}개가 가리키는 코드 "
                             f"{source['sourceExplanationCodes']}개)")
                self.assertEqual(len(explained), source["sourceExplanationCodes"], f"{subject} {band}")
                self.assertEqual(source["orphanExplanationCodes"], 0, f"{subject} {band}")
                self.assertEqual(len(records), source["standards"])
        print("\n[해설] " + " / ".join(lines))
        for record in self.standards.values():
            if record["explanation"]:
                head = extract.LEADING_CODES.match(record["explanation"])
                self.assertIsNotNone(head, record["code"])
                self.assertIn(record["code"], extract.expand_codes(head[1]), record["code"])
            else:  # 원래 없는 것과 추출 실패를 구분: 원문에 항목이 없다는 표시가 있어야 함
                self.assertIn("원문 (가) 성취기준 해설에 이 성취기준 항목이 없음(원래 없는 것)", record["notes"])
        # 에픽 결정 요약의 원문 대조 값(수학 초3·초4 성취기준 47개 중 14개)
        self.assertEqual(self.summary["explanations"]["수학"]["초3~4"]["standardsWithExplanation"], 14)

    def test_every_domain_has_considerations_and_content(self):
        """영역마다 고려 사항·내용 체계가 비어 있지 않다(사회·과학은 단원·내용 체계 영역을 나눠서)."""
        for domain in self.domains.values():
            if domain["scope"] in ("BOTH", "STANDARD_GROUP"):
                self.assertTrue(domain["considerations"], domain["id"])
            if domain["scope"] in ("BOTH", "CONTENT_SYSTEM"):
                self.assertTrue(domain["coreIdeas"], domain["id"])
                self.assertTrue(domain["knowledge"] or domain["process"] or domain["values"], domain["id"])
            expected_scope = {"BOTH"} if domain["subject"] in ("국어", "도덕", "수학") else {
                "CONTENT_SYSTEM", "STANDARD_GROUP"}
            self.assertIn(domain["scope"], expected_scope, domain["id"])
        for record in self.standards.values():
            self.assertIn(self.domains[record["domainId"]]["scope"], ("BOTH", "STANDARD_GROUP"), record["code"])
        self.assertEqual((self.summary["domainsWithoutConsiderations"], self.summary["domainsWithoutContent"]),
                         ([], []))
        science = [d for d in self.domains.values() if d["subject"] == "과학" and d["scope"] == "STANDARD_GROUP"]
        self.assertTrue(all(d.get("activities") for d in science))  # 과학 단원의 <탐구 활동>

    def test_subject_guides_for_all_five_subjects(self):
        guides = {g["subject"]: g for g in self.by_kind["subject_guide"]}
        self.assertEqual(set(guides), set(SUBJECTS))
        for subject, guide in guides.items():
            self.assertEqual(guide["id"], f"{subject}:guide")
            self.assertTrue(guide["teaching"] and guide["assessment"], subject)
            self.assertNotIn("excerpt", guide)  # 샘플과 달리 (1) 방향·(2) 방법 전부
            for item in guide["teaching"] + guide["assessment"]:
                self.assertIsNone(re.match(r"^\([가-하]\)", item), item[:30])  # 항목 머리 번호는 뺌

    def test_content_ids_follow_c1_hash_rule(self):
        ids = [r.get("id") or r.get("code") or r.get("type") for r in self.records]
        self.assertEqual(len(ids), len(set(ids)))
        expected = set()
        for domain in self.domains.values():
            for key, letter in (("knowledge", "K"), ("process", "P"), ("values", "V")):
                for item in domain[key]:
                    digest = hashlib.sha256(unicodedata.normalize("NFC", item["text"]).encode()).hexdigest()[:8]
                    expected.add((f"{domain['id']}:{letter}:{digest}", item["text"], item["group"]))
        actual = {(c["id"], c["text"], c["group"]) for c in self.by_kind["content"]}
        self.assertEqual(actual, expected)
        for content in self.by_kind["content"]:
            self.assertIn(self.domains[content["domainId"]]["scope"], ("BOTH", "CONTENT_SYSTEM"))
            self.assertNotIn(content["text"], ("-", "–"))  # 원문 '-'(해당 없음)는 내용 요소가 아님

    def test_symbols_fractions_units_are_kept(self):
        """곱셈·나눗셈 기호·분수·단위가 빠지거나 깨지지 않는다(시범 추출에서 곱셈 기호가 빠졌던 문제)."""
        explanation = self.standards["4수01-04"]["explanation"]
        self.assertEqual(explanation.count("×"), 4)
        self.assertIn("‘(두 자리 수)×(한 자리 수)’", explanation)
        self.assertIn("‘(두 자리 수)÷(한 자리 수)’", self.standards["4수01-06"]["explanation"])
        self.assertIn("‘(자연수)÷(자연수)’", self.standards["6수01-10"]["statement"])
        self.assertIn("‘(분수)÷(자연수)’", self.standards["6수01-11"]["explanation"])
        self.assertIn("가능성을 0, 1/2, 1 등과 같은 수로", self.standards["6수04-05"]["explanation"])  # 수식 분수
        self.assertIn("1도(°)", self.standards["4수03-24"]["statement"])
        self.assertIn("g, ㎏", self.standards["4과01-03"]["explanation"])
        self.assertIn("(원주)÷(지름)", self.standards["6수03-15"]["explanation"])
        shapes = {i["text"] for i in self.domains["수학:초3~4:도형과 측정"]["knowledge"]}
        self.assertTrue({"각도(°)", "들이(L, mL)", "무게(kg, g, t)", "길이(mm, km)"} <= shapes)
        considerations = "\n".join(self.domains["수학:초3~4:수와 연산"]["considerations"])
        self.assertIn("소수점(.), ÷", considerations)
        text = json.dumps(self.records, ensure_ascii=False)
        self.assertNotIn("�", text)  # 깨진 글자 없음
        self.assertIsNone(re.search(r"[-\U000f0000-\U000fffff]", text))  # 한글 PUA 글자 없음
        self.assertNotIn(" over ", text)  # 수식 스크립트가 그대로 남지 않음

    def test_semesters_follow_semester_map(self):
        """학기는 semester_map.csv(코드↔학기만)와 같고, 학년은 학기에서 정한다. 학기 없는 성취기준 목록을 낸다."""
        with SEMESTER_MAP.open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            header, rows = reader.fieldnames, {row["code"]: row for row in reader}
        self.assertEqual(header, extract.SEMESTER_COLUMNS)
        self.assertEqual(set(rows), set(self.seed))
        semester = re.compile(r"^([3-6]-[12](;[3-6]-[12])*)?$")
        no_semester = []
        for code, row in rows.items():
            for column in ("semesters", "seoul", "gyeonggi", "seoulFocus"):
                self.assertRegex(row[column], semester, f"{code} {column}")  # 문장 없이 학기 글자만
            record = self.standards[code]
            chosen = [s for s in row["semesters"].split(";") if s]
            self.assertEqual(record["semesters"], chosen, code)
            grades = BANDS[record["noticeGradeBand"]]
            self.assertTrue(all(int(s[0]) in grades for s in chosen), code)
            self.assertEqual(record["grades"], sorted({int(s[0]) for s in chosen}) or list(grades), code)
            self.assertIn("코드↔학기만", record["semesterSource"])
            if not chosen:
                no_semester.append(code)
        print(f"\n[학기] 학기 대응이 없는 성취기준: {no_semester or '없음'}")
        self.assertEqual(no_semester, self.summary["noSemester"])
        differences = sorted(code for code, row in rows.items() if row["basis"] == extract.BASIS_DIFF)
        print(f"[학기] 경기·서울이 다른 코드 {len(differences)}개: {differences}")
        self.assertEqual(differences, sorted(d["code"] for d in self.summary["semesterDifferences"]))
        for code in differences:
            self.assertTrue(any(note.startswith("학기 대응:") for note in self.standards[code]["notes"]), code)
        moral = [r for r in self.standards.values() if r["subject"] == "도덕" and r["noticeGradeBand"] == "초5~6"]
        self.assertTrue(all(any("기준안" in n for n in r["notes"]) for r in moral))  # 초5·초6 도덕 학기는 기준안

    def test_summary_matches_records(self):
        self.assertEqual(self.summary["dataset"], "curriculum-v1")
        self.assertEqual((self.summary["notice"]["number"], self.summary["notice"]["date"]),
                         ("교육부 고시 제2022-33호", "2022-12-22"))
        documents = self.summary["notice"]["documents"]
        self.assertEqual(len(documents), 5)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", d["sha256"]) for d in documents))
        self.assertEqual(self.summary["records"], dict(sorted(Counter(r["kind"] for r in self.records).items())))
        self.assertEqual(self.summary["recordTotal"], len(self.records))
        for subject in SUBJECTS:
            for semester in extract.SEMESTERS:
                count = sum(1 for r in self.standards.values()
                            if r["subject"] == subject and semester in r["semesters"])
                self.assertEqual(self.summary["standardsBySemester"][subject][semester], count)
        self.assertEqual(self.summary["unknownLines"], [])  # 원문에서 어디에도 넣지 못한 줄 없음
        for subject, checks in self.summary["tocCheck"].items():  # 계산한 쪽이 차례 쪽수와 같음
            mismatched = [title for title, page, found in checks if found is not None and page != found]
            self.assertEqual(mismatched, [], subject)
        print("\n[레코드] " + json.dumps(self.summary["records"], ensure_ascii=False)
              + f" 합계 {self.summary['recordTotal']}")

    def test_excluded_sources_are_absent(self):
        """평가원 성취수준·교육청 문장은 넣지 않는다(교육청 자료는 학기 대응 출처 표기만)."""
        for record in self.records:
            for word in ("성취수준", "평가원", "경기도", "교육청"):
                self.assertNotIn(word, record["source"]["doc"])
            if record["kind"] != "thinking_type":
                self.assertTrue(record["source"]["doc"].startswith("교육부 고시 제2022-33호 [별책 "))
                self.assertEqual(record["source"]["notice"], "교육부 고시 제2022-33호")
                self.assertIs(record["reviewed"], False)


class ThinkingTypeTests(unittest.TestCase):
    """생각 유형 레코드 5개는 thinking_types.md에서 오고, 우리 말 지침과 출처 표기만 담는다."""

    @classmethod
    def setUpClass(cls):
        cls.records = [r for r in load_jsonl(DATA) if r["kind"] == "thinking_type"]

    def test_five_types_from_markdown(self):
        self.assertEqual([r["type"] for r in self.records], ["ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT"])
        self.assertEqual(self.records, extract.read_thinking_types(THINKING))
        codes = {e["code"] for r in self.records for e in r["elements"]}
        self.assertEqual(len(codes), 14)  # FN 1.5 표준 요소(#262)
        reflect = next(r for r in self.records if r["type"] == "REFLECT")
        self.assertEqual([e["code"] for e in reflect["elements"]],
                         ["REFLECT_CHANGE", "REFLECT_REASON", "REFLECT_CONNECT"])  # #262 돌아보기 3요소
        self.assertTrue(all(e["requiredDefault"] is None for r in self.records for e in r["elements"]))

    def test_our_words_and_attribution_only(self):
        for record in self.records:
            texts = record["questionMust"] + record["questionMustNot"] + [e["description"] for e in record["elements"]]
            for text in texts:
                self.assertIsNone(re.search(r"[A-Za-z]{4,}", text), text)  # 영어 원문 문장을 옮기지 않음
            for basis in record["basis"]:
                if "블룸" in basis["framework"] or "AAC&U" in basis["framework"]:
                    self.assertIn("참고", basis["attribution"])
                if "AAC&U" in basis["framework"]:
                    self.assertIn("보증을 받은 내용이 아님", basis["attribution"])
                    self.assertIn("원문", basis["attribution"])
        # 출처 목록 앞 본문에는 영어 문장이 없다(항목 이름처럼 다섯 낱말 이하만)
        markdown = THINKING.read_text(encoding="utf-8").split("## 5. 출처")[0]
        self.assertIsNone(re.search(r"[A-Za-z']+(?: [A-Za-z']+){5,}", markdown))


# --- 합성 HWP5 ------------------------------------------------------------------------------------


def record(tag, level, payload=b""):
    size = len(payload)
    if size >= 0xFFF:
        return struct.pack("<II", tag | (level << 10) | (0xFFF << 20), size) + payload
    return struct.pack("<I", tag | (level << 10) | (size << 20)) + payload


def text_payload(*parts):
    """글(str)·확장 제어(ctrl id) 조각 → PARA_TEXT 내용."""
    out = b""
    for part in parts:
        if isinstance(part, bytes):  # 확장 제어 문자 11 + ctrl id(뒤집어 저장) + 채움
            out += struct.pack("<H", 11) + part[::-1] + b"\0" * 8 + struct.pack("<H", 11)
        else:
            out += part.encode("utf-16-le")
    return out


def line_seg(y, height=1000):
    return struct.pack("<IiiiiiiiI", 0, y, height, height, 850, 600, 0, 40000, 0x60000)


def paragraph(level, parts, controls=b"", y=0, page_break=False):
    header = struct.pack("<IIHBB", 0, 0, 0, 0, 0x04 if page_break else 0)
    return (record(0x42, level, header) + record(0x43, level + 1, text_payload(*parts))
            + record(0x45, level + 1, line_seg(y)) + controls)


def ctrl_header(ctrl, level, inline=True, height=2000):
    payload = ctrl.encode("latin-1")[::-1] + struct.pack("<IiiII", 1 if inline else 0, 0, 0, 40000, height)
    return record(0x47, level, payload)


def table(level, cells, rows, cols):
    """cells: [(row, col, row_span, col_span, [문단 글])]. level은 CTRL_HEADER 수준."""
    out = ctrl_header("tbl ", level) + record(0x4D, level + 1, struct.pack("<IHH", 0, rows, cols))
    for row, col, row_span, col_span, texts in cells:
        cell = struct.pack("<HHI", len(texts), 0, 0) + struct.pack("<HHHHII", col, row, col_span, row_span,
                                                                     10000, 1000)
        out += record(0x48, level + 1, cell + b"\0" * 12)
        for text in texts:
            out += paragraph(level + 1, [text])
    return out


def equation(level, script):
    raw = script.encode("utf-16-le")
    return ctrl_header("eqed", level) + record(0x58, level + 1, struct.pack("<IH", 0, len(script)) + raw)


def compound_file(streams):
    """표준 CFB(섹터 512바이트). mini stream 기준을 0으로 두어 모든 스트림을 일반 섹터에 둔다."""
    sector = 512
    data_sectors, chains, start = [], {}, 1  # 섹터 0은 FAT
    for name, data in streams.items():
        count = max(1, -(-len(data) // sector))
        chains[name] = (start + 1, len(data))  # 디렉터리 섹터(1) 다음부터
        data_sectors.append(data.ljust(count * sector, b"\0"))
        start += count
    directory_sector = 1
    fat = [0xFFFFFFFD, 0xFFFFFFFE]
    position = 2
    for data in streams.values():
        count = max(1, -(-len(data) // sector))
        fat += [position + i + 1 for i in range(count - 1)] + [0xFFFFFFFE]
        position += count
    fat += [0xFFFFFFFF] * (128 - len(fat))

    def entry(name, kind, first, size):
        raw = name.encode("utf-16-le") + b"\0\0"
        return (raw.ljust(64, b"\0") + struct.pack("<HBB", len(raw), kind, 1) + struct.pack("<III", 0xFFFFFFFF,
                0xFFFFFFFF, 0xFFFFFFFF) + b"\0" * 36 + struct.pack("<IQ", first, size)).ljust(128, b"\0")

    directory = entry("Root Entry", 5, 0xFFFFFFFE, 0)
    for name, (first, size) in chains.items():
        directory += entry(name, 2, first, size)
    directory = directory.ljust(sector, b"\0")
    header = bytearray(512)
    header[0:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<HHHH", header, 24, 0x3E, 3, 0xFFFE, 9)
    struct.pack_into("<H", header, 32, 6)
    struct.pack_into("<I", header, 44, 1)  # FAT 섹터 수
    struct.pack_into("<I", header, 48, directory_sector)
    struct.pack_into("<I", header, 56, 0)  # mini stream 기준
    struct.pack_into("<IIII", header, 60, 0xFFFFFFFE, 0, 0xFFFFFFFE, 0)
    struct.pack_into("<109I", header, 76, 0, *([0xFFFFFFFF] * 108))
    return bytes(header) + struct.pack("<128I", *fat) + directory + b"".join(data_sectors)


def hwp_file(section, compressed=True):
    header = b"HWP Document File".ljust(32, b"\0") + struct.pack("<II", 0x05000300, 1 if compressed else 0)
    page_def = record(0x49, 2, struct.pack("<9IIi", 59528, 84188, 8504, 8504, 5668, 4252, 4252, 4252, 0, 0, 0))
    first = paragraph(0, ["교육부 고시 제2022-33호 [별책 8]"], ctrl_header("secd", 1) + page_def)
    body = first + section
    if compressed:
        body = zlib.compress(body)[2:-4]  # HWP5 본문은 머리 없는 deflate
    return compound_file({"FileHeader": header.ljust(256, b"\0"), "Section0": body})


class Hwp5ReaderTests(unittest.TestCase):
    """표준 라이브러리 HWP5 읽기: 문단·표 칸·수식·특수 글자."""

    def read(self, section):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.hwp"
            path.write_bytes(hwp_file(section))
            return hwp5.read_hwp(path)

    def test_paragraphs_tables_and_equations(self):
        section = (
            paragraph(0, ["가. 내용 체계"], y=1000)
            + paragraph(0, ["‘(두 자리 수)", b"eqed", "(한 자리 수)’ 기호 ", b"eqed"],
                        equation(1, "times") + equation(1, "{1} over {2}"), y=2000)
            + paragraph(0, [b"tbl "], table(1, [(0, 0, 2, 1, ["지식⋅", "이해"]), (0, 1, 1, 1, ["⋅길이(mm, km)"]),
                                                  (1, 1, 1, 1, ["⋅들이(L, mL)"])], 2, 2), y=3000)
            + paragraph(0, ["다음 쪽 ₩ 𝑥"], y=0, page_break=True)
        )
        document = self.read(section)
        texts = [b.text for b in document.blocks if isinstance(b, hwp5.Paragraph)]
        self.assertIn("‘(두 자리 수)×(한 자리 수)’ 기호 1/2", texts)
        self.assertIn("다음 쪽 ₩ 𝑥", texts)  # 대리 쌍 글자 보존
        grid = next(b for b in document.blocks if isinstance(b, hwp5.Table)).grid()
        self.assertIs(grid[0][0], grid[1][0])  # 합친 칸
        self.assertEqual(grid[1][1].text, "⋅들이(L, mL)")
        self.assertEqual(document.equations, 2)
        pages = [b.page for b in document.blocks]
        self.assertEqual(pages[-1], pages[0] + 1)  # 쪽 나눔

    def test_equation_scripts(self):
        cases = {"times": "×", "div": "÷", "{1} over {2}": "1/2", "{ax+b} over {cx+d}": "(ax+b)/(cx+d)",
                 "DEG": "°", "90^circ": "90°", "a LEQ b": "a ≤ b", "rm ANGLE ABC": "∠ ABC", "x^2": "x^2"}
        for script, expected in cases.items():
            self.assertEqual(hwp5.equation_text(script), expected, script)

    def test_private_use_and_control_characters(self):
        payload = "".join(chr(c) for c in (0xDB82, 0xDC54)).encode("utf-16-le", "surrogatepass")  # U+F0854
        payload += "책".encode("utf-16-le") + struct.pack("<H", 30) + struct.pack("<H", 9) + b"\0" * 14
        payload += "".join(chr(c) for c in (0xDB82, 0xDC55)).encode("utf-16-le", "surrogatepass")
        self.assertEqual("".join(r for r in hwp5._paragraph_runs(payload) if isinstance(r, str)), "『책 \t』")
        self.assertEqual(hwp5.HWP_PUA[0xF02B1], "①")

    def test_rejects_non_hwp_and_broken_files(self):
        with self.assertRaises(hwp5.Hwp5Error):
            hwp5.CompoundFile(b"not an ole file" * 100)
        with self.assertRaises(hwp5.Hwp5Error):
            hwp5.parse_records(struct.pack("<I", 0x43 | (0 << 10) | (100 << 20)) + b"short")


class ParsingHelperTests(unittest.TestCase):
    def test_items_labels_codes(self):
        self.assertEqual(extract.split_items(["⋅중력  ⋅마찰력  ⋅탄성력", "⋅시각과 시간", "(시, 분)"]),
                         ["중력", "마찰력", "탄성력", "시각과 시간(시, 분)"])
        self.assertEqual(extract.split_items(["⋅비교⋅분석하기"]), ["비교⋅분석하기"])  # 낱말 안 가운뎃점은 그대로
        self.assertEqual(extract.label_of(["내용", "확인⋅추론⋅", "평가"]), "내용 확인⋅추론⋅평가")
        self.assertEqual(extract.label_of(["자연-", "인간의", "상호 작용"]), "자연-인간의 상호 작용")
        self.assertEqual(extract.expand_codes("[4과09-01∼02] 자석"), ["4과09-01", "4과09-02"])
        self.assertEqual(extract.expand_codes("[4사05-01]과 [4사05-02]에서"), ["4사05-01", "4사05-02"])
        self.assertEqual(extract.code_of("4사01–01"), "4사01-01")
        self.assertEqual(extract.band_of_header("3-4학년군"), "초3~4")
        self.assertEqual(extract.band_of_header("5∼6학년"), "초5~6")
        self.assertIsNone(extract.band_of_header("1~3학년"))

    def test_excel_date_header_is_semester_text(self):
        """서울 1~4학년 연결표 머리글은 엑셀이 날짜로 바꾼 값(45717=3월 1일 → '3-1')."""
        self.assertEqual([extract.excel_header_semester(v) for v in ("45717", "45718", "45719", "45720")],
                         ["3-1", "3-2", "3-3", "3-4"])  # 3-3·3-4는 머리글 오타(실제 4-1·4-2), 교과별 시트로 바로잡음
        self.assertEqual(extract.excel_header_semester("5-2"), "5-2")


@unittest.skipUnless(os.environ.get("KNOWLEDGE_SOURCE_DIR"), "원문 HWP 폴더(KNOWLEDGE_SOURCE_DIR)가 있을 때만")
class ReExtractTests(unittest.TestCase):
    """원문을 다시 추출하면 저장소 추출본과 같다(재현성)."""

    def test_reextract_equals_committed_jsonl(self):
        folder = Path(os.environ["KNOWLEDGE_SOURCE_DIR"])
        sources = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".hwp")
        notices = [extract.read_notice(p) for p in sources]
        records, _ = extract.build_records(notices, extract.load_seed(SEED),
                                           extract.read_semester_map(SEMESTER_MAP),
                                           extract.read_thinking_types(THINKING))
        self.assertEqual(records, load_jsonl(DATA))


if __name__ == "__main__":
    unittest.main()
