"""화면설계서를 참고 양식([모델 배포]화면설계서.pdf)과 같은 배치로 생성한다.

양식: 1920×1080 표지 1장 + 화면마다 1장.
- 오른쪽 위 Confidential / 팀명
- 상단 표: 화면명·요구사항 ID / 화면 경로·화면 ID (진회색 머리 칸)
- 왼쪽: 화면 캡처와 파란 번호 원
- 오른쪽: Description(화면 ID, 번호별 굵은 제목 + 설명) → Check Point(굵은 제목 + 항목)

요구사항 ID는 지어내지 않는다: v1.1의 연계 기능(FN) → 기능 명세서 요구사항 열,
새 화면은 요구사항 대조 데이터에서 확인한 ID만 쓴다.
"""
import argparse
import json
import re
from pathlib import Path

from PIL import Image
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from xml.sax.saxutils import escape

W, H = 1920, 1080
pdfmetrics.registerFont(TTFont("Malgun", "C:/Windows/Fonts/malgun.ttf"))
pdfmetrics.registerFont(TTFont("MalgunBold", "C:/Windows/Fonts/malgunbd.ttf"))
INK, HEAD, LINE, RED, BLUE = map(HexColor, ["#111111", "#595959", "#111111", "#E0201A", "#1630F5"])
BODY = ParagraphStyle("b", fontName="Malgun", fontSize=15, leading=21, textColor=INK, wordWrap="CJK")
BOLD = ParagraphStyle("t", fontName="MalgunBold", fontSize=17, leading=23, textColor=INK, wordWrap="CJK")
TEAM = "SKN34-Final-3Team"
VERIFIED_NEW = {"FFJ-25", "FBF-21", "FBN-12", "FFJ-26", "FFH-15", "FFH-17", "FBF-28", "FFH-18",
                "FFJ-30", "FFJ-31", "FFJ-29", "FBF-26", "FAC-12", "FAR-05", "FBN-21", "FBN-22"}


def top(y):
    """양식 좌표(위에서 아래로)를 PDF 좌표로."""
    return H - y


def para(c, text, style, x, y_top, width):
    p = Paragraph(escape(text), style)
    _, h = p.wrap(width, 2000)
    p.drawOn(c, x, top(y_top) - h)
    return y_top + h


def label(c, s, x, y_top, w, h, size=17, bold=False, color=white, center=True, bg=None):
    if bg is not None:
        c.setFillColor(bg)
        c.rect(x, top(y_top + h), w, h, fill=1, stroke=0)
    c.setStrokeColor(LINE)
    c.setLineWidth(1.2)
    c.rect(x, top(y_top + h), w, h, fill=0, stroke=1)
    c.setFillColor(color)
    c.setFont("MalgunBold" if bold else "Malgun", size)
    if center:
        c.drawCentredString(x + w / 2, top(y_top + h / 2) - size * 0.35, s)
    else:
        c.drawString(x + 14, top(y_top + h / 2) - size * 0.35, s)


def corner(c):
    c.setFont("Malgun", 15)
    c.setFillColor(RED)
    c.drawRightString(1715, top(40), "Confidential")
    c.setFillColor(INK)
    c.drawRightString(1888, top(40), TEAM)


def cover(c, meta, logo):
    c.setFillColor(white)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(INK)
    c.setFont("MalgunBold", 26)
    c.drawString(70, top(90), "사고뭉치")
    c.setFillColor(BLUE)
    c.drawString(70 + pdfmetrics.stringWidth("사고뭉치", "MalgunBold", 26) + 2, top(90), ".")
    c.setFillColor(INK)
    c.setFont("Malgun", 50)
    c.drawString(163, top(310), TEAM)
    c.drawImage(str(logo), 160, top(378), width=46, height=52, mask="auto", preserveAspectRatio=True)
    c.setFont("MalgunBold", 31)
    c.drawString(218, top(362), meta["tagline"])
    c.setFillColor(HexColor("#333333"))
    c.setFont("Malgun", 92)
    c.drawString(158, top(560), "사고뭉치 화면설계서")
    c.setFillColor(INK)
    for i, (k, v) in enumerate([("Date", meta["date"]), ("Writer", meta["writer"]), ("Version", meta["version"])]):
        y = 790 + i * 56
        c.setFont("MalgunBold", 24)
        c.drawString(1438, top(y), k)
        c.setFont("Malgun", 24)
        c.drawString(1593, top(y), v)
    c.showPage()


def draw_image(c, path, markers):
    ax, ay, aw, ah = 33, 180, 1440, 825  # 캡처 영역 (양식 기준)
    img = Image.open(path)
    iw, ih = img.size
    s = min(aw / iw, ah / ih)
    dw, dh = iw * s, ih * s
    px, py = ax + (aw - dw) / 2, ay + (ah - dh) / 2
    c.drawImage(str(path), px, top(py + dh), width=dw, height=dh)
    c.setStrokeColor(HexColor("#d0d0d0"))
    c.setLineWidth(1)
    c.rect(px, top(py + dh), dw, dh, fill=0, stroke=1)
    for m in markers:
        mx, my = px + m["x"] * s, py + m["y"] * s
        c.setFillColor(BLUE)
        c.setStrokeColor(white)
        c.setLineWidth(2)
        c.circle(mx, top(my), 17, fill=1, stroke=1)
        c.setFillColor(white)
        c.setFont("MalgunBold", 18)
        c.drawCentredString(mx, top(my) - 6.5, m["label"])


def screen_page(c, s, page_no):
    c.setFillColor(white)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    corner(c)
    # 상단 표
    x0, wl, wv, wl2, wv2, rh = 33, 239, 983, 240, 390, 48
    rows = [("화면명", s["title"], "요구사항 ID", ", ".join(s["reqs"]) or "-"),
            ("화면 경로", s["path"], "화면 ID", s["id"])]
    for i, (a, b, d, e) in enumerate(rows):
        y = 72 + i * rh
        label(c, a, x0, y, wl, rh, bg=HEAD)
        label(c, b, x0 + wl, y, wv, rh, color=INK, center=False)
        label(c, d, x0 + wl + wv, y, wl2, rh, bg=HEAD)
        size = 17 if len(e) <= 22 else 14 if len(e) <= 30 else 12
        label(c, e, x0 + wl + wv + wl2, y, wv2, rh, size=size, color=INK, center=False)
    # 캡처
    draw_image(c, s["path_file"], s["markers"])
    # 오른쪽 패널
    px, pw, bottom = 1495, 390, 1013
    c.setStrokeColor(LINE)
    c.setLineWidth(1.5)
    c.rect(px, top(bottom), pw, bottom - 168, fill=0, stroke=1)
    label(c, "Description", px, 168, pw, 36, size=17, bg=HEAD)
    label(c, s["id"], px, 204, pw, 48, color=INK, center=False)
    y = 252
    for i, d in enumerate(s["desc"], 1):
        start = y
        yy = para(c, d["title"], BOLD, px + 58, y + 12, pw - 72)
        yy = para(c, "• " + d["text"], BODY, px + 62, yy + 4, pw - 78) + 12
        c.setStrokeColor(LINE)
        c.setLineWidth(1.2)
        c.line(px, top(yy), px + pw, top(yy))
        c.line(px + 42, top(start), px + 42, top(yy))
        c.setFont("Malgun", 17)
        c.setFillColor(INK)
        c.drawCentredString(px + 21, top((start + yy) / 2) - 6, str(i))
        y = yy
    label(c, "Check Point", px, y, pw, 36, size=17, bg=HEAD)
    y += 36
    y = para(c, s["title"], BOLD, px + 14, y + 12, pw - 28)
    for line in s["checks"]:
        y = para(c, "• " + line, BODY, px + 22, y + 6, pw - 36)
    if y > bottom - 6:
        raise ValueError(f"{s['id']}: 오른쪽 패널이 넘칩니다 ({y:.0f} > {bottom})")
    c.setFont("Malgun", 13)
    c.setFillColor(HexColor("#888888"))
    c.drawRightString(1888, top(1052), str(page_no))
    c.bookmarkPage(s["id"])
    c.addOutlineEntry(f"{s['id']} {s['title']}", s["id"], level=0)
    c.showPage()


def requirement_map(spec: Path):
    """기능 명세서 표의 FN ID → 마지막 열(요구사항 ID 목록)."""
    out = {}
    for line in spec.read_text(encoding="utf-8").splitlines():
        if line.startswith("| FN-"):
            cells = [v.strip() for v in line.split("|")]
            out[cells[1]] = [r.strip() for r in cells[-2].split(",") if re.match(r"^F[A-Z]{2}-\d+$", r.strip())]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--spec", required=True, type=Path, help="docs/design/functional-spec.md")
    ap.add_argument("--v11-screens", required=True, type=Path, help="v1.1 screens.json (연계 기능)")
    ap.add_argument("--logo", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    a = ap.parse_args()
    if a.output.exists():
        raise FileExistsError(f"기존 PDF를 덮어쓰지 않습니다: {a.output}")
    meta = json.loads((a.data_dir / "build.json").read_text(encoding="utf-8"))
    screens = json.loads((a.data_dir / "screens.json").read_text(encoding="utf-8"))
    features = {s["key"]: s["features"] for s in json.loads(a.v11_screens.read_text(encoding="utf-8"))}
    reqs = requirement_map(a.spec)
    shots = {}
    for folder in ("run1", "extra"):
        for sh in json.loads((a.data_dir / "captures" / folder / "captures.json").read_text(encoding="utf-8"))["shots"]:
            shots[f"{folder}/{sh['file']}"] = sh
    order = {"C": 0, "S": 1, "P": 2, "A": 3}
    screens.sort(key=lambda s: (order[s["key"][0]], s["id"]))
    for s in screens:
        s["path_file"] = a.data_dir / "captures" / s["capture"]
        if not s["path_file"].is_file():
            raise FileNotFoundError(s["path_file"])
        if s["markers"] is None:
            s["markers"] = shots[s["capture"]]["markers"]
        derived = {r for f in features.get(s["key"], []) for r in reqs.get(f, [])}
        s["reqs"] = sorted(derived | (set(s["reqs"]) & VERIFIED_NEW))
        if len(s["markers"]) != len(s["desc"]):
            raise ValueError(f"{s['id']}: 번호 {len(s['markers'])}개와 설명 {len(s['desc'])}개가 다릅니다")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(a.output), pagesize=(W, H))
    c.setTitle(f"사고뭉치 화면설계서 {meta['version']}")
    c.setAuthor(meta["writer"])
    cover(c, meta, a.logo)
    for i, s in enumerate(screens, 2):
        screen_page(c, s, i)
    c.save()
    print(f"{a.output} · {len(screens) + 1}쪽")
    for s in screens:
        print(s["id"], s["title"], "|", ", ".join(s["reqs"]) or "-")


if __name__ == "__main__":
    main()
