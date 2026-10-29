"""learning /internal/records/... 호출 (API 4.1, learning-service.yaml).

- 받은 사용자 컨텍스트 헤더를 그대로 전달 (아키텍처 2.3). 권한 판단은 analysis_agent.tools
- 조회 실패를 빈 기록으로 바꾸지 않음 (FN-AGT-10): RecordsUnavailable로 올려 error 이벤트
- 재시도 없음, 타임아웃은 internal_client의 config 값 (아키텍처 1.3)
- 질문 하나의 조회들은 HTTP 연결 하나를 같이 씀 (router가 끝나면 aclose)
"""

from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.analysis_agent.models import (
    Metric,
    RecordAttempt,
    RecordChange,
    RecordEvidence,
    Scope,
    ThinkingActivity,
    ThinkingTypeItem,
)
from app.clients.base import internal_client
from app.security import UserContext

PAGE_SIZE = 100  # 1.1 목록 최대 크기
MAX_PAGES = 50  # 응답 이상으로 끝없이 읽지 않게 막는 상한


class RecordsUnavailable(Exception):
    def __init__(self, code: str, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class LearningClient:
    def __init__(self, base_url: str, user: UserContext) -> None:
        self._base_url = base_url
        self._user = user
        self._client: httpx.AsyncClient | None = None

    async def summary(self, scope: Scope) -> list[Metric]:
        body = await self._get_student(scope, "summary", {})
        return _parse(Metric, body.get("metrics"))

    async def thinking_types(self, scope: Scope) -> list[ThinkingTypeItem]:
        body = await self._get_student(scope, "thinking-types", {})
        return _parse(ThinkingTypeItem, body.get("items"))

    async def attempts(self, scope: Scope, size: int) -> list[RecordAttempt]:
        """최근 답변 순 첫 페이지만. 아이가 쓴 생각은 최근 몇 개만 보여 주므로 전체를 읽지 않음."""
        body = await self._get_student(scope, "attempts", {"page": 0, "size": size})
        return _parse(RecordAttempt, body.get("items"))

    async def changes(self, scope: Scope) -> list[RecordChange]:
        # 전후 변화 비율의 분모라 모든 페이지를 읽음
        items: list[Any] = []
        for page in range(MAX_PAGES):
            body = await self._get_student(scope, "changes", {"page": page, "size": PAGE_SIZE})
            batch = body.get("items")
            if not isinstance(batch, list):
                raise RecordsUnavailable("RECORDS_INVALID", retryable=False)
            items.extend(batch)
            if not batch or len(items) >= int(body.get("totalElements", 0)):
                return _parse(RecordChange, items)
        raise RecordsUnavailable("RECORDS_INVALID", retryable=False)

    async def thinking_activities(self, scope: Scope) -> list[ThinkingActivity]:
        body = await self._get_student(scope, "thinking-activities", {})
        return _parse(ThinkingActivity, body.get("items"))

    async def evidence(self, answer_ids: list[str]) -> list[RecordEvidence]:
        """요청 순서대로. 없는 답변·삭제 학생은 available=false(원문 없음) 그대로 반환."""
        body = await self._get("/internal/records/evidence", {"answerIds": ",".join(answer_ids)})
        return _parse(RecordEvidence, body.get("items"))

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_student(
        self, scope: Scope, resource: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        path = f"/internal/records/students/{scope.student_id}/{resource}"
        query = {"from": scope.from_.isoformat(), "to": scope.to.isoformat(), **params}
        body = await self._get(path, query)
        _check_body(body, scope)
        return body

    async def _get(self, path: str, query: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:
            self._client = internal_client(self._base_url)
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
        if not isinstance(body, dict):
            raise RecordsUnavailable("RECORDS_INVALID", retryable=False)
        return body


def _check_body(body: dict[str, Any], scope: Scope) -> None:
    """요청한 학생·기간의 확정 결과인지 확인. 처리 중·실패는 사용하지 않음."""
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
