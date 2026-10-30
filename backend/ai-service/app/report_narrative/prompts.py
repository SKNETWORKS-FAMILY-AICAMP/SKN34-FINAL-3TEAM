"""리포트 서술·저녁 질문 프롬프트. 문구를 바꾸면 PROMPT_VERSION을 올림 (NFR-DAT-02).

LLM에는 report가 계산한 수치·기록만 전달, 학생 이름·ID와 기록 ID는 넣지 않음 (NFR-SEC-03).
인용은 후보 번호와 원문 구절로 고르게 하고, 서비스가 구절이 후보 원문에 있는지 확인.
규칙은 report ReportVerifier가 통과로 보는 범위(숫자·인용·금지 표현)에 맞춤.
"""

from pydantic import BaseModel

from app.report_narrative.models import (
    Change,
    Metric,
    NarrativeRequest,
    Reflection,
    ThinkingTypeSummary,
)

PROMPT_VERSION = "report@1"

TYPE_LABEL = {
    "ANALYZE": "분석하기",
    "EVALUATE": "따져 보기",
    "CREATE": "새로 만들기",
    "SOLVE": "문제 해결하기",
    "REFLECT": "돌아보기",
}  # API 명세서 1.5 코드값
DIFFICULTY_LABEL = {"EASY": "쉬웠어", "NORMAL": "보통", "HARD": "어려웠어"}

SYSTEM = """\
너는 초등학생의 한 주 생각 기록을 학부모에게 전하는 주간 리포트 서술과 "이번 주 저녁 질문"을 쓴다.

서술 규칙
- 학부모에게 해요체로 3~5문장, 600자 이내로 쓴다. 아이는 "아이"라고 부른다.
- 숫자는 "수치"와 "되묻기 전후 변화"에 있는 값만 아라비아 숫자 그대로 쓴다.
  새로 계산하거나 더하거나 빼거나 추정하지 않는다.
- "한 번", "두 개", "세 문장"처럼 한글로 수를 쓰지 않는다.
- 미션 제목·아이 답에 들어 있는 숫자는 따옴표 인용 밖에서 쓰지 않는다.
- 비율이 없는 수치(표본 5 미만)는 비율로 말하지 않고 개수만 말한다.
- 적은 기록을 능력 부족으로 해석하지 않는다.
- 기록이 없는 생각 유형은 "확인된 기록 없음"으로만 말하고 내용을 짐작하지 않는다.
- 되묻기 전후 변화는 센 값(글자 수·문장 수·까닭을 잇는 말 수)만 말한다.
- 생각이 깊어졌다, 사고력이 늘었다처럼 단정하지 않는다.
- "점수", "등급", "레벨", "순위"라는 낱말과 또래 비교를 어떤 뜻으로도 쓰지 않는다.
- 쓰지 않은 미션 돌아보기 글은 "쓰지 않음"으로만 말하고 내용을 대신 쓰거나 짐작하지 않는다.
- 큰따옴표는 아이 말을 옮길 때만 쓴다. 옮길 때는 "인용 후보" 한 개에서 이어진 구절을
  글자·띄어쓰기·문장부호 그대로 잘라 큰따옴표 안에 넣는다. 후보에 없는 말은 인용하지 않는다.
- 옮긴 구절마다 cited_quotes에 후보 번호(candidate)와 큰따옴표 안 구절(quote)을 똑같이 넣는다.

저녁 질문 규칙
- 학부모가 저녁에 아이에게 그대로 읽어 줄 질문 하나를 친근한 반말 한 문장으로 쓴다.
- 이번 주 실제 미션이나 아이가 쓴 생각에서 출발하고, 한 번에 한 가지만 묻는다.
- 정답·평가·능력을 암시하지 않고, 아이가 자기 생각을 편하게 말하도록 묻는다.
- 숫자·따옴표·금지 낱말 규칙은 서술과 같다.
"""


class CitedQuote(BaseModel):
    candidate: int  # 인용 후보 번호 (1부터)
    quote: str  # 서술 큰따옴표 안 구절, 후보 원문의 일부


class GeneratedNarrative(BaseModel):
    narrative: str
    evening_question: str
    cited_quotes: list[CitedQuote]


def metric_line(metric: Metric) -> str:
    ratio = f", 비율 {round(metric.value * 100)}%" if metric.value is not None else ""
    return (
        f"- {metric.label}: {metric.numerator}/{metric.denominator}, 개수 {metric.count}{ratio}"
        f" (계산식: {metric.formula})"
    )


def thinking_type_line(item: ThinkingTypeSummary) -> str:
    if item.state == "NO_RECORD":
        return f"- {TYPE_LABEL[item.type]}: 확인된 기록 없음"
    titles = ", ".join(mission.title for mission in item.missions) or "미션 이름 없음"
    return f"- {TYPE_LABEL[item.type]}: {titles}"


def change_lines(change: Change) -> list[str]:
    counts = change.counts
    return [
        f"- 받은 질문: {change.followup or '없음'}",
        f"  처음 답: {change.first.text}",
        f"  마지막 답: {change.revised.text}",
        f"  글자 수 {counts.chars}, 문장 수 {counts.sentences},"
        f" 까닭을 잇는 말 수 {counts.reason_connectives}",
    ]


def reflection_line(reflection: Reflection) -> str:
    if not reflection.written:
        return "- 쓰지 않음"
    difficulty = DIFFICULTY_LABEL.get(reflection.difficulty or "", reflection.difficulty)
    return f"- 어려움 {difficulty or '-'}: {reflection.text or ''}"


def build_user(request: NarrativeRequest) -> str:
    sections = {
        "수치": [metric_line(metric) for metric in request.metrics],
        "생각 유형별 활동": [thinking_type_line(item) for item in request.thinking_types],
        "되묻기 전후 변화 ([처음, 마지막])": [
            line for change in request.changes for line in change_lines(change)
        ],
        "미션 돌아보기 글": [reflection_line(reflection) for reflection in request.reflections],
        "인용 후보": [f"{n}. {quote.text}" for n, quote in enumerate(request.quotes, 1)],
    }
    lines: list[str] = []
    for title, body in sections.items():
        lines += [f"{title}:", *(body or ["- 없음"]), ""]
    return "\n".join(lines[:-1])
