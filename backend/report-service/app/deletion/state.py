"""삭제 명령과 순수 상태 판정. DB 작업과 HTTP 오류 처리는 service/repository 소유."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.generation.models import GenerationBusy
from app.generation.records import RecordContractError


@dataclass(frozen=True)
class DeleteStudent:
    event_id: UUID
    student_id: UUID
    request_id: UUID
    scope: str
    occurred_at: datetime

    def __post_init__(self):
        if self.scope not in {"PROFILE", "RECORDS"} or self.occurred_at.utcoffset() is None:
            raise RecordContractError("Invalid student deletion scope/time")


def begin_action(row, processed, command: DeleteStudent):
    if processed is not None:
        if (
            processed == "student.deleted"
            and row is not None
            and row["status"] == "PENDING"
            and row["deletion_request_id"] != command.request_id
        ):
            # Completed before a newer request started; resend only its completion report.
            return "SKIP"
        if (
            processed != "student.deleted"
            or row is None
            or row["status"] != "COMPLETED"
            # PROFILE also covers later events: use the same coverage rule
            # on redelivery as when the event was first marked processed.
            or (row["scope"] != "PROFILE" and row["cutoff_at"] < command.occurred_at)
            or (command.scope == "PROFILE" and row["scope"] != "PROFILE")
        ):
            raise RecordContractError("Processed deletion identity is inconsistent")
        return "SKIP"
    if row is not None:
        covered = row["scope"] == "PROFILE" or (
            command.scope == "RECORDS" and row["cutoff_at"] >= command.occurred_at
        )
        if covered and row["status"] == "COMPLETED":
            return "MARK"
        if row["status"] == "PENDING" and row["deletion_request_id"] != command.request_id:
            raise GenerationBusy("Another deletion request must finish first")
    return "START"


def generation_allowed(status):
    if status is None:
        return True
    if status == "PENDING":
        raise GenerationBusy("Student deletion is pending")
    return False


def __getattr__(name):
    # #252 호환 요구: 과거 테스트의 테이블 import만 지연 재노출한다.
    # 실제 업무 코드와 순수 규칙은 이 경로를 사용하지 않는다.
    if name in {"deletion_guard", "processed_event"}:
        from app.deletion import repository

        return getattr(repository, name)
    raise AttributeError(name)
