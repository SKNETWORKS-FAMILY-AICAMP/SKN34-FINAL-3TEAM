"""수치 계산 (FN-AGT-05, P08). LLM은 숫자를 만들지 않고 여기서 계산한 값만 문장으로 옮김.

집계 대상: 기간 안에 답변을 1건 이상 제출한 시도 (완료·미완료 모두).
제외: 처리 실패만 있는 시도·삭제 기록. 분모 5 미만은 비율 대신 개수만.
전후 변화: 시도당 최초 vs 마지막 답변의 글자 수(공백 포함)·문장 수·까닭을 잇는 말.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.analysis_agent.models import (
    Evidence,
    Intent,
    Metric,
    Period,
    QueryState,
    RecordAnswer,
    RecordAttempt,
    Records,
    Scope,
)

KST = timezone(timedelta(hours=9))
MIN_RATIO_DENOMINATOR = 5
CONNECTIVES = ("왜냐하면", "때문", "그래서", "따라서")  # P08 고정 목록 (report와 같음)
SENTENCE_SPLIT = re.compile(r"[.?!\n]")
THINKING_TYPE_LABELS = {
    "ANALYZE": "분석하기",
    "EVALUATE": "따져 보기",
    "CREATE": "새로 만들기",
    "SOLVE": "문제 해결하기",
    "REFLECT": "돌아보기",
}
DIFFICULTY_LABELS = {"EASY": "쉬웠어", "NORMAL": "보통", "HARD": "어려웠어"}
THOUGHT_LIMIT = 8  # 아이가 쓴 생각 원문 후보 최대 개수 (최근 순)

INCLUSION = "기간 안에 답변을 1건 이상 제출한 시도 (처리 실패만 있는 시도·삭제 기록 제외)"


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
    included = included_attempts(records.attempts, scope)
    n = len(included)
    metrics = [_count("집계 대상 시도 수", n, INCLUSION, period)]
    sources: list[Source] = []
    insufficient = "NO_RECORD" if n == 0 else None

    if intent == "COUNT":
        completed = sum(1 for attempt in included if attempt.status == "COMPLETED")
        unaided = sum(1 for attempt in included if _started_unaided(attempt))
        metrics += [
            _count("완료한 시도 수", completed, "집계 대상 중 완료한 시도 수", period),
            _ratio(
                "도움 없이 시작한 비율",
                unaided,
                n,
                "최초 답변 전 도움 열람이 없는 시도 수 / 집계 대상 시도 수",
                period,
            ),
        ]
    elif intent == "THINKING_TYPES":
        ids = {attempt.attempt_id for attempt in included}
        counts: Counter[str] = Counter()
        for item in records.thinking_types or []:
            counts[item.type] += len({m.attempt_id for m in item.missions} & ids)
        for code, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])):
            if count:
                label = THINKING_TYPE_LABELS.get(code, code)
                metrics.append(
                    _count(f"{label} 시도 수", count, f"{label} 유형 집계 대상 시도 수", period)
                )
    elif intent == "CHILD_THOUGHTS":
        latest = [(_last_answer(attempt, scope), attempt) for attempt in included]
        latest.sort(key=lambda pair: pair[0].submitted_at, reverse=True)
        for answer, attempt in latest[:THOUGHT_LIMIT]:
            if answer.text:
                sources.append(_answer_source(attempt, answer))
    elif intent == "CHANGES":
        by_id = {attempt.attempt_id: attempt for attempt in included}
        changes = [c for c in records.changes or [] if c.attempt_id in by_id]
        longer = sentences = connectives = 0
        for change in changes:
            first, revised = change.first.text or "", change.revised.text or ""
            longer += len(revised) > len(first)
            sentences += sentence_count(revised) > sentence_count(first)
            connectives += connective_count(revised) > connective_count(first)
            attempt = by_id[change.attempt_id]
            for ref in (change.first, change.revised):
                answer = _find_answer(attempt, ref.answer_id)
                if answer is not None and answer.text:
                    sources.append(_answer_source(attempt, answer))
        total = len(changes)
        rule = "되묻기 후 다시 쓴 시도 수"
        metrics += [
            _count(rule, total, "집계 대상 중 최초·마지막 답변이 다른 시도 수", period),
            _ratio(
                "글자 수가 늘어난 시도",
                longer,
                total,
                f"글자 수(공백 포함)가 늘어난 시도 / {rule}",
                period,
            ),
            _ratio(
                "문장 수가 늘어난 시도", sentences, total, f"문장 수가 늘어난 시도 / {rule}", period
            ),
            _ratio(
                "까닭을 잇는 말이 늘어난 시도",
                connectives,
                total,
                f"'{'·'.join(CONNECTIVES)}' 개수가 늘어난 시도 / {rule}",
                period,
            ),
        ]
        if n and not total:
            insufficient = "NO_CHANGES"
    elif intent == "REFLECTIONS":
        completed = [attempt for attempt in included if attempt.status == "COMPLETED"]
        written = [attempt for attempt in completed if attempt.reflection is not None]
        metrics.append(
            _ratio(
                "돌아보기를 쓴 시도",
                len(written),
                len(completed),
                "돌아보기를 쓴 시도 수 / 집계 대상 중 완료한 시도 수",
                period,
            )
        )
        difficulty = Counter(
            attempt.reflection.difficulty for attempt in written if attempt.reflection
        )
        for code, label in DIFFICULTY_LABELS.items():
            if difficulty[code]:
                metrics.append(
                    _count(
                        f"난이도 {label} 돌아보기", difficulty[code], "난이도별 돌아보기 수", period
                    )
                )
        for attempt in written:
            if attempt.reflection and attempt.reflection.text:
                sources.append(_reflection_source(attempt))
        if n and not written:
            insufficient = "NO_REFLECTIONS"

    extra = {
        str(part) for day in (scope.from_, scope.to) for part in (day.month, day.day, day.year)
    }
    return Computation(metrics, sources, n, insufficient, extra)


def included_attempts(attempts: list[RecordAttempt], scope: Scope) -> list[RecordAttempt]:
    result = []
    for attempt in attempts:
        if not attempt.available or attempt.mission is None:
            continue
        in_period = [
            a for a in attempt.answers if scope.from_ <= kst_date(a.submitted_at) <= scope.to
        ]
        if not in_period:
            continue
        if all(a.feedback is not None and a.feedback.status == "FAILED" for a in in_period):
            continue
        result.append(attempt)
    return result


def kst_date(value: str) -> date:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=KST)
    return moment.astimezone(KST).date()


def sentence_count(text: str) -> int:
    return sum(1 for part in SENTENCE_SPLIT.split(text) if part.strip())


def connective_count(text: str) -> int:
    return sum(text.count(word) for word in CONNECTIVES)


def _started_unaided(attempt: RecordAttempt) -> bool:
    first = min(attempt.answers, key=lambda a: _moment(a.submitted_at))
    return all(_moment(h.opened_at) >= _moment(first.submitted_at) for h in attempt.hint_usages)


def _last_answer(attempt: RecordAttempt, scope: Scope) -> RecordAnswer:
    in_period = [a for a in attempt.answers if kst_date(a.submitted_at) <= scope.to]
    return max(in_period, key=lambda a: a.version)


def _find_answer(attempt: RecordAttempt, answer_id: str) -> RecordAnswer | None:
    return next((a for a in attempt.answers if a.answer_id == answer_id), None)


def _moment(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=KST)


def _answer_source(attempt: RecordAttempt, answer: RecordAnswer) -> Source:
    text = answer.text or ""
    evidence = Evidence(
        attempt_id=attempt.attempt_id,
        mission_title=attempt.mission.title if attempt.mission else "",
        answer_id=answer.answer_id,
        answer_version=answer.version,
        submitted_at=answer.submitted_at,
        quote=text,
    )
    return Source(evidence, text)


def _reflection_source(attempt: RecordAttempt) -> Source:
    reflection = attempt.reflection
    text = reflection.text if reflection and reflection.text else ""
    evidence = Evidence(
        attempt_id=attempt.attempt_id,
        mission_title=attempt.mission.title if attempt.mission else "",
        answer_id=None,
        answer_version=None,
        submitted_at=reflection.created_at if reflection else None,
        quote=text,
    )
    return Source(evidence, text)


def _count(label: str, count: int, formula: str, period: Period) -> Metric:
    return Metric(
        label=label,
        value=None,
        count=count,
        numerator=None,
        denominator=None,
        formula=formula,
        period=period,
        state="OK" if count else "NO_RECORD",
    )


def _ratio(label: str, numerator: int, denominator: int, formula: str, period: Period) -> Metric:
    state: QueryState = "OK"
    if denominator == 0:
        state = "NO_RECORD"
    elif denominator < MIN_RATIO_DENOMINATOR:
        state = "INSUFFICIENT_SAMPLE"
    return Metric(
        label=label,
        value=round(numerator / denominator, 4) if state == "OK" else None,
        count=numerator,
        numerator=numerator,
        denominator=denominator,
        formula=formula,
        period=period,
        state=state,
    )
