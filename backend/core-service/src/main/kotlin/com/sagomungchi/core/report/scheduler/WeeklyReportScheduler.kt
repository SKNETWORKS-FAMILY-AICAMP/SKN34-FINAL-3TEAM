package com.sagomungchi.core.report.scheduler

import com.sagomungchi.core.report.domain.ReportPeriodType
import com.sagomungchi.core.report.service.ReportScheduleService
import net.javacrumbs.shedlock.core.LockAssert
import net.javacrumbs.shedlock.core.LockProvider
import net.javacrumbs.shedlock.provider.jdbctemplate.JdbcTemplateLockProvider
import net.javacrumbs.shedlock.spring.annotation.EnableSchedulerLock
import net.javacrumbs.shedlock.spring.annotation.SchedulerLock
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import java.time.Clock
import java.time.Duration

/**
 * Both jobs run at 00:00 KST, right on the period boundary. Spring may fire a few ms early, which would make
 * `clock.instant()` fall on the previous KST day and pick a period one step too old, so the run instant is shifted
 * forward. A late run (up to lockAtMostFor) still lands on the same KST day and so the same target.
 */
internal val EARLY_RUN_GRACE: Duration = Duration.ofMinutes(1)

@Configuration
@EnableSchedulerLock(defaultLockAtMostFor = "PT30M")
class ReportScheduleConfiguration {
    @Bean fun reportClock(): Clock = Clock.systemUTC()
    @Bean fun reportLockProvider(jdbc: JdbcTemplate): LockProvider = JdbcTemplateLockProvider(
        JdbcTemplateLockProvider.Configuration.builder().withJdbcTemplate(jdbc).usingDbTime().build())
}

/** P06: every Monday 00:00 KST (the end of Sunday) for the previous KST Monday..Sunday. */
@Component
class WeeklyReportScheduler(private val service: ReportScheduleService, @Qualifier("reportClock") private val clock: Clock) {
    @Scheduled(cron = "0 0 0 * * MON", zone = "Asia/Seoul")
    @SchedulerLock(name = "core-weekly-reports", lockAtMostFor = "PT30M", lockAtLeastFor = "PT1M")
    fun generate() {
        LockAssert.assertLocked()
        service.generate(clock.instant().plus(EARLY_RUN_GRACE), ReportPeriodType.WEEKLY)
    }
}

/** P24: every day 00:00 KST (the end of the target day) for the previous KST day. A separate lock lets Monday run both schedules. */
@Component
class DailyReportScheduler(private val service: ReportScheduleService, @Qualifier("reportClock") private val clock: Clock) {
    @Scheduled(cron = "0 0 0 * * *", zone = "Asia/Seoul")
    @SchedulerLock(name = "core-daily-reports", lockAtMostFor = "PT30M", lockAtLeastFor = "PT1M")
    fun generate() {
        LockAssert.assertLocked()
        service.generate(clock.instant().plus(EARLY_RUN_GRACE), ReportPeriodType.DAILY)
    }
}
