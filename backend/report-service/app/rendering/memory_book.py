"""추억 그림책 화면 값 (docs/proposals/memory-book.md 11.2).

learning 회차 조립 응답(제안 7.2)에서 그림을 `data:` URI로 바꾼 값을 받아 템플릿 값으로 만든다.
렌더러는 네트워크를 막으므로 그림은 허용한 형식의 `data:` URI만 남기고
나머지는 "그림 없음"으로 둔다.
엔딩을 보지 않은 회차는 종료 이야기·정답·종료 그림을 템플릿에 넘기지 않는다(P23).
"""

import base64
import re
from datetime import date, timedelta
from functools import cache
from pathlib import Path

DAY_LABELS = {"MON": "월요일", "TUE": "화요일", "WED": "수요일", "THU": "목요일", "FRI": "금요일"}
EVENING_TITLE = "이번 주 저녁 질문"
IMAGE_URI = re.compile(r"data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}")


TITLE_FONT = Path(__file__).parent / "fonts" / "GowunDodum-Regular.subset.ttf"


@cache
def title_font_uri() -> str:
    """제목·이야기 글꼴(고운돋움 부분 집합, OFL 1.1)을 `data:` URI로(#1047).

    렌더러가 모든 요청을 막아서 파일 URL로는 읽히지 않는다. 한 번 읽어 둔다.
    """
    encoded = base64.b64encode(TITLE_FONT.read_bytes()).decode("ascii")
    return f"data:font/ttf;base64,{encoded}"


def safe_image(value) -> str | None:
    """허용한 래스터 형식의 base64 `data:` URI만 통과. 외부 URL·SVG·형식 오류는 None."""
    if isinstance(value, str) and IMAGE_URI.fullmatch(value):
        return value
    return None


def week_label(week_start: str) -> str:
    start = date.fromisoformat(week_start)
    if start.weekday() != 0:
        raise ValueError("weekStart must be a Monday")
    end = start + timedelta(days=5)  # 토요일까지 풀 수 있음(P23)
    return f"{start.year}년 {start.month}월 {start.day}일 ~ {end.month}월 {end.day}일"


def evening_question(big_question: str | None) -> str:
    """D9 권장안: 새 LLM 호출 없이 큰 질문으로 만든 고정 문장."""
    if big_question and big_question.strip():
        return (
            f"이번 주 큰 질문은 「{big_question.strip()}」였어요. 우리 가족이라면 어떻게 답할까요?"
        )
    return "이번 주 이야기에서 가장 기억에 남는 장면은 무엇인가요?"


# 판정 순위(#1024): 다시 생각 < 부분 < 맞음. 보류(HELD)·판정 없음(None)은 순위 없음
GROWTH_RANK = {"RETHINK": 0, "PARTIAL": 1, "CORRECT": 2}


def most_grown_day(days: list[dict]) -> str | None:
    """이번 주 가장 많이 자란 날(요일 코드). 없으면 None.

    그 날 처음 답과 마지막 답이 둘 다 순위가 있을 때만 후보이고, 오름 = 마지막 − 처음.
    오름이 0보다 큰 날 중 가장 큰 날 하나, 같으면 앞 요일(월 → 금).
    답이 하나뿐인 날·문제가 바뀌어 시도가 없는 날은 후보가 아니다.
    판정 결과는 고르는 데만 쓰고 책에는 싣지 않는다.
    """
    best, best_rise = None, 0
    for day in sorted(days, key=lambda d: list(DAY_LABELS).index(d["day"])):
        answers = sorted(
            (day.get("attempt") or {}).get("answers") or [], key=lambda a: a["version"]
        )
        if len(answers) < 2:
            continue
        first = GROWTH_RANK.get(answers[0].get("result"))
        last = GROWTH_RANK.get(answers[-1].get("result"))
        if first is None or last is None:
            continue
        if last - first > best_rise:
            best, best_rise = day["day"], last - first
    return best


# 요일 쪽 단계 카드 연결 문구(#1047). 별명은 넣지 않는다
FIRST_LEAD = "처음엔 이렇게 생각했어요"
FOLLOWUP_LEADS = ("그때 뭉치가 물었어요", "뭉치가 한 번 더 물었어요")
REVISED_LEADS = ("그래서 다시 생각했어요", "그래서 또 생각했어요")


def _attempt(attempt: dict | None) -> dict | None:
    """요일 쪽 오른쪽 칸 값: 답과 되묻기를 차례대로 단계 카드로. 판정 결과는 넘기지 않는다.

    되묻기는 그 다음 답 앞에 온다. 번호는 카드 순서대로 1부터, 되묻기 없이 다시 낸 답도
    다시 낸 답 차례로 센다. 아이 답 글은 그대로 넘긴다(따옴표·줄이기 없음).
    """
    if attempt is None:
        return None
    steps = []
    followups = revised = 0
    for index, answer in enumerate(
        sorted(attempt.get("answers") or [], key=lambda a: a["version"])
    ):
        question = (answer.get("followup") or {}).get("question")
        if question:
            steps.append(
                {"kind": "mungchi", "lead": FOLLOWUP_LEADS[min(followups, 1)], "text": question}
            )
            followups += 1
        if index == 0:
            lead = FIRST_LEAD
        else:
            lead = REVISED_LEADS[min(revised, 1)]
            revised += 1
        steps.append({"kind": "child", "lead": lead, "text": answer.get("text") or ""})
    for number, step in enumerate(steps, start=1):
        step["number"] = number
    reflection = attempt.get("reflection") or {}
    return {"steps": steps, "reflection": reflection.get("text") or None}


def memory_book_view(book: dict) -> dict:
    """템플릿 값. 입력을 바꾸지 않는다."""
    ending = book.get("ending") or {}
    seen = ending.get("seen") is True
    grown = most_grown_day(book["days"])
    days = []
    for day in sorted(book["days"], key=lambda d: list(DAY_LABELS).index(d["day"])):
        attempt = _attempt(day.get("attempt"))
        days.append(
            {
                "day": day["day"],
                "dayLabel": DAY_LABELS[day["day"]],
                "title": day.get("title") or "",
                "thinkingType": day["thinkingType"],
                "question": day.get("question") or "",
                "sceneImage": safe_image(day.get("sceneImage")),
                "dialogue": [
                    {"speaker": line.get("speaker") or "", "text": line.get("text") or ""}
                    for line in day.get("dialogue") or []
                ],
                "attempt": attempt,
                # 넓은 쪽(#1047): 오른쪽 칸에 카드 1개뿐인 날·안내 문장뿐인 날(문제가 바뀜)
                "wide": attempt is None or len(attempt["steps"]) <= 1,
                "highlight": day["day"] == grown,
            }
        )
    # 목차: 표지가 1쪽, 요일·끝·저녁 질문은 각자 새 쪽에서 시작한다(템플릿 break-before).
    # 엔딩 전이면 끝 쪽 없이 안내 한 줄과 저녁 질문이 한 쪽에 들어간다.
    toc = [
        {
            "label": day["dayLabel"],
            "title": day["title"],
            "page": 2 + index,
            "highlight": day["highlight"],
        }
        for index, day in enumerate(days)
    ]
    next_page = 2 + len(days)
    if seen:
        toc.append({"label": "끝", "title": "이야기의 끝", "page": next_page, "highlight": False})
        next_page += 1
    toc.append({"label": "함께", "title": EVENING_TITLE, "page": next_page, "highlight": False})
    return {
        "toc": toc,
        "title": book["title"],
        "weekLabel": week_label(book["weekStart"]),
        "intro": book.get("intro") or "",
        "introImage": safe_image(book.get("introImage")),
        "bigQuestion": book.get("bigQuestion") or None,
        "days": days,
        "ending": {
            "seen": seen,
            "outro": (ending.get("outro") or "") if seen else None,
            "answer": ending.get("answer") if seen else None,
            "outroImage": safe_image(ending.get("outroImage")) if seen else None,
        },
        "eveningTitle": EVENING_TITLE,
        "eveningQuestion": evening_question(book.get("bigQuestion")),
    }
