package com.sagomungchi.learning.judgment.scheduler

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning.judgment.service.JudgmentService
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import java.time.Instant

/**
 * 고착 RUNNING 판정 1분 주기 탐지 (P12, state-diagram 3.3, #241). 스케줄 수신만 하고 처리는 JudgmentService (아키텍처 2.1).
 * 조건부 UPDATE라 레플리카가 같은 주기에 실행해도 한 번만 바뀜 (ProcessedEventCleanupScheduler처럼 잠금 없음)
 */
@Component
class StuckJudgmentScheduler(
    private val service: JudgmentService,
    private val properties: AppProperties,
) {
    @Scheduled(
        fixedDelayString = "\${app.judgment.stuck-detection-interval:PT1M}",
        initialDelayString = "\${app.judgment.stuck-detection-interval:PT1M}",
    )
    fun detect() {
        if (properties.judgment.stuckDetectionEnabled) service.failStuck(Instant.now())
    }
}
