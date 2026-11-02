package com.sagomungchi.learning.record.repository

import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.record.service.ProcessedEventCleanup
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.time.Duration
import java.time.Instant
import java.util.UUID
import kotlin.test.assertEquals

/** #208 processed_event 90일 보존 정리 */
class ProcessedEventRepositoryTest : PostgresRepositoryTest() {
    @Autowired lateinit var repository: ProcessedEventRepository
    @Autowired lateinit var cleanup: ProcessedEventCleanup
    @Autowired lateinit var jdbc: JdbcTemplate

    @Test
    fun `정리는 보존 기간이 지난 처리 기록만 삭제`() {
        val now = Instant.now()
        val old = UUID.randomUUID().also { repository.markProcessed(it, "student.deleted", now.minus(Duration.ofDays(91))) }
        val recent = UUID.randomUUID().also { repository.markProcessed(it, "student.deleted", now) }

        cleanup.cleanup()

        assertEquals(0, count(old))
        assertEquals(1, count(recent))
    }

    private fun count(id: UUID) = jdbc.queryForObject("SELECT count(*) FROM processed_event WHERE event_id = ?", Int::class.java, id)
}
