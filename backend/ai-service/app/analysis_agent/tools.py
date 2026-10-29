"""분석 에이전트 기록 조회 도구 (FN-AGT-02·04, class-diagram 5.2 RecordTools).

- 도구는 학생·기간을 LLM에게 받지 않고 그래프 상태의 확인된 scope만 씀
- 호출마다 사용자 컨텍스트의 허용 학생인지 다시 확인, 범위 밖이면 learning을 부르지 않음
"""

from app.analysis_agent.calculators import RECORD_COUNT_LABEL
from app.analysis_agent.models import (
    Metric,
    RecordAttempt,
    RecordChange,
    RecordEvidence,
    Scope,
    ThinkingActivity,
    ThinkingTypeItem,
)
from app.clients.learning_client import LearningClient, RecordsUnavailable
from app.errors import ApiError
from app.security import UserContext


class RecordTools:
    def __init__(self, client: LearningClient, user: UserContext) -> None:
        self._client = client
        self._user = user

    async def summary(self, scope: Scope) -> list[Metric]:
        self._require(scope)
        metrics = await self._client.summary(scope)
        # 기록 수는 모든 답변·기록 부족 안내의 기준이라 없으면 쓰지 않음
        if not any(metric.label == RECORD_COUNT_LABEL for metric in metrics):
            raise RecordsUnavailable("RECORDS_INVALID", retryable=False)
        return metrics

    async def thinking_types(self, scope: Scope) -> list[ThinkingTypeItem]:
        self._require(scope)
        return await self._client.thinking_types(scope)

    async def attempts(self, scope: Scope, size: int) -> list[RecordAttempt]:
        self._require(scope)
        return await self._client.attempts(scope, size)

    async def changes(self, scope: Scope) -> list[RecordChange]:
        self._require(scope)
        return await self._client.changes(scope)

    async def thinking_activities(self, scope: Scope) -> list[ThinkingActivity]:
        self._require(scope)
        return await self._client.thinking_activities(scope)

    async def evidence(self, scope: Scope, answer_ids: list[str]) -> list[RecordEvidence]:
        """답변별 학생 범위는 learning이 다시 확인 (범위 밖 답변이면 403)."""
        self._require(scope)
        return await self._client.evidence(answer_ids)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _require(self, scope: Scope) -> None:
        # 도구 실행마다 권한 재확인 (FN-AGT-02)
        try:
            self._user.require_student(scope.student_id)
        except ApiError as exc:
            raise RecordsUnavailable("FORBIDDEN", retryable=False) from exc
