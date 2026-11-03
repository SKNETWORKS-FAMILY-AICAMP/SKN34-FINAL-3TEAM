package com.sagomungchi.learning.record.scheduler

import com.sagomungchi.learning.record.service.ProcessedEventCleanupService
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import java.time.Instant

/** processed_event 보존 정리 주기 실행 (#208). 스케줄 수신만 하고 삭제는 ProcessedEventCleanupService (아키텍처 2.1, #278) */
@Component
class ProcessedEventCleanupScheduler(private val service: ProcessedEventCleanupService) {
    @Scheduled(fixedDelayString = "\${app.messaging.event-retention-cleanup-interval:3600000}", initialDelayString = "3600000")
    fun cleanup() {
        service.cleanup(Instant.now())
    }
}
