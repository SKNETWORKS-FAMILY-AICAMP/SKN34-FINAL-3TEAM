"""CloudEvents 형식 이벤트 봉투 (아키텍처 1.6). 스키마: contracts/events/envelope.schema.json"""

from datetime import UTC, datetime
from typing import Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

T = TypeVar("T")


class EventEnvelope(BaseModel, Generic[T]):
    id: str = Field(default_factory=lambda: str(uuid4()))
    specversion: str = "1.0"
    type: str
    source: str
    time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    subject: str | None = None
    dataschema: str
    traceparent: str | None = None
    data: T
