package com.sagomungchi.core._common.scheduler

import com.sagomungchi.core._common.web.IdempotencyService
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component

/** 만료 멱등 키 정리 주기 실행. 스케줄 수신만 하고 삭제는 IdempotencyService (아키텍처 2.1, #314). 만료 행 DELETE라 ShedLock 없음 */
@Component
class IdempotencyCleanupScheduler(private val service: IdempotencyService) {
    @Scheduled(fixedDelayString = "\${app.web.idempotency-cleanup-interval:3600000}", initialDelayString = "3600000")
    fun cleanup() {
        service.deleteExpired()
    }
}
