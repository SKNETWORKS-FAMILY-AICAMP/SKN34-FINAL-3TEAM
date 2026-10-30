"""분석 대화 테스트용 learning 기록 (contracts/openapi/learning-service.yaml 형태)."""

from app.analysis_agent.models import (
    Metric,
    RecordAttempt,
    RecordChange,
    Records,
    Scope,
    ThinkingActivity,
    ThinkingTypeItem,
)
from app.clients.learning_client import RecordsUnavailable

STUDENT = "s-1"
PERIOD = {"from": "2026-10-20", "to": "2026-10-26"}
SCOPE = Scope.model_validate({"studentId": STUDENT, **PERIOD})


def metric(label: str, numerator: int, denominator: int, formula: str) -> dict:
    """learning Metric.count·ratio와 같은 규칙."""
    ratio = "/" in formula
    state = "OK" if denominator >= 5 else "NO_RECORD" if denominator == 0 else "INSUFFICIENT_SAMPLE"
    return {
        "label": label,
        "value": numerator / denominator if ratio and denominator >= 5 else None,
        "count": numerator,
        "numerator": numerator,
        "denominator": denominator,
        "formula": formula,
        "period": PERIOD,
        "sourceType": "RECORD",
        "state": state,
    }


def summary(total: int = 3) -> list[dict]:
    return [
        metric("학습한 활동", total, total, "기간 내 답변 제출이 있는 시도 수"),
        metric(
            "완료한 활동", min(total, 1), total, "돌아보기까지 마친 시도 수 / 집계 대상 시도 수"
        ),
        metric(
            "도움 없이 시작한 활동",
            min(total, 2),
            total,
            "최초 답변 전 생각 열기를 열지 않은 시도 수 / 집계 대상 시도 수",
        ),
        metric(
            "되묻기 후 생각을 더한 활동",
            min(total, 1),
            min(total, 2),
            "보완 답변 제출 시도 수 / 되묻기 받은 시도 수",
        ),
    ]


def answer(answer_id: str, version: int, text: str) -> dict:
    return {
        "answerId": answer_id,
        "version": version,
        "submittedAt": f"2026-10-2{version}T19:00:00+09:00",
        "inputType": "NARRATIVE",
        "text": text,
    }


REVISED = "나는 찬성해. 왜냐하면 쉬는 시간이 길면 더 잘 놀 수 있어."
# 최근 답변 순
ATTEMPTS = [
    {
        "attemptId": "t-3",
        "mission": {"title": "개미 길 찾기"},
        "answers": [answer("a-4", 1, "개미는 냄새로 길을 찾아.")],
    },
    {
        "attemptId": "t-2",
        "mission": {"title": "물 증발"},
        "answers": [answer("a-3", 1, "물이 증발해서 줄어든 것 같아요.")],
    },
    {
        "attemptId": "t-1",
        "mission": {"title": "쉬는 시간 토론"},
        "answers": [answer("a-1", 1, "나는 찬성해."), answer("a-2", 2, REVISED)],
        "reflection": {
            "difficulty": "HARD",
            "text": "근거 찾기가 어려웠어",
            "createdAt": "2026-10-22T19:30:00+09:00",
        },
    },
]
THINKING_TYPES = [
    {
        "type": "ANALYZE",
        "state": "OK",
        "missions": [
            {"attemptId": "t-1", "title": "쉬는 시간 토론"},
            {"attemptId": "t-3", "title": "개미 길 찾기"},
        ],
    },
    {"type": "EVALUATE", "state": "NO_RECORD", "missions": []},
    {"type": "SOLVE", "state": "OK", "missions": [{"attemptId": "t-2", "title": "물 증발"}]},
]
CHANGES = [
    {
        "attemptId": "t-1",
        "followup": "왜 찬성하는지 더 말해 줄래?",
        "first": {"answerId": "a-1", "text": "나는 찬성해."},
        "revised": {"answerId": "a-2", "text": REVISED},
        "counts": {"chars": [7, 33], "sentences": [1, 2], "reasonConnectives": [0, 1]},
    }
]
ACTIVITIES = [
    {
        "attemptId": "t-3",
        "thinkingType": "ANALYZE",
        "missionTitle": "개미 길 찾기",
        "reflection": None,
    },
    {"attemptId": "t-2", "thinkingType": "SOLVE", "missionTitle": "물 증발", "reflection": None},
    {
        "attemptId": "t-1",
        "thinkingType": "ANALYZE",
        "missionTitle": "쉬는 시간 토론",
        "reflection": {"difficulty": "HARD", "text": "근거 찾기가 어려웠어"},  # createdAt 없음
    },
]


def records(empty: bool = False) -> Records:
    return Records(
        summary=[Metric.model_validate(m) for m in summary(0 if empty else 3)],
        attempts=[] if empty else [RecordAttempt.model_validate(a) for a in ATTEMPTS],
        thinking_types=[ThinkingTypeItem.model_validate(t) for t in THINKING_TYPES],
        changes=[] if empty else [RecordChange.model_validate(c) for c in CHANGES],
        activities=[] if empty else [ThinkingActivity.model_validate(a) for a in ACTIVITIES],
    )


class FakeRecords:
    """RecordTools 대역. fail에 오류를 넣으면 모든 조회가 실패."""

    def __init__(self, empty: bool = False, fail: RecordsUnavailable | None = None) -> None:
        self._records = records(empty)
        self._fail = fail
        self.calls: list[tuple[str, Scope]] = []
        self.closed = False

    async def summary(self, scope):
        return self._call("summary", scope, self._records.summary)

    async def thinking_types(self, scope):
        return self._call("thinking_types", scope, self._records.thinking_types)

    async def attempts(self, scope, size):
        self.attempts_size = size
        return self._call("attempts", scope, (self._records.attempts or [])[:size])

    async def changes(self, scope):
        return self._call("changes", scope, self._records.changes)

    async def thinking_activities(self, scope):
        return self._call("thinking_activities", scope, self._records.activities)

    async def aclose(self) -> None:
        self.closed = True

    def _call(self, name, scope, value):
        self.calls.append((name, scope))
        if self._fail:
            raise self._fail
        return value
