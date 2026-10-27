package com.sagomungchi.core.usage

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.messaging.EventEnvelope
import com.sagomungchi.core.usage.consumer.LlmUsageRecorded
import com.sagomungchi.core.usage.domain.CallType
import com.sagomungchi.core.usage.service.LlmUsageService
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.test.context.TestPropertySource
import java.math.BigDecimal
import java.time.LocalDate
import java.time.OffsetDateTime
import kotlin.test.*

@TestPropertySource(properties = ["app.llm-pricing.query-model.input=3", "app.llm-pricing.query-model.output=15"])
class LlmUsageQueryTest : PostgresRepositoryTest() {
    @Autowired lateinit var usage: LlmUsageService
    private val day = LocalDate.parse("2026-11-12")
    private fun event(time: String, type: String = "JUDGMENT", success: Boolean = true,
                      model: String = "query-model", latency: Int = 100, input: Int? = 1000) = EventEnvelope(
        type = "llm.usage.recorded", source = "ai-service", dataschema = "llm.usage.recorded.v1",
        data = LlmUsageRecorded("ai", type, model, "judge@1", input, 2000, latency,
            success, if (success) null else "TIMEOUT", OffsetDateTime.parse(time)))

    @Test fun `KST inclusive dates exclude adjacent instants and duplicate collection stays idempotent`() {
        val first = event("2026-11-11T15:00:00Z")
        repeat(2) { usage.record(first) }
        usage.record(event("2026-11-12T14:59:59.999999Z", success = false, latency = 300))
        usage.record(event("2026-11-11T14:59:59.999999Z"))
        usage.record(event("2026-11-12T15:00:00Z"))
        usage.record(event("2026-11-12T01:00:00Z", "FOLLOWUP"))
        val summary = usage.summarize(day, day, CallType.JUDGMENT).single()
        assertEquals(2L, summary.calls)
        assertEquals(1L, summary.failures)
        assertEquals(0, BigDecimal("200").compareTo(summary.latencyMs))
        assertEquals(2000L, summary.inputTokens)
        assertEquals(4000L, summary.outputTokens)
        assertEquals(0, BigDecimal("0.066").compareTo(summary.costUsd))
        assertEquals(0L, summary.unpricedCalls)
        assertEquals(listOf("FOLLOWUP", "JUDGMENT"), usage.summarize(day, day, null).map { it.callType })
    }

    @Test fun `mixed unknown cost and tokens remain null instead of reporting incomplete zero totals`() {
        usage.record(event("2026-11-12T01:00:00Z"))
        usage.record(event("2026-11-12T02:00:00Z", model = "unregistered", input = null))
        val summary = usage.summarize(day, day, null).single()
        assertNull(summary.costUsd)
        assertNull(summary.inputTokens)
        assertEquals(4000L, summary.outputTokens)
        assertEquals(1L, summary.unpricedCalls)
    }

    @Test fun `every existing call type can be queried and empty ranges stay empty`() {
        CallType.entries.forEach { usage.record(event("2026-11-12T01:00:00Z", it.name)) }
        assertEquals(7, usage.summarize(day, day, null).size)
        assertTrue(usage.summarize(day.plusDays(1), day.plusDays(2), null).isEmpty())
        CallType.entries.forEach { assertEquals(it.name, usage.summarize(day, day, it).single().callType) }
    }

    @Test fun `366 inclusive days are allowed and the next day is rejected`() {
        val from = LocalDate.parse("2024-01-01")
        assertTrue(usage.summarize(from, from.plusDays(365), null).isEmpty())
        val error = assertFailsWith<BusinessException> { usage.summarize(from, from.plusDays(366), null) }
        assertEquals(400, error.status.value())
        assertEquals("VALIDATION_FAILED", error.code)
    }

    @Test fun `four digit year edges query successfully and extreme years or unbounded ranges return 400`() {
        val earliest = LocalDate.of(1, 1, 1)
        val latest = LocalDate.of(9999, 12, 31)
        assertTrue(usage.summarize(earliest, earliest, null).isEmpty())
        assertTrue(usage.summarize(latest, latest, null).isEmpty())
        listOf(earliest to latest, LocalDate.of(0, 1, 1) to earliest,
            latest to LocalDate.of(10000, 1, 1), LocalDate.MIN to LocalDate.MIN,
            LocalDate.MAX to LocalDate.MAX).forEach { (from, to) ->
            val error = assertFailsWith<BusinessException> { usage.summarize(from, to, null) }
            assertEquals(400, error.status.value())
            assertEquals("VALIDATION_FAILED", error.code)
        }
    }

    @Test fun `reversed periods are rejected`() {
        assertEquals("VALIDATION_FAILED", assertFailsWith<BusinessException> {
            usage.summarize(day.plusDays(1), day, null)
        }.code)
    }
}
