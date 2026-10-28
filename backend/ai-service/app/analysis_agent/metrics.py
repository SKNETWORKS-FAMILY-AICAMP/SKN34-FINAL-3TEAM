"""질문 유형별 수치·원문 고르기 (FN-AGT-05, P08). LLM은 숫자를 만들지 않고 여기 값만 문장으로 옮김.

집계 대상·기간·건수·비율은 learning이 P08로 계산해 줌 (summary·thinking-types·changes.counts).
대시보드·리포트와 숫자가 어긋나지 않도록 ai는 그 값을 그대로 쓰고, learning 값을 세는 지표만 더함.
"""

from collections import Counter
from dataclasses import dataclass, field

from app.analysis_agent.models import (
    Evidence,
    Intent,
    Metric,
    Period,
    QueryState,
    RecordAttempt,
    Records,
    Scope,
)
from app.analysis_agent.records import RECORD_COUNT_LABEL

MIN_RATIO_DENOMINATOR = 5
COMPLETED_LABEL = "완료한 활동"
REVISED_LABEL = "되묻기 후 생각을 더한 활동"
THINKING_TYPE_LABELS = {
    "ANALYZE": "분석하기",
    "EVALUATE": "따져 보기",
    "CREATE": "새로 만들기",
    "SOLVE": "문제 해결하기",
    "REFLECT": "돌아보기",
}
DIFFICULTY_LABELS = {"EASY": "쉬웠어", "NORMAL": "보통", "HARD": "어려웠어"}
THOUGHT_LIMIT = 8  # 아이가 쓴 생각 원문 후보 최대 개수 (최근 답변 순)
CHANGE_RULE = "되묻기 후 다시 쓴 시도 수"


@dataclass(frozen=True)
class Source:
    """대조·인용에 쓰는 원문 하나. evidence.quote는 원문 전체(인용 시 잘라 씀)."""

    evidence: Evidence
    text: str


@dataclass
class Computation:
    metrics: list[Metric]
    sources: list[Source]
    record_count: int
    insufficient: str | None = None  # NO_RECORD·NO_CHANGES·NO_REFLECTIONS
    extra_numbers: set[str] = field(default_factory=set)  # 답변에 써도 되는 기간 날짜 숫자


def compute(intent: Intent, records: Records, scope: Scope) -> Computation:
    period = Period.model_validate({"from": scope.from_, "to": scope.to})
    summary = {metric.label: metric for metric in records.summary}
    total = summary[RECORD_COUNT_LABEL]
    metrics = [total]
    sources: list[Source] = []
    insufficient = "NO_RECORD" if total.count == 0 else None
    titles = {a.attempt_id: a.mission_title for a in records.activities or []}

    if intent == "COUNT":
        metrics = list(records.summary)
    elif intent == "THINKING_TYPES":
        for item in records.thinking_types or []:
            if item.missions:
                label = THINKING_TYPE_LABELS.get(item.type, item.type)
                formula = f"{label} 유형 시도 수"
                metrics.append(count_metric(f"{label} 활동", len(item.missions), formula, period))
    elif intent == "CHILD_THOUGHTS":
        latest = (_latest_answer(attempt) for attempt in records.attempts or [])
        sources = [source for source in latest if source is not None]
    elif intent == "CHANGES":
        changes = records.changes or []
        grew = {
            "글자 수가 늘어난 시도": sum(c.counts.chars[1] > c.counts.chars[0] for c in changes),
            "문장 수가 늘어난 시도": sum(
                c.counts.sentences[1] > c.counts.sentences[0] for c in changes
            ),
            "까닭을 잇는 말이 늘어난 시도": sum(
                c.counts.reason_connectives[1] > c.counts.reason_connectives[0] for c in changes
            ),
        }
        if REVISED_LABEL in summary:
            metrics.append(summary[REVISED_LABEL])
        metrics += [
            ratio_metric(label, count, len(changes), f"{label} 수 / {CHANGE_RULE}", period)
            for label, count in grew.items()
        ]
        sources = [
            _source(
                change.attempt_id, titles.get(change.attempt_id, ""), answer.answer_id, answer.text
            )
            for change in changes
            for answer in (change.first, change.revised)
        ]
        if total.count and not changes:
            insufficient = "NO_CHANGES"
    elif intent == "REFLECTIONS":
        written = [a for a in records.activities or [] if a.reflection is not None]
        if COMPLETED_LABEL in summary:
            metrics.append(summary[COMPLETED_LABEL])
        metrics.append(
            count_metric("돌아보기를 쓴 활동", len(written), "기간 안에 쓴 돌아보기 수", period)
        )
        difficulty = Counter(a.reflection.difficulty for a in written if a.reflection)
        for code, label in DIFFICULTY_LABELS.items():
            if difficulty[code]:
                formula = "난이도별 돌아보기 수"
                metrics.append(
                    count_metric(f"난이도 {label} 돌아보기", difficulty[code], formula, period)
                )
        sources = [
            _source(a.attempt_id, a.mission_title, None, a.reflection.text)
            for a in written
            if a.reflection and a.reflection.text
        ]
        if total.count and not written:
            insufficient = "NO_REFLECTIONS"

    extra = {
        str(part) for day in (scope.from_, scope.to) for part in (day.month, day.day, day.year)
    }
    return Computation(metrics, sources, total.count, insufficient, extra)


def count_metric(label: str, count: int, formula: str, period: Period) -> Metric:
    """learning Metric.count와 같은 규칙: value null, 분자·분모 = 건수."""
    return Metric(
        label=label,
        value=None,
        count=count,
        numerator=count,
        denominator=count,
        formula=formula,
        period=period,
        state=_state(count),
    )


def ratio_metric(
    label: str, numerator: int, denominator: int, formula: str, period: Period
) -> Metric:
    """learning Metric.ratio와 같은 규칙: 분모 5 미만이면 value null."""
    return Metric(
        label=label,
        value=numerator / denominator if denominator >= MIN_RATIO_DENOMINATOR else None,
        count=numerator,
        numerator=numerator,
        denominator=denominator,
        formula=formula,
        period=period,
        state=_state(denominator),
    )


def _state(n: int) -> QueryState:
    if n == 0:
        return "NO_RECORD"
    return "INSUFFICIENT_SAMPLE" if n < MIN_RATIO_DENOMINATOR else "OK"


def _latest_answer(attempt: RecordAttempt) -> Source | None:
    if not attempt.answers:
        return None
    answer = max(attempt.answers, key=lambda a: a.version)
    if not answer.text.strip():
        return None
    source = _source(attempt.attempt_id, attempt.mission.title, answer.answer_id, answer.text)
    update = {"answer_version": answer.version, "submitted_at": answer.submitted_at}
    return Source(source.evidence.model_copy(update=update), source.text)


def _source(attempt_id: str, mission_title: str, answer_id: str | None, text: str) -> Source:
    evidence = Evidence(
        attempt_id=attempt_id,
        mission_title=mission_title,
        answer_id=answer_id,
        answer_version=None,
        submitted_at=None,
        quote=text,
    )
    return Source(evidence, text)
