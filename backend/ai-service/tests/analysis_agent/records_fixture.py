"""분석 대화 테스트용 learning 기록 (API 4.1.1 구현안 형태)."""

from typing import Any

from app.analysis_agent.models import (
    RecordAttempt,
    RecordChange,
    Records,
    Scope,
    ThinkingTypeItem,
)
from app.analysis_agent.records import RecordsUnavailable

SCOPE = Scope.model_validate({"studentId": "s-1", "from": "2026-10-20", "to": "2026-10-26"})


def answer(answer_id: str, version: int, day: int, text: str, status: str = "DONE") -> dict:
    return {
        "answerId": answer_id,
        "version": version,
        "submittedAt": f"2026-10-{day:02d}T19:00:00+09:00",
        "text": text,
        "feedback": {"status": status},
    }


def attempt(attempt_id: str, *answers: dict, **extra: Any) -> dict:
    return {
        "attemptId": attempt_id,
        "mission": {"title": f"미션 {attempt_id}", "thinkingType": extra.pop("type", "ANALYZE")},
        "status": extra.pop("status", "IN_PROGRESS"),
        "answers": list(answers),
        "hintUsages": extra.pop("hints", []),
        **extra,
    }


ATTEMPTS = [
    attempt(
        "t-1",
        answer("a-1", 1, 21, "나는 찬성해."),
        answer("a-2", 2, 21, "나는 찬성해. 왜냐하면 쉬는 시간이 길면 더 잘 놀 수 있어."),
        status="COMPLETED",
        completedAt="2026-10-21T19:30:00+09:00",
        reflection={
            "difficulty": "HARD",
            "text": "근거 찾기가 어려웠어",
            "createdAt": "2026-10-21T19:40:00+09:00",
        },
    ),
    attempt("t-2", answer("a-3", 1, 23, "물이 증발해서 줄어든 것 같아요."), type="SOLVE"),
    attempt(
        "t-3",
        answer("a-4", 1, 24, "개미는 냄새로 길을 찾아."),
        hints=[{"openedAt": "2026-10-24T18:00:00+09:00"}],
    ),
    # 기간 밖 답변만 있는 시도·처리 실패만 있는 시도·삭제 표식은 집계 제외 (P08)
    attempt("t-4", answer("a-5", 1, 10, "기간 밖 답변")),
    attempt("t-5", answer("a-6", 1, 22, "실패한 답변", status="FAILED")),
    {"attemptId": "t-6", "available": False},
]
THINKING_TYPES = [
    {
        "type": "ANALYZE",
        "missions": [
            {"attemptId": "t-1", "title": "미션 t-1"},
            {"attemptId": "t-3", "title": "미션 t-3"},
            {"attemptId": "t-4", "title": "미션 t-4"},
        ],
    },
    {"type": "SOLVE", "missions": [{"attemptId": "t-2", "title": "미션 t-2"}]},
]
CHANGES = [
    {
        "attemptId": "t-1",
        "followup": "왜 찬성하는지 더 말해 줄래?",
        "first": {"answerId": "a-1", "text": "나는 찬성해."},
        "revised": {
            "answerId": "a-2",
            "text": "나는 찬성해. 왜냐하면 쉬는 시간이 길면 더 잘 놀 수 있어.",
        },
    }
]


def records(attempts: list[dict] = ATTEMPTS) -> Records:
    return Records(
        attempts=[RecordAttempt.model_validate(a) for a in attempts],
        thinking_types=[ThinkingTypeItem.model_validate(t) for t in THINKING_TYPES],
        changes=[RecordChange.model_validate(c) for c in CHANGES],
    )


class FakeRecords:
    """learning 기록 조회 대역. fail에 오류를 넣으면 모든 조회가 실패."""

    def __init__(
        self, attempts: list[dict] = ATTEMPTS, fail: RecordsUnavailable | None = None
    ) -> None:
        self._records = records(attempts)
        self._fail = fail
        self.calls: list[tuple[str, Scope]] = []

    async def attempts(self, scope: Scope) -> list[RecordAttempt]:
        return self._call("attempts", scope, self._records.attempts)

    async def thinking_types(self, scope: Scope) -> list[ThinkingTypeItem]:
        return self._call("thinking_types", scope, self._records.thinking_types or [])

    async def changes(self, scope: Scope) -> list[RecordChange]:
        return self._call("changes", scope, self._records.changes or [])

    def _call(self, name: str, scope: Scope, value):
        self.calls.append((name, scope))
        if self._fail:
            raise self._fail
        return value
