package com.sagomungchi.core.report

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.report.domain.ReportPeriod
import com.sagomungchi.core.report.domain.ReportPeriodType
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
    @Test fun `daily cron fires every day at 0700 KST`() {
        val cron = CronExpression.parse("0 0 7 * * *")
        val first = cron.next(ZonedDateTime.parse("2026-10-31T07:00:00+09:00[Asia/Seoul]"))!!
        assertEquals("2026-11-01T07:00+09:00[Asia/Seoul]", first.toString())
        assertEquals(first.plusDays(1), cron.next(first))
    }
    @Test fun `missing product provider fails explicitly rather than inventing a plan`() {
        val provider=org.mockito.Mockito.mock(com.sagomungchi.core.payment.service.ProductEntitlementService::class.java)
        val student=UUID.randomUUID()
        org.mockito.Mockito.`when`(provider.forStudent(student)).thenThrow(BusinessException(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE,"PAYMENT_FREE_PRODUCT_UNAVAILABLE","상품 설정이 필요합니다."))
        val error = assertFailsWith<BusinessException> { ReportEntitlementService(provider).narrativeEnabled(student) }
        assertEquals(503, error.status.value()); assertEquals("PAYMENT_FREE_PRODUCT_UNAVAILABLE", error.code)
    }
}
