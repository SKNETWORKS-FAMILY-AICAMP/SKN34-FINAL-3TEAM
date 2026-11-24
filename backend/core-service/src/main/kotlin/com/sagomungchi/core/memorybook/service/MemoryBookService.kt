package com.sagomungchi.core.memorybook.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import com.sagomungchi.core.memorybook.client.MemoryBookFileResult
import com.sagomungchi.core.memorybook.client.MemoryBookLearningClient
import com.sagomungchi.core.memorybook.client.MemoryBookReportClient
import com.sagomungchi.core.memorybook.domain.MemoryBookDownload
import com.sagomungchi.core.memorybook.domain.MemoryBookJob
import com.sagomungchi.core.memorybook.domain.MemoryBookPage
import com.sagomungchi.core.memorybook.domain.MemoryBookRound
import com.sagomungchi.core.memorybook.domain.MemoryBookRoundPage
import com.sagomungchi.core.memorybook.domain.MemoryBookRoundView
import com.sagomungchi.core.memorybook.domain.MemoryBookStatus
import com.sagomungchi.core.memorybook.domain.MemoryBookView
import com.sagomungchi.core.memorybook.repository.MemoryBookRepository
import com.sagomungchi.core.payment.service.ProductEntitlementService
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.time.DayOfWeek
import java.util.UUID

/** 생성 결과: 새로 만들기 시작했으면 created = true(202), 같은 회차의 기존 작업이면 false(200) */
data class MemoryBookCreated(val view: MemoryBookView, val created: Boolean)

/**
 * 추억 그림책 공개 API 흐름 (docs/proposals/memory-book.md 6·7·10장).
 * 발급은 학부모만(2026-11-23 결정, D1 변경): 연결된 자녀의 보유 액자 회차를 골라 만들고 받는다. 학생 경로는 없다.
 * 원문 공개 자녀만(D2): 회차 목록·생성·목록·내려받기 모두 지금 `parentSharingEnabled`가 false면 403 `STUDENT_RECORDS_PRIVATE`.
 * 생성 순서: 공개 확인 → 같은 회차 재사용 → learning 보유 확인(외부 호출, 트랜잭션 밖) → 하루 한도 → 유료 판정·사용 예약
 * → 작업 행·명령 저장(실패하면 예약을 미사용으로 마감)
 */
@Service
class MemoryBookService(
    private val jobs: MemoryBookJobService,
    private val repository: MemoryBookRepository,
    private val learning: MemoryBookLearningClient,
    private val report: MemoryBookReportClient,
    private val entitlements: ProductEntitlementService,
    private val learningContext: StudentLearningContextService,
    private val students: StudentAccessService,
) {
    /** 발급 화면: 자녀의 보유 액자 회차(최근순)와 회차마다 가장 최근 그림책 */
    fun rounds(childId: UUID, page: Int?, size: Int?): MemoryBookRoundPage {
        verifiedParent(childId)
        val (p, s) = paging(page, size)
        learningContext.requireShared(childId)
        val (items, total) = learning.album(childId, p, s)
        val now = jobs.now()
        val latest = repository.latestByStudent(childId).associateBy { MemoryBookRound(it.themeId, it.weekStart) }
        return MemoryBookRoundPage(items.map { item ->
            MemoryBookRoundView(item.themeId, item.weekStart, item.title, item.imageUrl,
                latest[MemoryBookRound(item.themeId, item.weekStart)]?.let { MemoryBookView.of(it, now) })
        }, p, s, total)
    }

    fun create(childId: UUID, round: MemoryBookRound?): MemoryBookCreated {
        val parent = verifiedParent(childId)
        val key = validRound(round)
        learningContext.requireShared(childId)
        repository.reusable(childId, key.themeId, key.weekStart, jobs.now())?.let { return MemoryBookCreated(MemoryBookView.of(it, jobs.now()), false) }
        if (!learning.owned(childId, key)) throw BusinessException(HttpStatus.NOT_FOUND, "THEME_FRAME_NOT_FOUND", "보유하지 않은 기념 액자", "아직 받지 않은 기념 액자예요.")
        val limit = entitlements.memoryBookLimit(childId)
        if (repository.createdSince(childId, jobs.todayStart()) >= limit) jobs.limitReached()
        val bookId = UUID.randomUUID()
        val permit = entitlements.beginMemoryBook(childId, bookId)
        val now = jobs.now()
        val job = MemoryBookJob(bookId, childId, parent, key.themeId, key.weekStart, MemoryBookStatus.QUEUED, null, null, null,
            permit.reservationId, now, null, now.plusDays(RETENTION_DAYS))
        val (saved, created) = try { jobs.create(job, limit) } catch (error: RuntimeException) { release(childId, permit.reservationId); throw error }
        if (!created) release(childId, permit.reservationId)
        return MemoryBookCreated(MemoryBookView.of(saved, jobs.now()), created)
    }

    fun books(childId: UUID, page: Int?, size: Int?): MemoryBookPage {
        verifiedParent(childId)
        val (p, s) = paging(page, size)
        learningContext.requireShared(childId)
        val now = jobs.now()
        return MemoryBookPage(repository.page(childId, p, s).map { MemoryBookView.of(it, now) }, p, s, repository.count(childId))
    }

    fun download(childId: UUID, bookId: UUID): MemoryBookDownload {
        val parent = verifiedParent(childId)
        learningContext.requireShared(childId)
        val job = repository.find(bookId)?.takeIf { it.studentId == childId }
            ?: throw BusinessException(HttpStatus.NOT_FOUND, "MEMORY_BOOK_NOT_FOUND", "그림책을 찾을 수 없어요.")
        when {
            job.status == MemoryBookStatus.QUEUED -> throw BusinessException(HttpStatus.CONFLICT, "MEMORY_BOOK_NOT_READY", "그림책을 만들고 있어요.")
            job.status == MemoryBookStatus.FAILED -> throw BusinessException(HttpStatus.CONFLICT, "MEMORY_BOOK_FAILED", "그림책을 만들지 못했어요.", job.failureCode)
            job.expired(jobs.now()) -> expired()
        }
        val download = when (val result = report.fileUrl(childId, bookId)) {
            is MemoryBookFileResult.Url -> result.download
            MemoryBookFileResult.Missing -> expired()
            MemoryBookFileResult.Deleting -> throw BusinessException(HttpStatus.CONFLICT, "DELETION_IN_PROGRESS", "학생 기록을 삭제 중입니다.")
        }
        jobs.recordDownload(job, parent, "PARENT")
        return download
    }

    private fun paging(page: Int?, size: Int?): Pair<Int, Int> {
        val p = page ?: 0
        val s = size ?: DEFAULT_SIZE
        if (p < 0 || s !in 1..MAX_SIZE) invalid("page는 0 이상, size는 1~$MAX_SIZE")
        return p to s
    }

    private fun release(student: UUID, reservation: UUID?) {
        reservation ?: return
        try { entitlements.finishUsage(student, reservation, false) } catch (error: RuntimeException) {
            log.error("memory book usage not released: student={}", student, error)
        }
    }

    private fun validRound(round: MemoryBookRound?): MemoryBookRound {
        round ?: invalid("rounds는 회차 1개 배열이어야 합니다.")
        if (round.weekStart.dayOfWeek != DayOfWeek.MONDAY) invalid("weekStart는 월요일 날짜여야 합니다.")
        return round
    }

    /** 연결된 학부모(동의 포함). 학부모 사용자 ID */
    private fun verifiedParent(childId: UUID): UUID {
        val context = UserContextHolder.currentOrNull()
        if (context?.role != "PARENT" || context.userId == null) throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학부모 세션이 필요합니다.")
        return UUID.fromString(context.userId).also { students.requireLinked(it, childId) }
    }

    private fun expired(): Nothing = throw BusinessException(HttpStatus.GONE, "MEMORY_BOOK_EXPIRED", "보관 기간이 지난 그림책이에요.", "다시 만들 수 있어요.")

    private fun invalid(message: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", message)

    private companion object {
        val log = LoggerFactory.getLogger(MemoryBookService::class.java)
        const val RETENTION_DAYS = 30L
        const val DEFAULT_SIZE = 20
        const val MAX_SIZE = 100
    }
}
