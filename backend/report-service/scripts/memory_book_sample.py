"""추억 그림책 시험 PDF 만들기 (docs/proposals/memory-book.md 14장 1단계).

서비스 연결 없이 고정 데이터로 PDF·HTML을 만든다. 데이터는 모두 지어낸 값이다.

    uv run python -m scripts.memory_book_sample --out build/memory-book
    uv run python -m scripts.memory_book_sample --book my-round.json --out build/real

`--book` JSON은 learning 회차 조립 응답 초안(제안 7.2) 모양이다. 그림 칸에는 `data:` URI 외에
로컬 그림 파일 경로(.png·.jpg·.jpeg·.webp)를 넣을 수 있다. kind MinIO에서 받은 실제 테마 그림으로
결과를 볼 때 쓴다. 실제 서비스에서는 report가 learning의 presigned URL로 받아 data URI로 바꾼다.
"""

import argparse
import base64
import json
import struct
import zlib
from pathlib import Path

from app.rendering.renderer import ReportRenderer

TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
IMAGE_FIELDS = ("introImage", "sceneImage", "outroImage")


def placeholder_png(width: int, height: int, top: tuple, bottom: tuple) -> bytes:
    """위→아래 두 색 그러데이션 PNG(외부 라이브러리 없이)."""
    rows = []
    for y in range(height):
        t = y / max(height - 1, 1)
        pixel = bytes(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True))
        rows.append(b"\x00" + pixel * width)

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


def data_uri(png: bytes, content_type="image/png") -> str:
    return f"data:{content_type};base64,{base64.b64encode(png).decode()}"


def scene(top, bottom) -> str:
    return data_uri(placeholder_png(320, 200, top, bottom))


def sample_book(ending_seen=True) -> dict:
    """지어낸 회차: 엔딩 본 회차, 목요일은 문제가 바뀐 날(시도 없음).

    판정 결과도 지어낸 값이다. 월요일이 다시 생각 → 부분으로 올라 "가장 많이 자란 날"이 된다(#1024).
    """
    return {
        "themeId": "00000000-0000-0000-0000-0000000000a1",
        "weekStart": "2026-11-09",
        "title": "사라진 등대 불빛",
        "intro": "바닷가 마을의 등대 불빛이 어느 밤 갑자기 꺼졌어요.\n"
        "마을 사람들은 저마다 다른 까닭을 이야기해요. 누구 말이 맞을까요?",
        "introImage": scene((255, 214, 153), (120, 170, 220)),
        "bigQuestion": "등대 불빛은 왜 꺼졌을까?",
        "days": [
            {
                "day": "MON",
                "title": "등대지기의 일지",
                "thinkingType": "ANALYZE",
                "question": "일지에 적힌 세 가지 사실을 시간 순서대로 정리해 보세요.",
                "sceneImage": scene((200, 220, 240), (90, 120, 170)),
                "dialogue": [{"speaker": "등대지기", "text": "어젯밤엔 바람이 유난히 셌단다."}],
                "attempt": {
                    "answers": [
                        {
                            "version": 1,
                            "text": "먼저 바람이 불었고, 그다음 문이 열렸어요.",
                            "followup": None,
                            "result": "RETHINK",
                        },
                        {
                            "version": 2,
                            "text": "문이 열린 다음에 불이 꺼졌어요. 바람이 들어와서요.",
                            "followup": {
                                "type": "ONE_STEP_MORE",
                                "question": "불이 꺼진 건 언제였을까?",
                            },
                            "result": "PARTIAL",
                        },
                    ],
                    "reflection": {
                        "difficulty": "NORMAL",
                        "text": "순서를 다시 보니 까닭이 보였어요.",
                    },
                },
            },
            {
                "day": "TUE",
                "title": "누구 말이 더 믿을 만할까",
                "thinkingType": "EVALUATE",
                "question": "어부와 빵집 주인의 말 중 어느 쪽이 더 믿을 만한지 "
                "까닭과 함께 써 보세요.",
                "sceneImage": scene((250, 230, 200), (200, 150, 110)),
                "dialogue": [],
                "attempt": {
                    "answers": [
                        {
                            "version": 1,
                            "text": "어부 말이요. 직접 봤다고 했으니까요.",
                            "followup": None,
                            "result": "CORRECT",
                        }
                    ],
                    "reflection": None,
                },
            },
            {
                "day": "WED",
                "title": "새 등대 설계",
                "thinkingType": "CREATE",
                "question": "바람이 세도 꺼지지 않는 등대를 그림 대신 글로 설명해 보세요.",
                "sceneImage": scene((220, 245, 220), (120, 180, 140)),
                "dialogue": [],
                "attempt": {
                    "answers": [
                        {
                            "version": 1,
                            "text": "유리 벽을 두 겹으로 만들어요. <바람막이>도 달아요!",
                            "followup": None,
                            "result": "HELD",
                        }
                    ],
                    "reflection": {"difficulty": "EASY", "text": None},
                },
            },
            {
                "day": "THU",
                "title": "기름이 모자라요",
                "thinkingType": "SOLVE",
                "question": "남은 기름으로 며칠 밤을 밝힐 수 있는지 풀이 과정을 써 보세요.",
                "sceneImage": None,
                "dialogue": [],
                "attempt": None,
            },
            {
                "day": "FRI",
                "title": "큰 질문의 답 고르기",
                "thinkingType": "REFLECT",
                "question": "지금까지 얻은 단서로 등대 불빛이 꺼진 까닭을 골라 보세요.",
                "sceneImage": scene((210, 200, 240), (110, 90, 160)),
                "dialogue": [{"speaker": "고양이 나비", "text": "야옹, 단서는 다 모였어."}],
                "attempt": {
                    "answers": [
                        {
                            "version": 1,
                            "text": "바람에 문이 열려서 불이 꺼졌어요.",
                            "followup": None,
                            "result": "CORRECT",
                        }
                    ],
                    "reflection": None,
                },
            },
        ],
        "ending": {
            "seen": ending_seen,
            "outro": "등대지기는 문에 새 빗장을 달았어요. "
            "그날 밤부터 불빛은 다시 바다를 비췄답니다.",
            "answer": "세찬 바람에 등대 문이 열려 불이 꺼졌다",
            "outroImage": scene((255, 236, 170), (240, 150, 90)),
        },
    }


def with_local_images(book: dict, base: Path) -> dict:
    """그림 칸의 로컬 파일 경로를 data URI로 바꾼다(시험 스크립트 전용)."""

    def convert(value):
        if not isinstance(value, str) or value.startswith("data:"):
            return value
        path = (base / value).resolve()
        if path.suffix.lower() not in TYPES or not path.is_file():
            raise SystemExit(f"그림 파일을 찾을 수 없거나 형식이 아님: {value}")
        return data_uri(path.read_bytes(), TYPES[path.suffix.lower()])

    book = json.loads(json.dumps(book))
    book["introImage"] = convert(book.get("introImage"))
    for day in book["days"]:
        day["sceneImage"] = convert(day.get("sceneImage"))
    if book.get("ending"):
        book["ending"]["outroImage"] = convert(book["ending"].get("outroImage"))
    return book


def main() -> None:
    parser = argparse.ArgumentParser(description="추억 그림책 시험 PDF")
    parser.add_argument("--book", type=Path, help="회차 JSON(없으면 지어낸 표본)")
    parser.add_argument("--name", default="합성학생", help="표지 별명")
    parser.add_argument("--before-ending", action="store_true", help="표본을 엔딩 전 회차로")
    parser.add_argument(
        "--out", type=Path, default=Path("build/memory-book"), help="출력 파일 이름(확장자 없이)"
    )
    args = parser.parse_args()
    if args.book:
        book = with_local_images(
            json.loads(args.book.read_text(encoding="utf-8")), args.book.parent
        )
    else:
        book = sample_book(ending_seen=not args.before_ending)
    files = ReportRenderer().render_memory_book(book, args.name)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for kind, body in files.items():
        path = args.out.with_suffix("." + kind.lower())
        path.write_bytes(body)
        print(f"{kind}: {path} ({len(body):,} bytes)")


if __name__ == "__main__":
    main()
