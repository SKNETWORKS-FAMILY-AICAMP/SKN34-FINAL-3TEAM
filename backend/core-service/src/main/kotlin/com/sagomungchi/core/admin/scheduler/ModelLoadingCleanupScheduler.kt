package com.sagomungchi.core.admin.scheduler

import com.sagomungchi.core.admin.service.ModelLoadingService
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component

/** 오래된 모델 로딩 보고 정리 주기 실행. 스케줄 수신만 하고 삭제는 ModelLoadingService (아키텍처 2.1, #314). 만료 행 DELETE라 ShedLock 없음 */
@Component
class ModelLoadingCleanupScheduler(private val service: ModelLoadingService) {
    @Scheduled(fixedDelay = 3600000)
    fun cleanup() {
        service.cleanup()
    }
}
