"""추억 그림책 렌더링 (docs/proposals/memory-book.md 14장 1단계). 데이터는 모두 지어낸 값."""

import copy
import io
import re

import pytest
from markupsafe import escape
from pypdf import PdfReader

from app.rendering.memory_book import (
    evening_question,
    memory_book_view,
    most_grown_day,
    safe_image,
    week_label,
)
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
    # 표지 쪽에 목차·이야기의 시작까지, 그 뒤는 한 장면씩 새 쪽
    assert len(pages) == 8
    assert "합성학생의생각이자란한주" in pages[0] and "사라진등대불빛" in pages[0]
    assert "이야기의시작" in pages[0] and "월요일" in pages[0]  # 목차
    text = "".join(pages[1:])
    order = [
        "월요일",
        "화요일",
        "수요일",
        "목요일",
        "금요일",
        "이야기의끝",
        "이번주저녁질문",
    ]
    positions = [text.index(word) for word in order]
    assert positions == sorted(positions)
    assert "이날문제는그뒤에새문제로바뀌어서,아이가그때쓴답을함께싣지못했어요" in text
    assert "큰질문의답" in text


@pytest.mark.parametrize("ending_seen", [True, False])
def test_cover_toc_page_numbers_match_pdf_pages(ending_seen):
    book = sample_book(ending_seen=ending_seen)
    view = memory_book_view(book)
    pdf = ReportRenderer().render_memory_book(book, "합성학생")["PDF"]
    pages = [compact(p.extract_text()) for p in PdfReader(io.BytesIO(pdf)).pages]
    for item in view["toc"]:
        assert f"{compact(item['title'])}{item['page']}" in pages[0], item
    labels = [item["title"] for item in view["toc"]]
    assert ("이야기의 끝" in labels) is ending_seen
    for item in view["toc"]:
        head = compact(item["title"])
        assert head in pages[item["page"] - 1], item
    assert view["toc"][-1]["page"] == len(pages)
    # 쪽 수는 #1024 전과 같다(엔딩 본 회차 8쪽, 엔딩 전 7쪽). 표지는 한 쪽
    assert len(pages) == (8 if ending_seen else 7)
    assert "이렇게같이읽어요" in pages[0] and "★" in pages[0]
    assert "이번주가장많이자란생각" in pages[1]  # 표본은 월요일(2쪽)이 가장 많이 자란 날
    assert "이번주가장많이자란생각" not in "".join(pages[2:])


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
        "뭉치가 낸 오늘의 질문",
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


# ---------------------------------------------------------------- 같이 읽기 보강 (#1024)


def grown_day(code, *results, attempt=True):
    answers = [
        {"version": index + 1, "text": f"답 {index + 1}", "followup": None, "result": result}
        for index, result in enumerate(results)
    ]
    return {"day": code, "attempt": {"answers": answers} if attempt else None}


@pytest.mark.parametrize(
    "days,expected",
    [
        # 오른 날 없음: 그대로·답 하나뿐
        ([grown_day("MON", "PARTIAL", "PARTIAL"), grown_day("TUE", "RETHINK")], None),
        # 동점이면 앞 요일
        (
            [grown_day("WED", "RETHINK", "PARTIAL"), grown_day("TUE", "PARTIAL", "CORRECT")],
            "TUE",
        ),
        # 더 많이 오른 날이 앞 요일보다 먼저
        (
            [grown_day("MON", "RETHINK", "PARTIAL"), grown_day("THU", "RETHINK", "CORRECT")],
            "THU",
        ),
        # 보류·판정 없음은 처음이든 마지막이든 제외
        (
            [
                grown_day("MON", "RETHINK", "HELD"),
                grown_day("TUE", "HELD", "CORRECT"),
                grown_day("WED", None, "CORRECT"),
                grown_day("THU", "RETHINK", None),
            ],
            None,
        ),
        ([grown_day("MON", "RETHINK", "HELD"), grown_day("FRI", "RETHINK", "PARTIAL")], "FRI"),
        # 문제가 바뀐 날(시도 없음)·답 하나뿐인 날은 후보 아님
        ([grown_day("MON", attempt=False), grown_day("TUE", "CORRECT")], None),
        # 내려간 날은 제외
        ([grown_day("MON", "CORRECT", "PARTIAL")], None),
        # 처음 답과 마지막 답만 본다(가운데 값은 상관없음)
        ([grown_day("MON", "RETHINK", "CORRECT", "RETHINK")], None),
        ([grown_day("MON", "PARTIAL", "RETHINK", "CORRECT")], "MON"),
    ],
)
def test_most_grown_day_rule(days, expected):
    assert most_grown_day(days) == expected


def test_most_grown_day_reads_answers_in_version_order():
    day = grown_day("MON", "RETHINK", "CORRECT")
    day["attempt"]["answers"].reverse()
    assert most_grown_day([day]) == "MON"


def day_html(html, code, following):
    end = html.index(f'data-day="{following}"') if following else html.index("scene-block ending")
    return html[html.index(f'data-day="{code}"') : end]


def test_day_groups_first_then_mungchi_then_revised_thinking():
    html = html_of(sample_book())
    monday = day_html(html, "MON", "TUE")
    order = [
        "뭉치가 낸 오늘의 질문",
        'class="steps"',
        "처음엔 이렇게 생각했어요",
        "먼저 바람이 불었고",
        "그때 뭉치가 물었어요",
        "불이 꺼진 건 언제였을까?",
        "그래서 다시 생각했어요",
        "문이 열린 다음에",
        "돌아보기",
    ]
    positions = [monday.index(word) for word in order]
    assert positions == sorted(positions)
    # 돌아보기는 단계 카드 목록 밖(아래)
    assert monday.index('</ol><p class="reflection"><b>돌아보기') > monday.index("문이 열린 다음에")


def test_day_without_followup_has_first_thinking_only():
    tuesday = day_html(html_of(sample_book()), "TUE", "WED")
    assert tuesday.count("처음엔 이렇게 생각했어요") == 1
    assert "다시 생각" not in tuesday and "뭉치가 물었어요" not in tuesday


def test_answer_without_followup_after_first_is_still_revised_thinking():
    book = sample_book()
    book["days"][1]["attempt"]["answers"].append(
        {"version": 2, "text": "빵집 주인 말도 들어 봐야 해요.", "followup": None}
    )
    tuesday = day_html(html_of(book), "TUE", "WED")
    assert tuesday.index("처음엔 이렇게 생각했어요") < tuesday.index("그래서 다시 생각했어요")
    assert "뭉치가 물었어요" not in tuesday


def test_changed_question_day_keeps_notice_without_group():
    thursday = day_html(html_of(sample_book()), "THU", "FRI")
    assert "이 날 문제는 그 뒤에 새 문제로 바뀌어서" in thursday
    assert 'class="steps"' not in thursday and "처음엔 이렇게" not in thursday


def test_highlight_marks_one_day_page_and_its_toc_line():
    book = sample_book()
    view = memory_book_view(book)
    assert [d["day"] for d in view["days"] if d["highlight"]] == ["MON"]
    assert [t["title"] for t in view["toc"] if t["highlight"]] == ["등대지기의 일지"]
    html = html_of(book)
    assert html.count("이번 주 가장 많이 자란 생각") == 1
    assert html.count(' highlight"') == 1 and 'day highlight" data-day="MON"' in html
    assert html.count('class="toc-star"') == 1


def test_no_highlight_when_no_day_grew():
    book = sample_book()
    for day in book["days"]:
        for answer in (day["attempt"] or {}).get("answers", []):
            answer["result"] = None
    html = html_of(book)
    assert "가장 많이 자란 생각" not in html and "★" not in html


def test_judgment_results_never_reach_the_book():
    book = sample_book()
    view = memory_book_view(book)
    assert "result" not in repr(view)
    html = html_of(book)
    for word in ("CORRECT", "PARTIAL", "RETHINK", "HELD", "맞음", "부분", "다시 생각해"):
        assert word not in html, word


def test_cover_subtitle_and_reading_guide_use_nickname():
    html = html_of(sample_book(), name="합성학생")
    assert "합성학생의 생각이 자란 한 주" in html and "의 추억 그림책" not in html
    guide = [
        "합성학생에게 소리 내어 읽어 달라고 해 주세요.",
        '답을 고치지 말고 "왜 그렇게 생각했어?"만 물어봐 주세요.',
        "마지막 쪽 질문에 가족이 함께 답해 보세요.",
    ]
    positions = [html.index(line) for line in guide]
    assert positions == sorted(positions)


@pytest.mark.parametrize("ending_seen", [True, False])
def test_last_page_is_this_week_question_with_family_answer_lines(ending_seen):
    book = sample_book(ending_seen=ending_seen)
    view = memory_book_view(book)
    assert view["toc"][-1] | {"page": 0} == {
        "label": "함께",
        "title": "이번 주 저녁 질문",
        "page": 0,
        "highlight": False,
    }
    html = html_of(book)
    assert "오늘 저녁 질문" not in html
    closing = html[html.index('<section class="closing') :]
    assert "<h2>이번 주 저녁 질문</h2>" in closing
    assert evening_question(book["bigQuestion"]) in closing
    assert closing.count('class="family-row"') == 3
    assert "함께 이야기한 날 ____년 __월 __일" in closing


# ---------------------------------------------------------------- 디자인 개편 (#1047)


def answer(version, text, followup=None):
    return {
        "version": version,
        "text": text,
        "followup": {"type": "ONE_STEP_MORE", "question": followup} if followup else None,
    }


FIRST, ASKED, ASKED_AGAIN = (
    "처음엔 이렇게 생각했어요",
    "그때 뭉치가 물었어요",
    "뭉치가 한 번 더 물었어요",
)
REVISED, REVISED_AGAIN = "그래서 다시 생각했어요", "그래서 또 생각했어요"


@pytest.mark.parametrize(
    "answers,expected",
    [
        # 답 1개
        ([answer(1, "답 1")], [("child", FIRST)]),
        # 되묻기 1번
        (
            [answer(1, "답 1"), answer(2, "답 2", "물음 1")],
            [("child", FIRST), ("mungchi", ASKED), ("child", REVISED)],
        ),
        # 되묻기 2번, 그 뒤 되묻기 없이 한 번 더
        (
            [
                answer(1, "답 1"),
                answer(2, "답 2", "물음 1"),
                answer(3, "답 3", "물음 2"),
                answer(4, "답 4"),
            ],
            [
                ("child", FIRST),
                ("mungchi", ASKED),
                ("child", REVISED),
                ("mungchi", ASKED_AGAIN),
                ("child", REVISED_AGAIN),
                ("child", REVISED_AGAIN),
            ],
        ),
        # 되묻기 없이 다시 낸 답도 다시 낸 답 차례로 센다
        ([answer(1, "답 1"), answer(2, "답 2")], [("child", FIRST), ("child", REVISED)]),
        (
            [answer(1, "답 1"), answer(2, "답 2"), answer(3, "답 3", "물음 1")],
            [("child", FIRST), ("child", REVISED), ("mungchi", ASKED), ("child", REVISED_AGAIN)],
        ),
    ],
)
def test_step_leads_are_fixed_and_numbered_from_one(answers, expected):
    book = sample_book()
    book["days"][0]["attempt"]["answers"] = list(reversed(answers))  # 버전 순서로 다시 놓임
    steps = memory_book_view(book)["days"][0]["attempt"]["steps"]
    assert [(step["kind"], step["lead"]) for step in steps] == expected
    assert [step["number"] for step in steps] == list(range(1, len(steps) + 1))
    assert [step["text"] for step in steps if step["kind"] == "child"] == [
        a["text"] for a in answers
    ]


def test_step_numbers_run_on_in_the_page():
    book = sample_book()
    book["days"][0]["attempt"]["answers"].append(answer(3, "답 3", "물음 2"))
    html = html_of(book)
    numbers = re.findall(r'class="step-no">(\d+)<', day_html(html, "MON", "TUE"))
    assert numbers == ["1", "2", "3", "4", "5"]
    assert re.findall(r'class="step-no">(\d+)<', day_html(html, "TUE", "WED")) == ["1"]


def test_wide_page_only_for_one_card_day_or_changed_question_day():
    book = sample_book()
    book["days"][1]["attempt"]["answers"].append(answer(2, "빵집 주인 말도 들어 봐야 해요."))
    expected = {"MON": False, "TUE": False, "WED": True, "THU": True, "FRI": True}
    assert {d["day"]: d["wide"] for d in memory_book_view(book)["days"]} == expected
    classes = dict(
        (day, value.split())
        for value, day in re.findall(r'<section class="([^"]*)" data-day="(\w+)"', html_of(book))
    )
    assert {day: "wide" in value for day, value in classes.items()} == expected


def test_most_grown_day_has_one_pill_on_top_of_its_cards_and_no_gold_border():
    html = html_of(sample_book())
    assert html.count('class="grown"') == 1
    monday = day_html(html, "MON", "TUE")
    side = monday[monday.index('class="side"') :]
    assert side.index('class="grown"') < side.index('class="steps"')
    # 장식 별은 그림(SVG)이라 "★" 글자는 목차 1곳뿐
    assert html.count("★") == 1 and "★" not in monday
    for gold in ("#c98a2e", "#f3d28a", "box-shadow"):
        assert gold not in html, gold


def test_child_answers_are_not_quoted_but_dialogue_is():
    book = sample_book()
    html = html_of(book)
    texts = [a["text"] for d in book["days"] for a in (d["attempt"] or {}).get("answers", [])]
    assert texts
    for text in texts:
        escaped = str(escape(text))
        assert f">{escaped}<" in html
        for mark in ("“", "&#34;", "‘", "「"):
            assert f"{mark}{escaped}" not in html
    assert "“어젯밤엔 바람이 유난히 셌단다.”" in html and "— 등대지기" in html


def test_pictures_keep_their_whole_shape():
    html = html_of(sample_book())
    # 표지·요일 4(목요일은 그림 없음)·끝·저녁 질문(표지 그림 다시 씀)
    assert html.count('<img class="art"') == 7
    fits = re.findall(r"object-fit:\s*([\w-]+)", html)
    assert fits and set(fits) == {"contain"}


def test_ending_without_answer_has_no_cloud_and_only_left_side():
    book = sample_book()
    book["ending"]["answer"] = None
    html = html_of(book)
    ending = html[html.index("scene-block ending") : html.index('<section class="closing')]
    assert book["ending"]["outro"] in ending and " solo" in ending
    assert "큰 질문의 답은" not in ending and 'class="side"' not in ending


def test_pdf_embeds_gowun_dodum_subset_only_in_the_book(rendered):
    reader = PdfReader(io.BytesIO(rendered["PDF"]))
    fonts = {
        str(font.get_object()["/BaseFont"])
        for page in reader.pages
        for font in (page["/Resources"].get("/Font") or {}).values()
    }
    assert any(name.endswith("+GowunDodum-Regular") for name in fonts), fonts
    assert b"@font-face" in rendered["HTML"]
    assert "@font-face" not in html_of(sample_book())  # 글꼴 값 없이도 템플릿은 돈다
