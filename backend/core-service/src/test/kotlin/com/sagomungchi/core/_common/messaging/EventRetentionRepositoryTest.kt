package com.sagomungchi.core._common.messaging

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.assertEquals

/** #208 event_log 기록과 90일 보존 정리: 미발행 outbox는 기간과 무관하게 남김 */
class EventRetentionRepositoryTest : PostgresRepositoryTest() {
    @Autowired lateinit var eventLog: EventLogRepository
    @Autowired lateinit var outbox: OutboxEventRepository
    @Autowired lateinit var processed: ProcessedEventRepository
    @Autowired lateinit var cleanup: EventRetentionCleanup
    @Autowired lateinit var jdbc: JdbcTemplate

    private val now = OffsetDateTime.now()
    private val old = now.minusDays(91)

    @Test
    fun `event_log는 같은 id를 1행만 기록`() {
        val id = UUID.randomUUID()

        assertEquals(1, eventLog.insertIfAbsent(id, "llm.usage.recorded", "ai-service", null, now, now))
        assertEquals(0, eventLog.insertIfAbsent(id, "llm.usage.recorded", "ai-service", null, now, now.plusSeconds(1)))
    }

    @Test
    fun `정리는 보존 기간이 지난 발행 완료 outbox와 processed_event와 event_log만 삭제`() {
        val oldPublished = outboxRow(old, publishedAt = old)
        val oldUnpublished = outboxRow(old, publishedAt = null)
        val recentPublished = outboxRow(now, publishedAt = now)
        val oldProcessed = UUID.randomUUID().also { processed.insertIfAbsent(it, "student.deleted", old) }
        val recentProcessed = UUID.randomUUID().also { processed.insertIfAbsent(it, "student.deleted", now) }
        val oldLog = UUID.randomUUID().also { eventLog.insertIfAbsent(it, "report.started", "report-service", "s", old, old) }
        val recentLog = UUID.randomUUID().also { eventLog.insertIfAbsent(it, "report.started", "report-service", "s", now, now) }

        cleanup.cleanup()

        assertEquals(setOf(oldUnpublished, recentPublished), existing("outbox_event", "id", oldPublished, oldUnpublished, recentPublished))
        assertEquals(setOf(recentProcessed), existing("processed_event", "event_id", oldProcessed, recentProcessed))
        assertEquals(setOf(recentLog), existing("event_log", "event_id", oldLog, recentLog))
    }

    private fun outboxRow(createdAt: OffsetDateTime, publishedAt: OffsetDateTime?): UUID {
        val id = UUID.randomUUID()
        outbox.insert(OutboxEvent(id, "student.deleted", "student.deleted", "s", "{}", createdAt))
        publishedAt?.let { outbox.markPublished(id, it) }
        return id
    }

    private fun existing(table: String, column: String, vararg ids: UUID): Set<UUID> =
        ids.filter { jdbc.queryForObject("SELECT count(*) FROM $table WHERE $column = ?", Int::class.java, it) == 1 }.toSet()
}
