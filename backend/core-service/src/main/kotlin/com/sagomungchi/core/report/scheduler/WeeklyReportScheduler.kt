package com.sagomungchi.core.report.scheduler

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

@Configuration
@EnableSchedulerLock(defaultLockAtMostFor = "PT30M")
class ReportScheduleConfiguration {
    @Bean fun reportClock(): Clock = Clock.systemUTC()
    @Bean fun reportLockProvider(jdbc: JdbcTemplate): LockProvider = JdbcTemplateLockProvider(
        JdbcTemplateLockProvider.Configuration.builder().withJdbcTemplate(jdbc).usingDbTime().build())
}

@Component
class WeeklyReportScheduler(private val service: ReportScheduleService, @Qualifier("reportClock") private val clock: Clock) {
    @Scheduled(cron = "0 0 7 * * MON", zone = "Asia/Seoul")
    @SchedulerLock(name = "core-weekly-reports", lockAtMostFor = "PT30M", lockAtLeastFor = "PT1M")
    fun generate() {
        LockAssert.assertLocked()
        service.generate(clock.instant())
    }
}
