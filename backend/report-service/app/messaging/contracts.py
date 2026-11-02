"""Strict receive boundary for the existing CloudEvents schema; no generated defaults."""

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ConfigDict, field_validator

from app.messaging.envelope import EventEnvelope


class InvalidEvent(ValueError):
    """Permanent wire contract error; reject without delayed retries."""


def uuid_text(value: str) -> UUID:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}", value
    ):
        raise ValueError("Expected UUID string")
    return UUID(value)


class ReceivedEnvelope(EventEnvelope[dict[str, Any]]):
    model_config = ConfigDict(extra="forbid")

    id: str
    specversion: Literal["1.0"]
    time: datetime

    @field_validator("id")
    @classmethod
    def valid_id(cls, value):
        uuid_text(value)
        return value

    @field_validator("time", mode="before")
    @classmethod
    def valid_time(cls, value):
        if not isinstance(value, str):
            raise ValueError("Expected offset date-time string")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if "T" not in value.upper() or parsed.utcoffset() is None:
            raise ValueError("Expected offset date-time string")
        return value

    @field_validator("dataschema")
    @classmethod
    def valid_schema(cls, value):
        if not re.fullmatch(r"[a-z.]+\.v[0-9]+", value):
            raise ValueError("Unsupported schema identifier")
        return value
