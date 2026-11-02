"""Report-side narrative contract (API 4.2.1); no retries or silent API-error fallback."""

from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from pydantic.alias_generators import to_camel


class ResponseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="forbid")


class Narrative(ResponseModel):
    text: str = Field(min_length=1)
    source: Literal["LLM"]
    model_explanation: None = None


class Citation(ResponseModel):
    attempt_id: UUID
    answer_id: UUID
    answer_version: StrictInt = Field(ge=1)
    quote: str = Field(min_length=1)


class Versions(ResponseModel):
    prompt: str | None
    model: str | None


class NarrativeResponse(ResponseModel):
    narrative: Narrative
    evening_question: str = Field(min_length=1)
    cited_quotes: list[Citation]
    versions: Versions


class AiClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def narrative(self, payload: dict) -> NarrativeResponse:
        response = await self._client.post("/internal/report-narratives", json=payload)
        response.raise_for_status()
        return NarrativeResponse.model_validate(response.json())
