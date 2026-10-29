package com.sagomungchi.core.report.scheduler

import com.sagomungchi.core.report.service.ReportRecoveryService
import net.javacrumbs.shedlock.core.LockAssert
import net.javacrumbs.shedlock.spring.annotation.SchedulerLock
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component

@Component
class ReportRecoveryScheduler(private val service: ReportRecoveryService) {
    @Scheduled(fixedDelayString = "\${app.report.recovery.interval:PT1M}")
    @SchedulerLock(name = "core-report-recovery", lockAtMostFor = "PT30M")
    fun recover() {
        LockAssert.assertLocked()
        service.recover()
    }
}
