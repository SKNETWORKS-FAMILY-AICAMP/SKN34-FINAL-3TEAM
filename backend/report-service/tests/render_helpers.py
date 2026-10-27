"""Fixed, invented data only; also used for visual PDF quality checks."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from app.generation.metrics import MetricsCalculator
from app.generation.models import ItemType, ReportStatus, WeeklyReport
from app.generation.presentation import from_result
from app.generation.records import ReflectionRecord
from tests.record_helpers import PERIOD, attempt_for, instant, records_for


def fixed_result(student=None):
    student = student or UUID(int=2)
    attempt = attempt_for(
        student,
        texts=("나는 나무가 좋아요.", "왜냐하면 그늘을 만들기 때문이에요."),
        status="COMPLETED",
    )
    attempt = replace(
        attempt, reflection=ReflectionRecord("NORMAL", "까닭을 더 적었어요.", instant())
    )
    result = MetricsCalculator().calculate(records_for(student, [attempt]))
    result = replace(
        result,
        items=tuple(
            replace(item, verified=True, payload={**item.payload, "verified": True})
            if item.type == ItemType.QUOTE
            else item
            for item in result.items
        ),
    )
    result = replace(
        result,
        generated_at=datetime(2026, 10, 26, 7, tzinfo=UTC),
        narrative={
            "text": "답변 제출 시도 1건이 확인되었습니다.",
            "source": "LLM",
            "modelExplanation": None,
        },
        evening_question="어떤 까닭을 더 떠올렸니?",
        versions={"prompt": "synthetic@1", "model": "test@1"},
        verification={"numbersMatched": True, "quotesMatched": True, "contentAllowed": True},
    )
    report = WeeklyReport(
        UUID(int=1), UUID(int=3), student, PERIOD.start, PERIOD.end, 1, ReportStatus.RUNNING, None
    )
    return report, result


def fixed_detail():
    report, result = fixed_result()
    return from_result(report, result)
