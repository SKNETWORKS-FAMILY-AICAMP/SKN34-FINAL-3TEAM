package com.sagomungchi.core.memorybook.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.messaging.ProcessedEventRepository
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import com.sagomungchi.core.memorybook.domain.MemoryBookCompleted
import com.sagomungchi.core.memorybook.domain.MemoryBookJob
import com.sagomungchi.core.memorybook.domain.MemoryBookStatus
import com.sagomungchi.core.memorybook.messaging.MemoryBookGenerateWriter
import com.sagomungchi.core.memorybook.repository.MemoryBookRepository
import com.sagomungchi.core.notification.service.NotificationService
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
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.util.UUID

@Configuration
class MemoryBookConfiguration { @Bean fun memoryBookClock(): Clock = Clock.systemUTC() }

/**
 * 추억 그림책 작업 행의 트랜잭션 경계 (docs/proposals/memory-book.md 6·8장).
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
    private val learningContext: StudentLearningContextService,
    private val notifications: NotificationService,
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

    /** "같이 읽었어요" 표시(#1025). 이미 있으면 처음 시각 그대로. 그 사이 학생 삭제로 행이 지워졌으면 null */
    @Transactional
    fun readTogether(job: MemoryBookJob): MemoryBookJob? = repository.readTogether(job.id, job.studentId, now())

    /**
     * 토요일 같이 읽기 알림(#1025) 한 자녀분. 자녀마다 따로 트랜잭션이라 한 자녀가 실패해도 다른 자녀는 그대로 남는다.
     * 학생 행을 잠그고 ACTIVE·현재 원문 공개·조건을 다시 확인한 뒤, 알림 받을 학부모(연결 + 필수 동의 + 법정대리인 동의)마다 1건.
     * 같은 주에 다시 돌아도 원천 ID가 같아 1건이다. 새로 만든 알림 수를 돌려준다
     */
    @Transactional
    fun remindReadTogether(studentId: UUID, weekStart: LocalDate, since: OffsetDateTime, at: OffsetDateTime): Int {
        if (students.lockStatus(studentId) != "ACTIVE") return 0
        // 받기가 403이라 원문 비공개 자녀에게는 알리지 않는다
        if (!learningContext.sharingEnabled(studentId)) return 0
        if (!repository.hasUnread(studentId, since, at)) return 0
        return students.notificationParents(studentId).count { parent ->
            val nickname = students.linkedStudents(parent).firstOrNull { it.id == studentId }?.nickname ?: return@count false
            notifications.memoryBookReadReminder(parent, studentId, nickname, weekStart)
        }
    }

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
