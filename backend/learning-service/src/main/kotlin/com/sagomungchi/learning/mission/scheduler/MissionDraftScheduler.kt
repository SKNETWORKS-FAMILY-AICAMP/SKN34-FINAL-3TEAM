package com.sagomungchi.learning.mission.scheduler

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning.mission.service.MissionDraftService
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import java.time.Instant

/**
 * 미션 초안 주기 생성 (class-diagram 4.1.1, state-diagram 3.4, #353). 스케줄 수신만 하고 처리는 MissionDraftService.
 * 한 주기에 초안 하나를 생성 1회. 점유가 조건부 UPDATE라 레플리카가 같은 주기에 돌아도 같은 초안을 잡지 않음
 */
@Component
class MissionDraftScheduler(
    private val service: MissionDraftService,
    private val properties: AppProperties,
) {
    @Scheduled(
        fixedDelayString = "\${app.mission-draft.interval:PT10S}",
        initialDelayString = "\${app.mission-draft.interval:PT10S}",
    )
    fun generate() {
        if (properties.missionDraft.enabled) service.generateNext(Instant.now())
    }
}
