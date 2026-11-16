"""scoring /internal/m2/scores·/internal/m1/checks 호출 (api-spec 4.3, #69).

- 인증·사용자 컨텍스트 헤더는 internal_client가 붙임, 재시도 없음 (아키텍처 1.3)
- 요청마다 남은 판정 시간으로 timeout을 정함 (api-spec 4.2.2)
- {active:false}만 비활성(None). 장애·계약 밖 응답을 비활성으로 바꾸지 않음
"""

from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.judgment.models import M2Preparation, ModelIdentity

NARRATIVE_ITEMS = frozenset(
    (
        "hol",
        "task_1",
        "content_1",
        "content_2",
        "content_3",
        "organization_1",
        "organization_2",
        "expression_1",
        "expression_2",
    )
)
ESSAY_ITEMS = frozenset(("org", "cont", "exp"))


class ScoringUnavailable(Exception):
    def __init__(self, retryable: bool) -> None:
        super().__init__("SCORING_UNAVAILABLE")
        self.retryable = retryable


class M2Scores(BaseModel):
    model_config = ConfigDict(extra="ignore")

    active: Literal[True]
    inputType: Literal["NARRATIVE", "ESSAY"]
    scores: dict[str, int] | None = None
    rawScores: dict[str, float] | None = None
    scored: bool = True
    reason: Literal["TEXT_TOO_SHORT"] | None = None
    preparation: M2Preparation | None = None
    model: ModelIdentity

    @model_validator(mode="after")
    def known_items(self):
        if not self.scored:
            if (
                self.reason != "TEXT_TOO_SHORT"
                or self.preparation is None
                or self.scores is not None
                or self.rawScores is not None
            ):
                raise ValueError("invalid scoreless response")
            return self
        if self.scores is None or self.rawScores is None or self.reason is not None:
            raise ValueError("scored response requires scores")
        items = NARRATIVE_ITEMS if self.inputType == "NARRATIVE" else ESSAY_ITEMS
        if set(self.scores) != items or set(self.rawScores) != items:
            raise ValueError("scores keys do not match inputType")
        return self


class M1Check(BaseModel):
    """활성 M1 응답의 ai 기대 형식. scoring M1 활성화 때 확정 (api-spec 4.2.2)."""

    model_config = ConfigDict(extra="ignore")

    active: Literal[True]
    confidence: float = Field(ge=0, le=1)
    model: ModelIdentity


class ScoringClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def m2_scores(self, body: dict[str, Any], timeout: float) -> M2Scores | None:
        return await self._post("/internal/m2/scores", body, timeout, M2Scores)

    async def m1_check(self, body: dict[str, Any], timeout: float) -> M1Check | None:
        return await self._post("/internal/m1/checks", body, timeout, M1Check)

    async def _post[M: BaseModel](
        self, path: str, body: dict[str, Any], timeout: float, model: type[M]
    ) -> M | None:
        try:
            response = await self._client.post(path, json=body, timeout=timeout)
        except httpx.HTTPError as exc:
            raise ScoringUnavailable(retryable=True) from exc
        if response.status_code >= 500:
            raise ScoringUnavailable(retryable=True)
        if response.status_code != 200:
            raise ScoringUnavailable(retryable=False)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ScoringUnavailable(retryable=False) from exc
        if payload == {"active": False}:
            return None
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise ScoringUnavailable(retryable=False) from exc
