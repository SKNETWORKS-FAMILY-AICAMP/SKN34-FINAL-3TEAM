"""HWP5(한글 97 이후 바이너리) 문서의 본문 문단·표를 표준 라이브러리만으로 읽는다(#465).

HWP5 파일은 OLE 복합 문서(CFB) 안에 `BodyText/SectionN` 스트림이 있고, 스트림은 zlib(raw deflate)로
압축된 레코드 열이다. 이 모듈은 다음만 한다.

- CFB 스트림 읽기(FAT·mini FAT·DIFAT)
- 레코드를 수준(level)으로 나무 구조로 묶기
- 문단(`PARA_TEXT`) 글자, 표(`tbl `) 칸 구조, 수식(`eqed`) 스크립트를 순서대로 꺼내기
- 한글이 저장한 줄 배치로 블록마다 인쇄 쪽 번호를 어림하기(아래 "쪽 번호" 절)

배포용(암호화) 문서는 읽지 않는다(`Hwp5Error`). 머리말·꼬리말·각주·쪽 번호 같은 조판 요소는 본문에서
뺀다. 그림·글상자 안 글은 문단으로 이어 붙인다.

원문은 신뢰하지 않는 입력이므로 크기·순환 검사를 하고, 파일을 실행하거나 외부 프로그램을 부르지 않는다.
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path

SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
END_OF_CHAIN = 0xFFFFFFFE
MAX_STREAM = 256 * 1024 * 1024

# 레코드 태그(HWPTAG_BEGIN = 0x10)
TAG_PARA_HEADER = 0x42
TAG_PARA_TEXT = 0x43
TAG_CTRL_HEADER = 0x47
TAG_LIST_HEADER = 0x48
TAG_TABLE = 0x4D
TAG_EQEDIT = 0x58

# 문단 글자 속 제어 문자: 글자 하나 크기(char), 8글자 크기(inline·extended)
CHAR_CONTROLS = {0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31}
EXTENDED_CONTROLS = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}
# 본문에서 빼는 조판 요소(머리말·꼬리말·각주·미주·쪽 번호·감추기 등)
SKIPPED_CONTROLS = {"head", "foot", "fn  ", "en  ", "pgnp", "pghd", "nwno", "atno", "pgct", "bokm", "idxm",
                    "tcmt", "tdut", "cold", "secd"}


# 한글 글꼴 사용자 정의 영역(PUA) 글자 중 고시 별책에 나오는 것. 나머지 PUA 글자는 그대로 둔다
HWP_PUA = {0xF0854: "『", 0xF0855: "』", 0xF0A0: "⋅",
           **{0xF02B1 + i: chr(0x2460 + i) for i in range(20)}}  # 원문자 ①~⑳


class Hwp5Error(ValueError):
    """HWP5로 읽을 수 없는 파일."""


@dataclass
class Paragraph:
    text: str
    page: int | None = None  # 인쇄 쪽(어림, 아래 쪽 번호 절)
    page_end: int | None = None


@dataclass
class Cell:
    row: int
    col: int
    row_span: int
    col_span: int
    blocks: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(block_text(block) for block in self.blocks).strip()


@dataclass
class Table:
    rows: int
    cols: int
    cells: list[Cell]
    page: int | None = None
    page_end: int | None = None

    def grid(self) -> list[list[Cell | None]]:
        """행·열 격자. 합친 칸은 왼쪽 위 칸 객체를 펼친 자리마다 같은 객체로 둔다."""
        grid: list[list[Cell | None]] = [[None] * self.cols for _ in range(self.rows)]
        for cell in self.cells:
            for r in range(cell.row, min(cell.row + cell.row_span, self.rows)):
                for c in range(cell.col, min(cell.col + cell.col_span, self.cols)):
                    grid[r][c] = cell
        return grid


def block_text(block) -> str:
    if isinstance(block, Paragraph):
        return block.text
    rows = []
    for row in block.grid():
        seen, parts = set(), []
        for cell in row:
            if cell is not None and id(cell) not in seen:
                seen.add(id(cell))
                parts.append(cell.text.replace("\n", " / "))
        rows.append(" | ".join(parts))
    return "\n".join(rows)


# --- CFB(OLE 복합 문서) ---------------------------------------------------------------------------


class CompoundFile:
    """CFB 스트림 읽기. 쓰기·수정은 하지 않는다."""

    def __init__(self, data: bytes):
        if data[:8] != SIGNATURE or len(data) < 512:
            raise Hwp5Error("OLE 복합 문서가 아님")
        self.data = data
        self.sector_size = 1 << struct.unpack_from("<H", data, 30)[0]
        self.mini_size = 1 << struct.unpack_from("<H", data, 32)[0]
        fat_count = struct.unpack_from("<I", data, 44)[0]
        first_dir = struct.unpack_from("<I", data, 48)[0]
        self.cutoff = struct.unpack_from("<I", data, 56)[0]
        first_mini, mini_count = struct.unpack_from("<II", data, 60)
        first_difat, difat_count = struct.unpack_from("<II", data, 68)
        per_sector = self.sector_size // 4
        difat = list(struct.unpack_from("<109I", data, 76))
        sector = first_difat
        for _ in range(difat_count):
            if sector >= END_OF_CHAIN:
                break
            values = struct.unpack_from(f"<{per_sector}I", data, self._offset(sector))
            difat += values[:-1]
            sector = values[-1]
        self.fat: list[int] = []
        for sector in difat[:fat_count]:
            self.fat += struct.unpack_from(f"<{per_sector}I", data, self._offset(sector))
        directory = self._chain(first_dir)
        self.entries: dict[str, tuple[int, int, int]] = {}
        self.order: list[str] = []
        for pos in range(0, len(directory) - 127, 128):
            raw = directory[pos:pos + 128]
            name_len = struct.unpack_from("<H", raw, 64)[0]
            if not 2 <= name_len <= 64:
                continue
            name = raw[:name_len - 2].decode("utf-16-le", errors="replace")
            kind = raw[66]
            start = struct.unpack_from("<I", raw, 116)[0]
            size = struct.unpack_from("<Q", raw, 120)[0] & 0xFFFFFFFF
            if name not in self.entries:
                self.entries[name] = (kind, start, size)
                self.order.append(name)
        root = self.entries.get("Root Entry")
        if root is None:
            raise Hwp5Error("루트 항목 없음")
        self.mini_stream = self._chain(root[1])[:root[2]]
        self.mini_fat: list[int] = []
        if mini_count:
            raw = self._chain(first_mini)
            self.mini_fat = list(struct.unpack(f"<{len(raw) // 4}I", raw))

    def _offset(self, sector: int) -> int:
        offset = (sector + 1) * self.sector_size
        if offset + self.sector_size > len(self.data):
            raise Hwp5Error("섹터 위치가 파일 밖")
        return offset

    def _chain(self, sector: int) -> bytes:
        out, steps = bytearray(), 0
        while sector < END_OF_CHAIN:
            if steps > len(self.fat) or sector >= len(self.fat):
                raise Hwp5Error("FAT 체인이 끊기거나 순환함")
            start = self._offset(sector)
            out += self.data[start:start + self.sector_size]
            sector = self.fat[sector]
            steps += 1
        return bytes(out)

    def stream(self, name: str) -> bytes:
        if name not in self.entries:
            raise Hwp5Error(f"스트림 없음: {name}")
        _, start, size = self.entries[name]
        if size > MAX_STREAM:
            raise Hwp5Error(f"스트림이 너무 큼: {name}")
        if size >= self.cutoff:
            return self._chain(start)[:size]
        out, sector, steps = bytearray(), start, 0
        while sector < END_OF_CHAIN and len(out) < size:
            if steps > len(self.mini_fat) or sector >= len(self.mini_fat):
                raise Hwp5Error("mini FAT 체인이 끊기거나 순환함")
            out += self.mini_stream[sector * self.mini_size:(sector + 1) * self.mini_size]
            sector = self.mini_fat[sector]
            steps += 1
        return bytes(out[:size])


# --- 레코드 ---------------------------------------------------------------------------------------


@dataclass
class Record:
    tag: int
    level: int
    payload: bytes
    children: list[Record] = field(default_factory=list)


def parse_records(raw: bytes) -> list[Record]:
    """레코드 열을 수준으로 묶은 나무(최상위 목록)."""
    roots: list[Record] = []
    stack: list[Record] = []
    pos = 0
    while pos + 4 <= len(raw):
        header = struct.unpack_from("<I", raw, pos)[0]
        tag, level, size = header & 0x3FF, (header >> 10) & 0x3FF, (header >> 20) & 0xFFF
        pos += 4
        if size == 0xFFF:
            size = struct.unpack_from("<I", raw, pos)[0]
            pos += 4
        if pos + size > len(raw):
            raise Hwp5Error("레코드 길이가 스트림 밖")
        record = Record(tag, level, raw[pos:pos + size])
        pos += size
        while stack and stack[-1].level >= level:
            stack.pop()
        (stack[-1].children if stack else roots).append(record)
        stack.append(record)
    return roots


def ctrl_id(payload: bytes) -> str:
    if len(payload) < 4:
        return ""
    return struct.unpack_from("<I", payload, 0)[0].to_bytes(4, "big").decode("latin-1")


# --- 수식 ---------------------------------------------------------------------------------------

EQUATION_WORDS = {
    "times": "×", "div": "÷", "cdot": "·", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠",
    "neq": "≠", "approx": "≈", "pm": "±", "circ": "°", "deg": "°", "cdots": "⋯", "ldots": "…",
    "angle": "∠", "triangle": "△", "square": "□", "box": "□", "bigcirc": "○", "rarrow": "→",
    "larrow": "←", "therefore": "∴", "because": "∵", "inf": "∞", "infty": "∞", "perp": "⊥",
    "prime": "′", "smallsum": "∑", "sum": "∑", "pi": "π", "alpha": "α", "beta": "β", "theta": "θ",
    "notin": "∉", "in": "∈", "subset": "⊂", "nsubset": "⊄", "cup": "∪", "smallinter": "∩", "inter": "∩",
    "emptyset": "∅", "sim": "~", "lrarrow": "↔", "bot": "⊥", "sqrt": "√", "delta": "Δ", "sigma": "σ",
    "smallprod": "∏", "it": "", "rm": "", "bold": "", "left": "", "right": "", "big": "",
}


def _fraction_part(part: str) -> str:
    part = part.strip()
    return f"({part})" if re.search(r"[\s+\-×÷]", part) else part


def _equation_groups(script: str) -> str:
    """`{a} over {b}` → `a/b`. 중괄호 묶음은 안쪽부터 풀어 낸다."""
    pattern = re.compile(r"\{([^{}]*)\}\s*over\s*\{([^{}]*)\}", re.IGNORECASE)
    for _ in range(50):
        replaced = pattern.sub(lambda m: f"{_fraction_part(m[1])}/{_fraction_part(m[2])}", script)
        replaced = re.sub(r"\{([^{}]*)\}", lambda m: m[1], replaced)
        if replaced == script:
            break
        script = replaced
    return script


def equation_text(script: str) -> str:
    """한글 수식 편집기 스크립트를 읽을 수 있는 글로 옮긴다(조판 명령은 버리고 기호는 남긴다).

    분수 `{a} over {b}`는 `a/b`, 곱셈·나눗셈 `times`·`div`는 ×·÷, 도 `DEG`·`^circ`는 °로 옮긴다.
    """
    text = script.replace("`", " ").replace("~", " ").replace("#", " ").replace("&", "")
    text = re.sub(r"\^\s*\{?\s*circ\s*\}?", "°", text, flags=re.IGNORECASE)
    text = _equation_groups(text)
    text = re.sub(r"(\S+)\s+over\s+(\S+)", r"\1/\2", text, flags=re.IGNORECASE)
    text = text.replace("->", "→")

    def word(match: re.Match) -> str:
        return EQUATION_WORDS.get(match[0].lower(), match[0])

    text = re.sub(r"[A-Za-z]+", word, text)
    text = re.sub(r"\s*\^\s*", "^", text)
    text = re.sub(r"\s*_\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def equation_script(record: Record) -> str | None:
    for child in record.children:
        if child.tag == TAG_EQEDIT and len(child.payload) >= 6:
            length = struct.unpack_from("<H", child.payload, 4)[0]
            return child.payload[6:6 + 2 * length].decode("utf-16-le", errors="replace")
    return None


# --- 문단·표 -------------------------------------------------------------------------------------


def _paragraph_runs(text_payload: bytes) -> list:
    """문단 글자를 [str | ('ctrl', 차례, id)] 열로 나눈다."""
    runs: list = []
    buffer = bytearray()  # UTF-16LE 그대로 모았다가 한 번에 푼다(대리 쌍 글자 보존)
    index = 0
    pos = 0

    def flush():
        if buffer:
            runs.append(buffer.decode("utf-16-le", errors="replace").translate(HWP_PUA))
            buffer.clear()

    while pos + 1 < len(text_payload):
        code = struct.unpack_from("<H", text_payload, pos)[0]
        if code >= 32:
            buffer += text_payload[pos:pos + 2]
            pos += 2
        elif code in CHAR_CONTROLS:
            if code == 10:
                buffer += "\n".encode("utf-16-le")
            elif code in (24, 30, 31):
                buffer += ("-" if code == 24 else " ").encode("utf-16-le")
            pos += 2
        else:
            if code == 9:
                buffer += "\t".encode("utf-16-le")
            elif code in EXTENDED_CONTROLS:
                ident = text_payload[pos + 2:pos + 6][::-1].decode("latin-1", errors="replace")
                flush()
                runs.append(("ctrl", index, ident))
                index += 1
            pos += 16
    flush()
    return runs


def _list_groups(children: list[Record]) -> list[tuple[Record, list[Record]]]:
    """LIST_HEADER 뒤에 오는 같은 수준 PARA_HEADER들을 한 묶음으로."""
    groups: list[tuple[Record, list[Record]]] = []
    for child in children:
        if child.tag == TAG_LIST_HEADER:
            groups.append((child, []))
        elif child.tag == TAG_PARA_HEADER and groups:
            groups[-1][1].append(child)
    return groups


def _table(record: Record) -> Table:
    table = next((c for c in record.children if c.tag == TAG_TABLE), None)
    if table is None or len(table.payload) < 8:
        raise Hwp5Error("표 레코드 없음")
    rows, cols = struct.unpack_from("<HH", table.payload, 4)
    cells = []
    for header, paragraphs in _list_groups(record.children):
        if len(header.payload) < 16:
            continue
        col, row, col_span, row_span = struct.unpack_from("<HHHH", header.payload, 8)
        cell = Cell(row, col, max(row_span, 1), max(col_span, 1))
        for paragraph in paragraphs:
            cell.blocks.extend(_paragraph_blocks(paragraph))
        cells.append(cell)
    return Table(rows, cols, cells)


def _nested_text(record: Record) -> list:
    """글상자·그림 묶음 안 문단."""
    blocks: list = []
    for _, paragraphs in _list_groups(record.children):
        for paragraph in paragraphs:
            blocks.extend(_paragraph_blocks(paragraph))
    for child in record.children:
        if child.tag not in (TAG_LIST_HEADER, TAG_PARA_HEADER):
            blocks.extend(_nested_text(child))
    return blocks


def _paragraph_blocks(paragraph: Record) -> list:
    text = next((c for c in paragraph.children if c.tag == TAG_PARA_TEXT), None)
    controls = [c for c in paragraph.children if c.tag == TAG_CTRL_HEADER]
    if text is None:
        return []
    blocks: list = []
    floating: list = []  # 글자처럼 취급하지 않는 표·글상자는 문단 글 뒤에 둔다(문단 맨 앞에 고정돼 있어도)
    line: list[str] = []

    def flush():
        joined = "".join(line).strip()
        if joined:
            blocks.append(Paragraph(joined))
        line.clear()

    for run in _paragraph_runs(text.payload):
        if isinstance(run, str):
            line.append(run)
            continue
        _, index, _ = run
        if index >= len(controls):
            continue
        control = controls[index]
        kind = ctrl_id(control.payload)
        if kind == "eqed":
            script = equation_script(control)
            if script:
                line.append(equation_text(script))
            continue
        if kind in SKIPPED_CONTROLS:
            continue
        nested = [_table(control)] if kind == "tbl " else _nested_text(control)
        if not nested:
            continue
        if _inline(control):
            flush()
            blocks.extend(nested)
        else:
            floating.extend(nested)
    flush()
    return blocks + floating


def _inline(control: Record) -> bool:
    """개체 공통 속성 첫 비트: 글자처럼 취급."""
    return len(control.payload) >= 8 and bool(struct.unpack_from("<I", control.payload, 4)[0] & 1)


@dataclass
class Document:
    blocks: list
    equations: int = 0
    toc: list[tuple[str, int]] = field(default_factory=list)  # 차례(제목, 쪽): 쪽 계산 검증용

    def text(self) -> str:
        return "\n".join(block_text(block) for block in self.blocks)


def _count_equations(records: list[Record]) -> int:
    total = 0
    for record in records:
        if record.tag == TAG_CTRL_HEADER and ctrl_id(record.payload) == "eqed":
            total += 1
        total += _count_equations(record.children)
    return total


# --- 쪽 번호 ---------------------------------------------------------------------------------------
# HWP5에는 쪽 번호가 저장되지 않는다. 한글이 저장할 때 남긴 줄 배치 정보(PARA_LINE_SEG의 세로 위치)가
# 줄어들면 새 쪽으로 보고, 여러 쪽에 걸친 표는 칸 안 줄 높이로 넘친 쪽 수를 어림한다. 새 번호(`nwno`)
# 조판 부호로 인쇄 쪽 번호를 맞춘다. 별책 5~9 차례 쪽수와 대조해 검증한다(어림값이라 어긋날 수 있음).

TAG_LINE_SEG = 0x45
TAG_PAGE_DEF = 0x49


def _find(records: list[Record], tag: int):
    for record in records:
        if record.tag == tag:
            yield record
        yield from _find(record.children, tag)


def _lines(paragraph: Record) -> list[tuple[int, int]]:
    out = []
    for child in paragraph.children:
        if child.tag == TAG_LINE_SEG:
            for pos in range(0, len(child.payload) - 35, 36):
                out.append(struct.unpack_from("<ii", child.payload, pos + 4))
    return out


def _object_height(control: Record) -> int:
    """표·그림 높이. 여러 쪽에 걸친 표는 개체 높이에 첫 쪽 몫만 남으므로 칸 높이·칸 안 줄 높이와 견준다."""
    height = struct.unpack_from("<I", control.payload, 20)[0] if len(control.payload) >= 24 else 0
    rows: dict[int, int] = {}
    longest = 0
    for header, paragraphs in _list_groups(control.children):
        if len(header.payload) >= 24:
            _, row, _, row_span = struct.unpack_from("<HHHH", header.payload, 8)
            if row_span == 1:
                rows[row] = max(rows.get(row, 0), struct.unpack_from("<I", header.payload, 20)[0])
        total = 0
        for paragraph in paragraphs:
            for child in paragraph.children:
                if child.tag == TAG_LINE_SEG:
                    for pos in range(0, len(child.payload) - 35, 36):
                        line_height, spacing = struct.unpack_from("<i", child.payload, pos + 8)[0], \
                            struct.unpack_from("<i", child.payload, pos + 20)[0]
                        total += line_height + spacing
        longest = max(longest, total)
    return max(height, sum(rows.values()), longest)


class _PageCounter:
    def __init__(self, body: int):
        self.body = body
        self.page = 1
        self.offset = 0
        self.last_bottom = None
        self.pending: tuple[int, int] | None = None
        self.spilled = False  # 앞 문단의 표·그림이 다음 쪽으로 넘쳤는지
        self.guessed = False  # 바로 앞 쪽 넘김을 세로 위치가 아니라 표 높이로만 정했는지

    def start(self, paragraph: Record) -> int:
        """문단 시작 쪽(인쇄 쪽 번호)."""
        lines = _lines(paragraph)
        controls = [c for c in paragraph.children if c.tag == TAG_CTRL_HEADER]
        self.spilled = False
        if lines:
            top = lines[0][0]
            if self.last_bottom is not None:
                page_break = len(paragraph.payload) > 11 and paragraph.payload[11] & 0x04
                overflow = bool(self.pending) and sum(self.pending) > self.body + 100
                reset = top < self.last_bottom - 100
                if reset and not page_break and not self.pending and self.guessed and top > 1000:
                    # 넘친 표 뒤 문단을 이미 다음 쪽으로 셌는데 그다음 문단이 쪽 중간에서 다시 위로 올라가면
                    # 같은 쪽으로 본다(수학 별책 차례 쪽수·다른 공개 추출본 쪽과 대조해 정한 규칙)
                    pass
                elif page_break or overflow or reset:
                    added = 1
                    if self.pending:
                        added = max(1, round((sum(self.pending) - top) / self.body))
                        self.spilled = sum(self.pending) > self.body + 100
                    self.page += added
                self.guessed = overflow and not reset and not page_break
        for control in controls:
            if ctrl_id(control.payload) == "nwno" and len(control.payload) >= 10:
                self.offset = self.page - struct.unpack_from("<H", control.payload, 8)[0]
        return self.page - self.offset

    def finish(self, paragraph: Record) -> int:
        """문단 끝 쪽(문단 안에서 쪽이 넘어간 만큼)."""
        lines = _lines(paragraph)
        if not lines:
            return self.page - self.offset
        for (upper, _), (lower, _) in zip(lines, lines[1:], strict=False):
            if lower < upper - 100:
                self.page += 1
        objects = [c for c in paragraph.children
                   if c.tag == TAG_CTRL_HEADER and ctrl_id(c.payload) in ("tbl ", "gso ")]
        self.pending = (lines[0][0], sum(_object_height(c) for c in objects)) if objects else None
        self.last_bottom = lines[-1][0] + lines[-1][1]
        return self.page - self.offset


def read_hwp(path: Path) -> Document:
    """HWP5 파일 본문을 문단·표 블록 열로 읽는다."""
    cfb = CompoundFile(Path(path).read_bytes())
    header = cfb.stream("FileHeader")
    if not header.startswith(b"HWP Document File"):
        raise Hwp5Error("HWP5 머리가 아님")
    properties = struct.unpack_from("<I", header, 36)[0]
    if properties & 0x2 or properties & 0x4:
        raise Hwp5Error("암호화·배포용 문서는 읽지 않음")
    compressed = bool(properties & 0x1)
    sections = sorted((name for name in cfb.order if re.fullmatch(r"Section\d+", name)), key=lambda n: int(n[7:]))
    blocks: list = []
    equations = 0
    toc: list[tuple[str, int]] = []
    counter = None
    previous_objects: list = []
    for name in sections:
        raw = cfb.stream(name)
        if compressed:
            raw = zlib.decompress(raw, -15)
        records = parse_records(raw)
        equations += _count_equations(records)
        page_def = next(_find(records, TAG_PAGE_DEF), None)
        if counter is None and page_def is not None and len(page_def.payload) >= 32:
            _, height, _, _, top, bottom, head, foot = struct.unpack_from("<8I", page_def.payload, 0)
            counter = _PageCounter(height - top - bottom - head - foot)
        for record in records:
            if record.tag != TAG_PARA_HEADER:
                continue
            start = counter.start(record) if counter else None
            if counter and counter.spilled:
                for block in previous_objects:
                    block.page_end = max(block.page_end or start, start)
            produced = _paragraph_blocks(record)
            end = counter.finish(record) if counter else None
            previous_objects = [block for block in produced if isinstance(block, Table)] or (
                previous_objects if not _lines(record) else [])
            for block in produced:
                block.page, block.page_end = start, end
                if isinstance(block, Paragraph):
                    match = re.fullmatch(r"(\S.*?)\t+(\d{1,3})", block.text)
                    if match:
                        toc.append((match[1].strip(), int(match[2])))
            blocks.extend(produced)
    return Document(blocks, equations, toc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HWP5 본문을 글로 뽑는다(표는 칸을 ' | '로 잇는다).")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    document = read_hwp(args.source)
    args.output.write_text(document.text() + "\n", encoding="utf-8")
    tables = sum(isinstance(block, Table) for block in document.blocks)
    print(f"{args.source.name}: blocks={len(document.blocks)} tables={tables} equations={document.equations}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
