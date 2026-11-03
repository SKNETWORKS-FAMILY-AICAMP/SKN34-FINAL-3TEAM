package com.sagomungchi.learning.record.service

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning.record.repository.ProcessedEventRepository
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import java.time.Duration
import java.time.Instant

/** 보존 기간(기본 90일)이 지난 processed_event 삭제 (아키텍처 1.6). 조건부 DELETE라 레플리카 동시 실행 무해 */
@Service
class ProcessedEventCleanupService(
    private val repository: ProcessedEventRepository,
    private val properties: AppProperties,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    fun cleanup(now: Instant): Int {
        val before = now.minus(Duration.ofDays(properties.messaging.eventRetentionDays))
        return repository.deleteProcessedBefore(before).also { log.info("processed_event 정리: {}", it) }
    }
}
