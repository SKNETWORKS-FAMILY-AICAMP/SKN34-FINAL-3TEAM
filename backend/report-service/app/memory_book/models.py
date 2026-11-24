"""추억 그림책 명령·결과 (docs/proposals/memory-book.md 7.2)."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

GENERATE_TYPE = "memorybook.generate"
GENERATE_SCHEMA = "memorybook.generate.v1"
COMPLETED_TYPE = "memorybook.completed"
COMPLETED_SCHEMA = "memorybook.completed.v1"


@dataclass(frozen=True)
class GenerateMemoryBook:
    book_id: UUID
    student_id: UUID
    theme_id: UUID
    week_start: date
    requested_at: datetime


class BookStatus(StrEnum):
    READY = "READY"
    FAILED = "FAILED"


class FailureCode(StrEnum):
    """영구 실패만(재시도해도 같은 결과). 일시 장애는 큐 재시도에 맡긴다"""

    STUDENT_RECORDS_PRIVATE = "STUDENT_RECORDS_PRIVATE"
    THEME_FRAME_NOT_FOUND = "THEME_FRAME_NOT_FOUND"
    STUDENT_DELETED = "STUDENT_DELETED"
    INVALID_ROUND = "INVALID_ROUND"
    # 그림 주소가 있는데 한 장도 받지 못함(출처 누락·저장소 오류 등).
    # 그림 없는 PDF를 완성으로 내지 않는다(#975)
    ASSET_UNAVAILABLE = "ASSET_UNAVAILABLE"


@dataclass(frozen=True)
class BookOutcome:
    status: BookStatus
    failure_code: FailureCode | None = None
    size_bytes: int | None = None
    theme_version_id: UUID | None = None
