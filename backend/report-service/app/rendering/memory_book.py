"""추억 그림책 화면 값 (docs/proposals/memory-book.md, 시험 구현 1단계).

learning 회차 조립 응답(제안 7.2)에서 그림을 `data:` URI로 바꾼 값을 받아 템플릿 값으로 만든다.
렌더러는 네트워크를 막으므로 그림은 허용한 형식의 `data:` URI만 남기고
나머지는 "그림 없음"으로 둔다.
엔딩을 보지 않은 회차는 종료 이야기·정답·종료 그림을 템플릿에 넘기지 않는다(P23).
"""

import re
from datetime import date, timedelta

DAY_LABELS = {"MON": "월요일", "TUE": "화요일", "WED": "수요일", "THU": "목요일", "FRI": "금요일"}
IMAGE_URI = re.compile(r"data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}")


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


def _attempt(attempt: dict | None) -> dict | None:
    if attempt is None:
        return None
    answers = []
    for answer in sorted(attempt.get("answers") or [], key=lambda a: a["version"]):
        followup = answer.get("followup")
        answers.append(
            {
                "text": answer.get("text") or "",
                "followup": (followup or {}).get("question") or None,
            }
        )
    reflection = attempt.get("reflection") or {}
    return {"answers": answers, "reflection": reflection.get("text") or None}


def memory_book_view(book: dict) -> dict:
    """템플릿 값. 입력을 바꾸지 않는다."""
    ending = book.get("ending") or {}
    seen = ending.get("seen") is True
    days = []
    for day in sorted(book["days"], key=lambda d: list(DAY_LABELS).index(d["day"])):
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
                "attempt": _attempt(day.get("attempt")),
            }
        )
    return {
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
        "eveningQuestion": evening_question(book.get("bigQuestion")),
    }
