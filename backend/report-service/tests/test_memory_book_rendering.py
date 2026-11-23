"""추억 그림책 렌더링 (docs/proposals/memory-book.md 14장 1단계). 데이터는 모두 지어낸 값."""

import copy
import io
import re

import pytest
from pypdf import PdfReader

from app.rendering.memory_book import evening_question, memory_book_view, safe_image, week_label
from app.rendering.renderer import ReportRenderer
from scripts.memory_book_sample import sample_book


def html_of(book, name="합성학생"):
    renderer = ReportRenderer()
    return renderer._templates.get_template("memory_book.html").render(
        book=memory_book_view(book), name=name
    )


def compact(text):
    return re.sub(r"\s+", "", text)


@pytest.fixture(scope="module")
def rendered():
    return ReportRenderer().render_memory_book(sample_book(), "합성학생")


def test_pdf_flows_cover_then_story_days_ending_and_evening_question(rendered):
    pages = [compact(p.extract_text()) for p in PdfReader(io.BytesIO(rendered["PDF"])).pages]
    # 표지만 한 쪽, 나머지는 이어지는 흐름(장면 칸은 쪽에 걸쳐 잘리지 않음)
    assert 4 <= len(pages) <= 9
    assert "합성학생의추억그림책" in pages[0] and "사라진등대불빛" in pages[0]
    assert "이야기의시작" not in pages[0]
    text = "".join(pages[1:])
    order = [
        "이야기의시작",
        "월요일",
        "화요일",
        "수요일",
        "목요일",
        "금요일",
        "이야기의끝",
        "오늘저녁질문",
    ]
    positions = [text.index(word) for word in order]
    assert positions == sorted(positions)
    assert "이날문제는나중에바뀌어서남은기록이없어요" in text
    assert "큰질문의답" in text


def test_answers_follow_version_order_with_followup_before_revised_answer():
    book = sample_book()
    book["days"][0]["attempt"]["answers"].reverse()
    html = html_of(book)
    first = html.index("먼저 바람이 불었고")
    followup = html.index("불이 꺼진 건 언제였을까?")
    revised = html.index("문이 열린 다음에 불이 꺼졌어요")
    assert first < followup < revised


def test_before_ending_hides_outro_answer_and_outro_image():
    book = sample_book(ending_seen=False)
    outro_image = book["ending"]["outroImage"]
    html = html_of(book)
    assert "아직 이 이야기의 끝을 보지 못했어요" in html
    assert book["ending"]["outro"] not in html
    assert "세찬 바람에" not in html
    assert outro_image not in html


def test_chat_keeps_long_answers_whole_and_in_conversation_order():
    book = sample_book()
    long = "가" * 120
    book["days"][1]["attempt"]["answers"][0]["text"] = long
    html = html_of(book)
    assert html.count(long) == 1
    monday = html[html.index('data-day="MON"') : html.index('data-day="TUE"')]
    order = [
        "등대지기",
        "오늘의 문제",
        "먼저 바람이 불었고",
        "불이 꺼진 건 언제였을까?",
        "문이 열린 다음에",
        "돌아보기",
    ]
    positions = [monday.index(word) for word in order]
    assert positions == sorted(positions)


def test_view_does_not_mutate_input():
    book = sample_book()
    before = copy.deepcopy(book)
    memory_book_view(book)
    assert book == before


def test_student_text_and_name_are_escaped():
    book = sample_book()
    book["days"][0]["attempt"]["answers"][0]["text"] = (
        '<script>fetch("https://untrusted.invalid")</script>'
    )
    book["days"][1]["dialogue"] = [{"speaker": "<b>", "text": "<img src=x onerror=alert(1)>"}]
    html = html_of(book, name="<img src=x>")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<img src=x" not in html


@pytest.mark.parametrize(
    "value",
    [
        "https://example.invalid/scene.png",
        "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",
        "data:text/html;base64,PGgxPg==",
        'data:image/png;base64,abc" onerror="x',
        "theme-drafts/run/INTRO",
        None,
        123,
    ],
)
def test_only_raster_data_uris_reach_the_template(value):
    assert safe_image(value) is None
    book = sample_book()
    book["introImage"] = value
    book["days"][0]["sceneImage"] = value
    view = memory_book_view(book)
    assert view["introImage"] is None and view["days"][0]["sceneImage"] is None
    assert "art--missing" in html_of(book)


def test_week_label_and_evening_question():
    assert week_label("2026-11-09") == "2026년 11월 9일 ~ 11월 14일"
    with pytest.raises(ValueError):
        week_label("2026-11-10")
    assert "「등대 불빛은 왜 꺼졌을까?」" in evening_question(" 등대 불빛은 왜 꺼졌을까? ")
    assert evening_question(None) == evening_question("  ")


def test_blank_display_name_is_rejected():
    with pytest.raises(ValueError):
        ReportRenderer().render_memory_book(sample_book(), " ")
