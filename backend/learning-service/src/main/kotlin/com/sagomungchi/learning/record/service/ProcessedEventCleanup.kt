package com.sagomungchi.learning.record.service

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning.record.repository.ProcessedEventRepository
import org.slf4j.LoggerFactory
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import java.time.Duration
import java.time.Instant

/** 보존 기간(기본 90일)이 지난 processed_event 삭제 (아키텍처 1.6). 조건부 DELETE라 레플리카 동시 실행 무해 */
@Component
class ProcessedEventCleanup(
    private val repository: ProcessedEventRepository,
    private val properties: AppProperties,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    @Scheduled(fixedDelayString = "\${app.messaging.event-retention-cleanup-interval:3600000}", initialDelayString = "3600000")
    fun cleanup() {
        val before = Instant.now().minus(Duration.ofDays(properties.messaging.eventRetentionDays))
        log.info("processed_event 정리: {}", repository.deleteProcessedBefore(before))
    }
}
