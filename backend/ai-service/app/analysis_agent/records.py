"""기록 조회 도구: learning /internal/records/... (FN-AGT-04, API 4.1).

- 도구는 학생·기간을 LLM에게 받지 않고 그래프 상태의 확인된 scope만 씀
- 호출마다 사용자 컨텍스트의 허용 학생인지 다시 확인 (FN-AGT-02)
- 조회 실패를 빈 기록으로 바꾸지 않음 (FN-AGT-10): RecordsUnavailable로 올려 error 이벤트
"""

from datetime import date
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from app.analysis_agent.models import (
    RecordAttempt,
    RecordChange,
    Scope,
    ThinkingTypeItem,
)
from app.clients.base import internal_client
from app.errors import ApiError
from app.security import UserContext

PAGE_SIZE = 100  # 1.1 목록 최대 크기, 모든 페이지를 읽음
MAX_PAGES = 50  # 응답 이상으로 끝없이 읽지 않게 막는 상한


class RecordsUnavailable(Exception):
    def __init__(self, code: str, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class LearningRecords(Protocol):
    async def attempts(self, scope: Scope) -> list[RecordAttempt]: ...

    async def thinking_types(self, scope: Scope) -> list[ThinkingTypeItem]: ...

    async def changes(self, scope: Scope) -> list[RecordChange]: ...


class HttpLearningRecords:
    def __init__(self, base_url: str, user: UserContext) -> None:
        self._base_url = base_url
        self._user = user

    async def attempts(self, scope: Scope) -> list[RecordAttempt]:
        items = await self._pages(scope, "attempts")
        return _parse_list(RecordAttempt, items)

    async def thinking_types(self, scope: Scope) -> list[ThinkingTypeItem]:
        body = await self._get(scope, "thinking-types", {})
        return _parse_list(ThinkingTypeItem, body.get("items"))

    async def changes(self, scope: Scope) -> list[RecordChange]:
        items = await self._pages(scope, "changes")
        return _parse_list(RecordChange, items)

    async def _pages(self, scope: Scope, resource: str) -> list[Any]:
        items: list[Any] = []
        for page in range(MAX_PAGES):
            body = await self._get(scope, resource, {"page": page, "size": PAGE_SIZE})
            batch = body.get("items")
            if not isinstance(batch, list):
                raise RecordsUnavailable("RECORDS_INVALID", retryable=False)
            items.extend(batch)
            if len(items) >= int(body.get("totalElements", 0)) or not batch:
                return items
        raise RecordsUnavailable("RECORDS_INVALID", retryable=False)

    async def _get(self, scope: Scope, resource: str, params: dict[str, Any]) -> dict[str, Any]:
        # 도구 실행마다 권한 재확인 (FN-AGT-02)
        try:
            self._user.require_student(scope.student_id)
        except ApiError as exc:
            raise RecordsUnavailable("FORBIDDEN", retryable=False) from exc
        path = f"/internal/records/students/{scope.student_id}/{resource}"
        query = {"from": scope.from_.isoformat(), "to": scope.to.isoformat(), **params}
        try:
            async with internal_client(self._base_url) as client:
                response = await client.get(path, params=query, headers=self._user.to_headers())
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
    """요청한 학생·기간의 확정 결과인지 확인. 처리 중·실패는 사용하지 않음 (4.1.1)."""
    if not isinstance(body, dict):
        raise RecordsUnavailable("RECORDS_INVALID", retryable=False)
    if body.get("state") in ("PROCESSING", "FAILED"):
        raise RecordsUnavailable("RECORDS_NOT_READY", retryable=True)
    child = body.get("childId")
    if child is not None and child != scope.student_id:
        raise RecordsUnavailable("RECORDS_INVALID", retryable=False)
    period = body.get("period")
    if isinstance(period, dict) and (
        _date(period.get("from")) != scope.from_ or _date(period.get("to")) != scope.to
    ):
        raise RecordsUnavailable("RECORDS_INVALID", retryable=False)


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _parse_list[M: RecordAttempt | RecordChange | ThinkingTypeItem](
    model: type[M], items: Any
) -> list[M]:
    if not isinstance(items, list):
        raise RecordsUnavailable("RECORDS_INVALID", retryable=False)
    try:
        return [model.model_validate(item) for item in items]
    except ValidationError as exc:
        raise RecordsUnavailable("RECORDS_INVALID", retryable=False) from exc
