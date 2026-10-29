package com.sagomungchi.core.report

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.report.domain.ReportPeriod
import com.sagomungchi.core.report.service.ReportEntitlementService
import org.junit.jupiter.api.Test
import org.springframework.scheduling.support.CronExpression
import java.time.Instant
import java.time.ZonedDateTime
import java.util.UUID
import kotlin.test.*

class ReportPeriodTest {
    @Test fun `previous week uses KST midnight across UTC and year boundaries`() {
        val cases = mapOf(
            "2026-10-25T14:59:59Z" to "2026-10-12",
            "2026-10-25T15:00:00Z" to "2026-10-19",
            "2026-10-25T22:00:00Z" to "2026-10-19",
            "2026-01-04T22:00:00Z" to "2025-12-29",
            "2024-03-03T22:00:00Z" to "2024-02-26")
        cases.forEach { (at, from) ->
            val period = ReportPeriod.previousWeek(Instant.parse(at))
            assertEquals(from, period.from.toString()); assertEquals(period.from.plusDays(6), period.to)
            val start = period.from.atStartOfDay(ReportPeriod.ZONE).toInstant()
            val end = period.to.plusDays(1).atStartOfDay(ReportPeriod.ZONE).toInstant()
            assertEquals(7 * 86400L, end.epochSecond - start.epochSecond)
        }
    }
    @Test fun `cron fires only next Monday at 0700 KST`() {
        val cron = CronExpression.parse("0 0 7 * * MON")
        val before = ZonedDateTime.parse("2026-10-26T06:59:59+09:00[Asia/Seoul]")
        val first = cron.next(before)!!
        assertEquals("2026-10-26T07:00+09:00[Asia/Seoul]", first.toString())
        assertEquals(first.plusWeeks(1), cron.next(first))
    }
    @Test fun `missing product provider fails explicitly rather than inventing a plan`() {
        val error = assertFailsWith<BusinessException> { ReportEntitlementService().narrativeEnabled(UUID.randomUUID()) }
        assertEquals(503, error.status.value()); assertEquals("REPORT_ENTITLEMENT_UNAVAILABLE", error.code)
    }
}
