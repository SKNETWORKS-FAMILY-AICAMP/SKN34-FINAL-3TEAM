package com.sagomungchi.core._common.messaging

import com.sagomungchi.core._common.config.AppProperties
import org.slf4j.LoggerFactory
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import java.time.OffsetDateTime

/**
 * 보존 기간(기본 90일)이 지난 발행 완료 outbox_event·processed_event·event_log 삭제 (아키텍처 1.6).
 * 미발행 outbox 행은 남김. 조건부 DELETE라 레플리카가 동시에 실행해도 결과가 같음.
 */
@Component
class EventRetentionCleanup(
    private val outbox: OutboxEventRepository,
    private val processed: ProcessedEventRepository,
    private val eventLog: EventLogRepository,
    private val properties: AppProperties,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    @Scheduled(fixedDelayString = "\${app.messaging.event-retention-cleanup-interval:3600000}", initialDelayString = "3600000")
    fun cleanup() {
        val before = OffsetDateTime.now().minusDays(properties.messaging.eventRetentionDays)
        val outboxCount = outbox.deletePublishedBefore(before)
        val processedCount = processed.deleteProcessedBefore(before)
        val eventLogCount = eventLog.deleteReceivedBefore(before)
        log.info("이벤트 기록 정리: outbox={}, processed={}, eventLog={}", outboxCount, processedCount, eventLogCount)
    }
}
