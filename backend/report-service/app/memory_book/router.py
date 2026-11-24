"""추억 그림책 파일 내려받기 주소 (docs/proposals/memory-book.md 7.2).

core만 부른다. 원문 공개(D2)·유료·연결 확인은 core가 하고,
여기서는 학생 범위·삭제 상태·파일 존재만 본다.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Security
from fastapi.security import APIKeyHeader

from app.clients.storage import memory_book_key
from app.concurrency import run_blocking
from app.config import get_settings
from app.database import run_db
from app.deletion.service import ensure_query_allowed
from app.errors import ApiError, problem_responses
from app.query.schemas import Download
from app.security import current_user_context

router = APIRouter(
    prefix="/internal/students/{student_id}/memory-books",
    tags=["memory-books"],
    dependencies=[Security(APIKeyHeader(name="X-Internal-Token", auto_error=False))],
)


class MemoryBookFiles:
    def __init__(self, factory, storage_loader, ttl: int):
        self._factory, self._storage, self._ttl = factory, storage_loader, ttl

    async def pdf(self, student_id: UUID, book_id: UUID) -> dict:
        context = current_user_context()
        if context is None:
            raise ApiError(403, "FORBIDDEN", "접근 범위 밖 학생")
        context.require_student(str(student_id))

        def allowed():
            with self._factory() as session:
                ensure_query_allowed(session, student_id)

        await run_db(allowed)
        storage = self._storage()
        key = memory_book_key(student_id, book_id)
        try:
            if not await run_blocking(lambda: storage.exists(key)):
                raise ApiError(404, "NOT_FOUND", "그림책 파일이 없습니다")
            return await run_blocking(
                lambda: storage.presigned_url(key, self._ttl, f"memory-book-{book_id}.pdf")
            )
        except ApiError:
            raise
        except Exception:
            raise ApiError(503, "DATA_UNAVAILABLE", "다운로드 주소를 만들 수 없습니다") from None


async def memory_book_files(request: Request) -> MemoryBookFiles:
    return MemoryBookFiles(
        request.app.state.session_factory,
        lambda: request.app.state.storage,
        get_settings().report_download_ttl_seconds,
    )


Files = Annotated[MemoryBookFiles, Depends(memory_book_files)]


@router.get(
    "/{book_id}/files/pdf",
    response_model=Download,
    response_model_exclude_unset=True,
    responses=problem_responses(401, 403, 404, 409, 503),
)
async def file(student_id: UUID, book_id: UUID, files: Files):
    return await files.pdf(student_id, book_id)
