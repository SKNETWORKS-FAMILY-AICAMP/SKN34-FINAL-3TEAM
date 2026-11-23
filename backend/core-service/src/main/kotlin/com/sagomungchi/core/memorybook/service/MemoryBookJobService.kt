package com.sagomungchi.core.memorybook.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.messaging.ProcessedEventRepository
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core.memorybook.domain.MemoryBookCompleted
import com.sagomungchi.core.memorybook.domain.MemoryBookJob
import com.sagomungchi.core.memorybook.domain.MemoryBookStatus
import com.sagomungchi.core.memorybook.messaging.MemoryBookGenerateWriter
import com.sagomungchi.core.memorybook.repository.MemoryBookRepository
import com.sagomungchi.core.payment.service.ProductEntitlementService
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.Clock
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.util.UUID

@Configuration
class MemoryBookConfiguration { @Bean fun memoryBookClock(): Clock = Clock.systemUTC() }

/**
 * 추억 그림책 작업 행의 트랜잭션 경계 (docs/proposals/memory-book.md 6·8장, 미도입 시험 구현).
 * 생성은 학생 행 잠금 안에서 재사용·하루 한도를 다시 확인하고 작업 행과 `memorybook.generate` Outbox를 함께 저장한다.
 * 완료는 처리한 이벤트를 한 번만 반영하고 사용 예약을 마감한다(READY = 사용, FAILED = 미사용)
 */
@Service
class MemoryBookJobService(
    private val repository: MemoryBookRepository,
    private val writer: MemoryBookGenerateWriter,
    private val students: StudentAccessService,
    private val processed: ProcessedEventRepository,
    private val entitlements: ProductEntitlementService,
    @Qualifier("memoryBookClock") private val clock: Clock,
) {
    fun now(): OffsetDateTime = OffsetDateTime.ofInstant(clock.instant(), ZoneOffset.UTC)

    /** KST 오늘 00:00 (하루 한도 기준) */
    fun todayStart(): OffsetDateTime = clock.instant().atZone(KST).toLocalDate().atStartOfDay(KST).toOffsetDateTime()

    /** 만들 작업 저장. 그 사이 같은 회차 작업이 생겼으면 그것을 돌려주고 새로 저장하지 않는다(second = 새로 저장했는지) */
    @Transactional
    fun create(job: MemoryBookJob, limit: Int): Pair<MemoryBookJob, Boolean> {
        if (students.lockStatus(job.studentId) != "ACTIVE")
            throw BusinessException(HttpStatus.CONFLICT, "STUDENT_UNAVAILABLE", "학생 상태를 다시 확인해 주세요.")
        repository.reusable(job.studentId, job.themeId, job.weekStart, now())?.let { return it to false }
        if (repository.createdSince(job.studentId, todayStart()) >= limit) limitReached()
        check(repository.insert(job) == 1)
        writer.append(job)
        return job to true
    }

    @Transactional
    fun complete(event: MemoryBookCompleted) {
        if (!processed.markProcessed(event.eventId, EVENT_TYPE)) return
        // 학생 삭제로 행이 지워졌으면 늦게 온 결과는 버린다
        val job = repository.lock(event.bookId) ?: return
        require(job.studentId == event.studentId) { "Memory book identity mismatch" }
        if (job.status != MemoryBookStatus.QUEUED) return
        repository.complete(job.id, event.status, event.failureCode, event.sizeBytes, event.themeVersionId, now())
        job.usageReservationId?.let { reservation ->
            try {
                entitlements.finishUsage(job.studentId, reservation, event.status == MemoryBookStatus.READY)
            } catch (error: BusinessException) {
                // 구독이 그 사이 끝났으면 예약 마감을 못 한다. 결과 반영은 유지하고 기록만 남긴다
                log.warn("memory book usage not finished: book={}, code={}", job.id, error.code)
            }
        }
    }

    @Transactional
    fun recordDownload(job: MemoryBookJob, user: UUID, role: String) = repository.download(job.id, job.studentId, user, role, now())

    /** 학생 삭제(P09)와 같은 트랜잭션에서만 */
    @Transactional(propagation = Propagation.MANDATORY)
    fun deleteStudent(studentId: UUID): Int = repository.deleteByStudent(studentId)

    fun limitReached(): Nothing =
        throw BusinessException(HttpStatus.TOO_MANY_REQUESTS, "USAGE_LIMIT_REACHED", "오늘은 추억 그림책을 더 만들 수 없어요.")

    companion object {
        const val EVENT_TYPE = "memorybook.completed"
        private val KST: ZoneId = ZoneId.of("Asia/Seoul")
        private val log = LoggerFactory.getLogger(MemoryBookJobService::class.java)
    }
}
