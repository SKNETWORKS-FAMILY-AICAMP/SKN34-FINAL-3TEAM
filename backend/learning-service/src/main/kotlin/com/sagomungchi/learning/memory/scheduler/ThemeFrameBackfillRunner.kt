package com.sagomungchi.learning.memory.scheduler

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning.memory.service.ThemeFrameService
import org.slf4j.LoggerFactory
import org.springframework.boot.context.event.ApplicationReadyEvent
import org.springframework.context.event.EventListener
import org.springframework.stereotype.Component

/**
 * 기념 액자 소급 (P27, 결정 기록 3.2, #559): 기동할 때마다 도입 전·지급 누락 회차를 같은 조건으로 채운다.
 * INSERT … ON CONFLICT DO NOTHING이라 다시 돌거나 레플리카가 동시에 돌아도 회차당 1개이고, 이미 있는 액자는 건드리지 않는다.
 * 롤링 배포 중 이전 Pod가 처리한 완료도 다음 기동 때 채워진다. 실패해도 학습 완료의 지급은 그대로라 기동은 막지 않는다
 */
@Component
class ThemeFrameBackfillRunner(
    private val service: ThemeFrameService,
    private val properties: AppProperties,
) {
    @EventListener(ApplicationReadyEvent::class)
    fun run() {
        if (!properties.themeFrame.backfillOnStartup) return
        try {
            log.info("theme_frame backfill inserted={}", service.backfill())
        } catch (exception: RuntimeException) {
            log.error("theme_frame backfill failed; next startup retries", exception)
        }
    }

    private companion object {
        val log = LoggerFactory.getLogger(ThemeFrameBackfillRunner::class.java)
    }
}
