"""추억 그림책 생성 (docs/proposals/memory-book.md 6·12장).

학생 잠금(공유) → 삭제 상태 확인 → 프로필(별명) 조회 → 이미 만든 파일이면 완료만 다시 알림
→ learning 회차 조립 → 그림 받기(data URI) → PDF 렌더링 → S3 저장 → Outbox `memorybook.completed`.
report DB에는 그림책 행을 두지 않는다
(키 규칙 `reports/memory-books/{studentId}/{bookId}/pdf`, 8.1·#975 C3).
영구 실패(미보유·계약 오류·삭제)는 FAILED 완료 이벤트로 알리고,
일시 장애는 예외로 올려 큐 재시도(1·5·15분)에 맡긴다.
"""

import asyncio
import logging

from app.clients.asset_fetcher import AssetFetcher
from app.clients.memory_book_client import MemoryBookLearningClient, MemoryBookRoundNotFound
from app.clients.storage import ObjectStorage, memory_book_key, memory_book_prefix
from app.concurrency import run_blocking
from app.database import run_db, transaction
from app.deletion.service import ensure_generation_allowed
from app.generation.records import RecordContractError
from app.memory_book.models import (
    COMPLETED_SCHEMA,
    COMPLETED_TYPE,
    BookOutcome,
    BookStatus,
    FailureCode,
    GenerateMemoryBook,
)
from app.messaging.envelope import EventEnvelope
from app.outbox import service as outbox_service
from app.rendering.renderer import ReportRenderer
from app.security import current_user_context

logger = logging.getLogger(__name__)


class MemoryBookService:
    def __init__(
        self,
        factory,
        locks,
        profiles,
        learning: MemoryBookLearningClient,
        assets: AssetFetcher,
        storage_loader,
        renderer: ReportRenderer | None = None,
        *,
        outbox=None,
    ):
        self._factory, self._locks = factory, locks
        self._profiles, self._learning, self._assets = profiles, learning, assets
        self._storage = storage_loader
        self._renderer = renderer or ReportRenderer()
        self._outbox = outbox

    async def generate(self, command: GenerateMemoryBook) -> None:
        # 주간 리포트와 같은 학생 공유 잠금: 학생 삭제(배타)와 겹치지 않게
        acquisition = asyncio.create_task(
            asyncio.to_thread(self._locks.acquire, command.book_id, command.student_id)
        )
        try:
            lease = await asyncio.shield(acquisition)
        except asyncio.CancelledError:
            try:
                lease = await acquisition
            except Exception:
                raise asyncio.CancelledError() from None
            await run_db(lease.close)
            raise
        try:
            outcome = await self._build(command)
            await run_db(lambda: self._complete(command, outcome))
        finally:
            await run_db(lease.close)

    async def _build(self, command: GenerateMemoryBook) -> BookOutcome:
        if not await run_db(lambda: self._allowed(command)):
            return BookOutcome(BookStatus.FAILED, FailureCode.STUDENT_DELETED)
        storage: ObjectStorage = self._storage()
        key = memory_book_key(command.student_id, command.book_id)
        profile = await self._profiles.lookup(command.student_id)
        if await run_blocking(lambda: storage.exists(key)):
            # 재전달: 이미 저장했으면 다시 만들지 않고 완료만 다시 알린다(core가 멱등 처리)
            return BookOutcome(BookStatus.READY)
        try:
            round_ = await self._learning.round(
                command.student_id, command.theme_id, command.week_start
            )
        except MemoryBookRoundNotFound:
            return BookOutcome(BookStatus.FAILED, FailureCode.THEME_FRAME_NOT_FOUND)
        except RecordContractError:
            return BookOutcome(BookStatus.FAILED, FailureCode.INVALID_ROUND)
        book, wanted, received = await self._with_images(round_.model_dump(mode="json"))
        if wanted and not received:
            # 일부만 빠지면 빈 칸으로 두고 완성, 전부 빠지면 실패
            # (사용 예약은 core가 미사용으로 마감)
            logger.warning("그림책 그림을 하나도 받지 못함: book=%s n=%d", command.book_id, wanted)
            return BookOutcome(BookStatus.FAILED, FailureCode.ASSET_UNAVAILABLE)
        files = await run_blocking(
            lambda: self._renderer.render_memory_book(book, profile.nickname)
        )
        pdf = files["PDF"]
        try:
            await run_blocking(lambda: storage.put(key, pdf, "application/pdf"))
        except Exception:
            try:
                await run_blocking(
                    lambda: storage.delete_prefix(
                        memory_book_prefix(command.student_id, command.book_id)
                    )
                )
            except Exception:
                logger.warning("그림책 부분 업로드 정리 재확인 필요: book=%s", command.book_id)
            raise
        return BookOutcome(
            BookStatus.READY, size_bytes=len(pdf), theme_version_id=round_.themeVersionId
        )

    async def _with_images(self, book: dict) -> tuple[dict, int, int]:
        """그림 주소를 data URI로 바꾼다. 돌려주는 값: (책, 주소가 있던 그림 수, 받은 그림 수)"""
        session = self._assets.session()
        counts = [0, 0]

        async def fetch(url):
            if not url:
                return None
            counts[0] += 1
            uri = await session.data_uri(url)
            counts[1] += uri is not None
            return uri

        book["introImage"] = await fetch(book.get("introImage"))
        for day in book["days"]:
            day["sceneImage"] = await fetch(day.get("sceneImage"))
        ending = book["ending"]
        ending["outroImage"] = await fetch(ending.get("outroImage")) if ending["seen"] else None
        return book, counts[0], counts[1]

    def _allowed(self, command: GenerateMemoryBook) -> bool:
        with transaction(self._factory) as session:
            return ensure_generation_allowed(session, command.student_id, command.requested_at)

    def _complete(self, command: GenerateMemoryBook, outcome: BookOutcome) -> None:
        context = current_user_context()
        data: dict = {
            "bookId": str(command.book_id),
            "studentId": str(command.student_id),
            "status": outcome.status.value,
        }
        if outcome.failure_code is not None:
            data["failureCode"] = outcome.failure_code.value
        if outcome.size_bytes is not None:
            data["sizeBytes"] = outcome.size_bytes
        if outcome.theme_version_id is not None:
            data["themeVersionId"] = str(outcome.theme_version_id)
        envelope = EventEnvelope[dict](
            type=COMPLETED_TYPE,
            source="report-service",
            subject=str(command.student_id),
            dataschema=COMPLETED_SCHEMA,
            traceparent=context.traceparent if context else None,
            data=data,
        )
        with transaction(self._factory) as session:
            if self._outbox is None:
                outbox_service.add_event(session, envelope)
            else:
                self._outbox.add(session, envelope)
