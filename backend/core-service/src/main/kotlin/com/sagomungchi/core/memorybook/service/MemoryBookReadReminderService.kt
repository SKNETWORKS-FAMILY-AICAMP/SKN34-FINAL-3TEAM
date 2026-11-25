package com.sagomungchi.core.memorybook.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.memorybook.repository.MemoryBookRepository
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.temporal.TemporalAdjusters

/** 한 번 실행한 결과(건수만, 학생 ID·별명 없음) */
data class MemoryBookReminderRun(val children: Int, val notifications: Int)

/**
 * 토요일 저녁 같이 읽기 알림(#1025, FN-RPT-18). 지난 7일 안에 READY가 됐고 같이 읽음 표시가 없으며 보관 기간 안인 책이
 * 있는 자녀마다, 알림 받을 학부모에게 그 주 1건(`MEMORY_BOOK_READ_REMINDER`, 원천 ID = 자녀 + 그 주 월요일 KST).
 * 자녀마다 따로 트랜잭션([MemoryBookJobService.remindReadTogether])이라 한 자녀가 실패해도 나머지는 계속하고,
 * 실패가 있으면 끝에 알린다. 로그에는 건수와 오류 코드만 남긴다
 */
@Service
class MemoryBookReadReminderService(private val repository: MemoryBookRepository, private val jobs: MemoryBookJobService) {
    fun remind(at: Instant): MemoryBookReminderRun {
        val now = OffsetDateTime.ofInstant(at, ZoneOffset.UTC)
        val since = now.minusDays(WINDOW_DAYS)
        val weekStart = LocalDate.ofInstant(at, KST).with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
        val students = repository.unreadStudents(since, now)
        var created = 0
        var failed = 0
        students.forEach { student ->
            try {
                created += jobs.remindReadTogether(student, weekStart, since, now)
            } catch (ex: Exception) {
                failed++
                log.warn("memory book read reminder failed for a child ({})", (ex as? BusinessException)?.code ?: ex.javaClass.simpleName)
            }
        }
        log.info("memory book read reminders: {} children checked, {} notifications created, {} failed", students.size, created, failed)
        check(failed == 0) { "memory book read reminder failed for $failed children; $created notifications created" }
        return MemoryBookReminderRun(students.size, created)
    }

    private companion object {
        val log = LoggerFactory.getLogger(MemoryBookReadReminderService::class.java)
        val KST: ZoneId = ZoneId.of("Asia/Seoul")
        const val WINDOW_DAYS = 7L
    }
}
