package com.sagomungchi.core.report

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.report.domain.ReportPeriod
import com.sagomungchi.core.report.domain.ReportPeriodType
import com.sagomungchi.core.report.scheduler.EARLY_RUN_GRACE
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
    @Test fun `cron fires only next Monday at 0000 KST`() {
        val cron = CronExpression.parse("0 0 0 * * MON")
        val before = ZonedDateTime.parse("2026-10-25T23:59:59+09:00[Asia/Seoul]")
        val first = cron.next(before)!!
        assertEquals("2026-10-26T00:00+09:00[Asia/Seoul]", first.toString())
        assertEquals(first.plusWeeks(1), cron.next(first))
    }
    @Test fun `previous day uses the KST date before the run including weekends and year boundaries`() {
        mapOf("2026-10-25T14:59:59Z" to "2026-10-24", "2026-10-25T15:00:00Z" to "2026-10-25",
            "2026-10-25T22:00:00Z" to "2026-10-25", "2026-10-31T22:00:00Z" to "2026-10-31", "2025-12-31T22:00:00Z" to "2025-12-31",
            "2026-02-28T22:00:00Z" to "2026-02-28").forEach { (at, day) ->
            val period = ReportPeriod.previousDay(Instant.parse(at))
            assertEquals(ReportPeriodType.DAILY, period.type); assertEquals(day, period.from.toString()); assertEquals(period.from, period.to)
        }
        assertFailsWith<IllegalArgumentException> { ReportPeriod(java.time.LocalDate.parse("2026-10-19"), java.time.LocalDate.parse("2026-10-20"), ReportPeriodType.DAILY) }
        // A daily period on a Monday is not a week, and a week is never one day.
        assertFailsWith<IllegalArgumentException> { ReportPeriod(java.time.LocalDate.parse("2026-10-19"), java.time.LocalDate.parse("2026-10-19")) }
    }
    @Test fun `daily cron fires every day at 0000 KST`() {
        val cron = CronExpression.parse("0 0 0 * * *")
        val first = cron.next(ZonedDateTime.parse("2026-10-31T00:00:00+09:00[Asia/Seoul]"))!!
        assertEquals("2026-11-01T00:00+09:00[Asia/Seoul]", first.toString())
        assertEquals(first.plusDays(1), cron.next(first))
    }
    @Test fun `a midnight run picks the day and week that just ended even when it fires slightly early or late`() {
        // Monday 2026-10-26 00:00 KST = 2026-10-25T15:00Z. The schedulers add EARLY_RUN_GRACE to the run instant.
        listOf("2026-10-25T14:59:59.900Z", "2026-10-25T15:00:00Z", "2026-10-25T15:00:05Z", "2026-10-25T15:29:00Z").forEach {
            val at = Instant.parse(it).plus(EARLY_RUN_GRACE)
            val day = ReportPeriod.previous(ReportPeriodType.DAILY, at)
            assertEquals("2026-10-25", day.from.toString(), it); assertEquals(day.from, day.to)
            val week = ReportPeriod.previous(ReportPeriodType.WEEKLY, at)
            assertEquals("2026-10-19", week.from.toString(), it); assertEquals("2026-10-25", week.to.toString(), it)
        }
        // A daily run late into the night still targets the day that ended at the preceding midnight.
        assertEquals("2026-10-25", ReportPeriod.previousDay(Instant.parse("2026-10-26T14:58:00Z").plus(EARLY_RUN_GRACE)).from.toString())
    }
    @Test fun `missing product provider fails explicitly rather than inventing a plan`() {
        val provider=org.mockito.Mockito.mock(com.sagomungchi.core.payment.service.ProductEntitlementService::class.java)
        val student=UUID.randomUUID()
        org.mockito.Mockito.`when`(provider.forStudent(student)).thenThrow(BusinessException(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE,"PAYMENT_FREE_PRODUCT_UNAVAILABLE","상품 설정이 필요합니다."))
        val error = assertFailsWith<BusinessException> { ReportEntitlementService(provider).narrativeEnabled(student) }
        assertEquals(503, error.status.value()); assertEquals("PAYMENT_FREE_PRODUCT_UNAVAILABLE", error.code)
    }
}
