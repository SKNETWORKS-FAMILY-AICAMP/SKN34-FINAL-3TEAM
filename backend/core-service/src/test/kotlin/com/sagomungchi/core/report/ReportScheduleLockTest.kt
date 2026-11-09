package com.sagomungchi.core.report

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.report.domain.ReportPeriodType
import com.sagomungchi.core.report.scheduler.DailyReportScheduler
import com.sagomungchi.core.report.scheduler.WeeklyReportScheduler
import com.sagomungchi.core.report.service.ReportScheduleService
import net.javacrumbs.shedlock.core.LockConfiguration
import net.javacrumbs.shedlock.core.LockProvider
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.test.context.bean.override.mockito.MockitoBean
import java.time.Duration
import java.time.Instant
import java.time.Clock
import kotlin.test.assertTrue

class ReportScheduleLockTest : PostgresRepositoryTest() {
    @Autowired lateinit var scheduler: WeeklyReportScheduler
    @Autowired lateinit var daily: DailyReportScheduler
    @Autowired lateinit var locks: LockProvider
    @MockitoBean lateinit var service: ReportScheduleService
    @MockitoBean(name = "reportClock") lateinit var clock: Clock

    @Test fun `DB lock held by another instance skips and immediate duplicate invocation is also skipped`() {
        val at = Instant.parse("2026-10-25T22:00:00Z")
        `when`(clock.instant()).thenReturn(at)
        val lock = locks.lock(LockConfiguration(Instant.now(), "core-weekly-reports", Duration.ofMinutes(2), Duration.ZERO))
        assertTrue(lock.isPresent)
        try { scheduler.generate(); verifyNoInteractions(service) } finally { lock.get().unlock() }
        scheduler.generate(); scheduler.generate()
        verify(service, times(1)).generate(at, ReportPeriodType.WEEKLY)
    }

    @Test fun `daily schedule has its own lock so Monday runs both and a held daily lock skips only daily`() {
        val at = Instant.parse("2026-10-26T22:00:00Z")
        `when`(clock.instant()).thenReturn(at)
        // The weekly lock may already be held for lockAtLeastFor by the other test; either way it must not block daily.
        val weekly = locks.lock(LockConfiguration(Instant.now(), "core-weekly-reports", Duration.ofMinutes(2), Duration.ZERO))
        try {
            val lock = locks.lock(LockConfiguration(Instant.now(), "core-daily-reports", Duration.ofMinutes(2), Duration.ZERO))
            assertTrue(lock.isPresent)
            try { daily.generate(); verify(service, never()).generate(at, ReportPeriodType.DAILY) } finally { lock.get().unlock() }
            daily.generate(); daily.generate()
            verify(service, times(1)).generate(at, ReportPeriodType.DAILY)
            verify(service, never()).generate(at, ReportPeriodType.WEEKLY)
        } finally { weekly.ifPresent { it.unlock() } }
    }
}
