package com.sagomungchi.learning.theme.scheduler

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning.theme.domain.ThemeWeek
import com.sagomungchi.learning.theme.service.ThemeDraftService
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import java.time.Clock
import java.time.Instant
import java.time.LocalDate

/**
 * 테마 초안 주기 생성·주간 자동 (class-diagram 4.4, state-diagram 3.5.1, #438). 스케줄 수신만 하고 처리는 ThemeDraftService.
 * 작업마다 스케줄러 스레드 하나(spring.task.scheduling.pool.size 5)라 생성이 ai를 16분 기다려도 다른 작업이 밀리지 않음
 */
@Component
class ThemeDraftScheduler(
    private val service: ThemeDraftService,
    private val properties: AppProperties,
    private val clock: Clock,
) {
    /** 한 주기에 초안 하나를 생성 1회. 점유가 조건부 UPDATE라 레플리카가 같은 주기에 돌아도 같은 초안을 잡지 않음 */
    @Scheduled(
        fixedDelayString = "\${app.theme-draft.interval:PT10S}",
        initialDelayString = "\${app.theme-draft.interval:PT10S}",
    )
    fun generate() {
        if (properties.themeDraft.enabled) service.generateNext(Instant.now())
    }

    /** 주간 자동(기준안 수요일 03:00 KST): 다음 주 G3~G6 각 1개. 레플리카가 같이 돌아도 부분 UK로 학년·주당 하나 */
    @Scheduled(cron = "\${app.theme-draft.weekly-cron:0 0 3 * * WED}", zone = "Asia/Seoul")
    fun createWeekly() {
        if (properties.themeDraft.enabled) service.createWeekly(ThemeWeek.startOf(LocalDate.now(clock)).plusWeeks(1))
    }
}
