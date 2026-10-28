"""기록 조회 도구: learning /internal/records/... (FN-AGT-04, API 4.1, learning-service.yaml).

- 도구는 학생·기간을 LLM에게 받지 않고 그래프 상태의 확인된 scope만 씀
- 호출마다 사용자 컨텍스트의 허용 학생인지 다시 확인 (FN-AGT-02)
- 조회 실패를 빈 기록으로 바꾸지 않음 (FN-AGT-10): RecordsUnavailable로 올려 error 이벤트
- 질문 하나의 조회들은 HTTP 연결 하나를 같이 씀 (router가 끝나면 aclose)
"""

from datetime import date
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from app.analysis_agent.models import (
    Metric,
    RecordAttempt,
    RecordChange,
    Scope,
    ThinkingActivity,
    ThinkingTypeItem,
)
from app.clients.base import internal_client
from app.errors import ApiError
from app.security import UserContext

PAGE_SIZE = 100  # 1.1 목록 최대 크기
MAX_PAGES = 50  # 응답 이상으로 끝없이 읽지 않게 막는 상한
RECORD_COUNT_LABEL = "학습한 활동"  # learning summary의 집계 대상 시도 수 지표


class RecordsUnavailable(Exception):
    def __init__(self, code: str, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class LearningRecords(Protocol):
    async def summary(self, scope: Scope) -> list[Metric]: ...

    async def thinking_types(self, scope: Scope) -> list[ThinkingTypeItem]: ...

    async def recent_attempts(self, scope: Scope, limit: int) -> list[RecordAttempt]: ...

    async def changes(self, scope: Scope) -> list[RecordChange]: ...

    async def thinking_activities(self, scope: Scope) -> list[ThinkingActivity]: ...

    async def aclose(self) -> None: ...


class HttpLearningRecords:
    def __init__(self, base_url: str, user: UserContext) -> None:
        self._base_url = base_url
        self._user = user
        self._client: httpx.AsyncClient | None = None

    async def summary(self, scope: Scope) -> list[Metric]:
        body = await self._get(scope, "summary", {})
        metrics = _parse(Metric, body.get("metrics"))
        if not any(metric.label == RECORD_COUNT_LABEL for metric in metrics):
            raise RecordsUnavailable("RECORDS_INVALID", retryable=False)
        return metrics

    async def thinking_types(self, scope: Scope) -> list[ThinkingTypeItem]:
        body = await self._get(scope, "thinking-types", {})
        return _parse(ThinkingTypeItem, body.get("items"))

    async def recent_attempts(self, scope: Scope, limit: int) -> list[RecordAttempt]:
        """최근 답변 순 첫 페이지만. 아이가 쓴 생각은 최근 몇 개만 보여 주므로 전체를 읽지 않음."""
        body = await self._get(scope, "attempts", {"page": 0, "size": limit})
        return _parse(RecordAttempt, body.get("items"))

    async def changes(self, scope: Scope) -> list[RecordChange]:
        # 전후 변화 비율의 분모라 모든 페이지를 읽음
        items: list[Any] = []
        for page in range(MAX_PAGES):
            body = await self._get(scope, "changes", {"page": page, "size": PAGE_SIZE})
            batch = body.get("items")
            if not isinstance(batch, list):
                raise RecordsUnavailable("RECORDS_INVALID", retryable=False)
            items.extend(batch)
            if not batch or len(items) >= int(body.get("totalElements", 0)):
                return _parse(RecordChange, items)
        raise RecordsUnavailable("RECORDS_INVALID", retryable=False)

    async def thinking_activities(self, scope: Scope) -> list[ThinkingActivity]:
        body = await self._get(scope, "thinking-activities", {})
        return _parse(ThinkingActivity, body.get("items"))

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, scope: Scope, resource: str, params: dict[str, Any]) -> dict[str, Any]:
        # 도구 실행마다 권한 재확인 (FN-AGT-02)
        try:
            self._user.require_student(scope.student_id)
        except ApiError as exc:
            raise RecordsUnavailable("FORBIDDEN", retryable=False) from exc
        if self._client is None:
            self._client = internal_client(self._base_url)
        path = f"/internal/records/students/{scope.student_id}/{resource}"
        query = {"from": scope.from_.isoformat(), "to": scope.to.isoformat(), **params}
        try:
            response = await self._client.get(path, params=query, headers=self._user.to_headers())
        except httpx.HTTPError as exc:
            raise RecordsUnavailable("RECORDS_UNAVAILABLE", retryable=True) from exc
        if response.status_code >= 500:
            raise RecordsUnavailable("RECORDS_UNAVAILABLE", retryable=True)
        if response.status_code == 403:
            raise RecordsUnavailable("FORBIDDEN", retryable=False)
        if response.status_code != 200:
            raise RecordsUnavailable("RECORDS_UNAVAILABLE", retryable=False)
        try:
            body = response.json()
        except ValueError as exc:
            raise RecordsUnavailable("RECORDS_INVALID", retryable=False) from exc
        _check_body(body, scope)
        return body


def _check_body(body: Any, scope: Scope) -> None:
    """요청한 학생·기간의 확정 결과인지 확인. 처리 중·실패는 사용하지 않음."""
    if not isinstance(body, dict):
        raise RecordsUnavailable("RECORDS_INVALID", retryable=False)
    if body.get("state") in ("PROCESSING", "FAILED"):
        raise RecordsUnavailable("RECORDS_NOT_READY", retryable=True)
    period = body.get("period")
    if (
        body.get("studentId") != scope.student_id
        or not isinstance(period, dict)
        or _date(period.get("from")) != scope.from_
        or _date(period.get("to")) != scope.to
    ):
        raise RecordsUnavailable("RECORDS_INVALID", retryable=False)


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _parse[M: BaseModel](model: type[M], items: Any) -> list[M]:
    if not isinstance(items, list):
        raise RecordsUnavailable("RECORDS_INVALID", retryable=False)
    try:
        return [model.model_validate(item) for item in items]
    except ValidationError as exc:
        raise RecordsUnavailable("RECORDS_INVALID", retryable=False) from exc
