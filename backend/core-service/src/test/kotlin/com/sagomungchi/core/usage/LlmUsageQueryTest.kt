package com.sagomungchi.core.usage

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.messaging.EventEnvelope
import com.sagomungchi.core.usage.domain.LlmUsageRecorded
import com.sagomungchi.core.usage.domain.CallType
import com.sagomungchi.core.usage.domain.UsageGroupBy
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.session
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core.usage.repository.LlmUsageRepository
import com.sagomungchi.core.usage.service.LlmCallMetrics
import com.sagomungchi.core.usage.service.LlmCostMetrics
import com.sagomungchi.core.usage.service.LlmUsageService
import io.opentelemetry.sdk.metrics.SdkMeterProvider
import io.opentelemetry.sdk.testing.exporter.InMemoryMetricReader
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.test.context.TestPropertySource
import java.math.BigDecimal
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneOffset
import kotlin.test.*

@TestPropertySource(properties = ["app.llm-pricing.query-model.input=3", "app.llm-pricing.query-model.output=15"])
@AutoConfigureMockMvc
class LlmUsageQueryTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var usage: LlmUsageService
    @Autowired lateinit var repository: LlmUsageRepository
    @Autowired lateinit var properties: AppProperties
    private val day = LocalDate.parse("2026-11-12")
    private fun event(time: String, type: String = "JUDGMENT", success: Boolean = true,
                      model: String = "query-model", latency: Int = 100, input: Int? = 1000,
                      output: Int? = 2000, prompt: String? = "judge@1",
                      errorCode: String? = if (success) null else "TIMEOUT") = EventEnvelope(
        type = "llm.usage.recorded", source = "ai-service", dataschema = "llm.usage.recorded.v1",
        data = LlmUsageRecorded("ai", type, model, prompt, input, output, latency,
            success, errorCode, OffsetDateTime.parse(time)))

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

    @Test fun `priced model with any missing token count stores null cost instead of an undercount`() {
        usage.record(event("2026-11-12T01:00:00Z", input = null))
        usage.record(event("2026-11-12T02:00:00Z", output = null))
        val summary = usage.summarize(day, day, null).single()
        assertNull(summary.costUsd)
        assertEquals(2L, summary.unpricedCalls)
    }

    @Test fun `every existing call type can be queried and empty ranges stay empty`() {
        CallType.entries.forEach { usage.record(event("2026-11-12T01:00:00Z", it.name)) }
        assertEquals(CallType.entries.size, usage.summarize(day, day, null).size)
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

    @Test fun `month to date starts at KST month start and counts unpriced calls separately`() {
        usage.record(event("2026-10-31T14:59:59.999999Z"))
        usage.record(event("2026-10-31T15:00:00Z"))
        usage.record(event("2026-11-12T01:00:00Z", model = "unregistered"))
        usage.record(event("2026-11-12T02:00:00Z", input = null))
        usage.record(event("2026-11-12T02:30:00Z"))
        val cost = usage.monthToDate(Instant.parse("2026-11-12T02:30:00Z"))
        assertEquals(0, BigDecimal("0.033").compareTo(cost.pricedUsd))
        assertEquals(2L, cost.unpricedCalls)
        val empty = usage.monthToDate(Instant.parse("2026-10-31T15:00:00Z"))
        assertEquals(0, BigDecimal.ZERO.compareTo(empty.pricedUsd))
        assertEquals(0L, empty.unpricedCalls)
    }

    @Test fun `cost metrics export the current KST month through OpenTelemetry`() {
        val now = OffsetDateTime.now(ZoneOffset.UTC).minusSeconds(1).toString()
        usage.record(event(now))
        usage.record(event(now, model = "unregistered"))
        val reader = InMemoryMetricReader.create()
        val provider = SdkMeterProvider.builder().registerMetricReader(reader).build()
        val metrics = LlmCostMetrics(usage, provider.get("test"))
        val exported = reader.collectAllMetrics().associateBy { it.name }
        assertEquals(0.033, exported.getValue("llm.usage.month_to_date.priced_cost").doubleGaugeData.points.single().value, 1e-9)
        assertEquals(1L, exported.getValue("llm.usage.month_to_date.unpriced_calls").longGaugeData.points.single().value)
        metrics.close()
        provider.close()
    }

    @Test fun `call metrics record a new event once and skip redelivered duplicates (#1028)`() {
        val reader = InMemoryMetricReader.create()
        val provider = SdkMeterProvider.builder().registerMetricReader(reader).build()
        val service = LlmUsageService(repository, properties, LlmCallMetrics(provider.get("test")))
        val first = event("2026-11-12T01:00:00Z", latency = 1500)
        service.record(first)
        service.record(first)
        service.record(event("2026-11-12T01:00:01Z", "FOLLOWUP", success = false, latency = 21000, input = null, output = null))
        val exported = reader.collectAllMetrics().associateBy { it.name }
        val durations = exported.getValue("llm.call.duration").histogramData.points.associateBy { it.attributes.asMap().entries.associate { (k, v) -> k.key to v.toString() } }
        val judgment = durations.getValue(mapOf("call_type" to "JUDGMENT", "model" to "query-model",
            "prompt_version" to "judge@1", "outcome" to "success", "error_code" to "none"))
        assertEquals(1L, judgment.count)
        assertEquals(1.5, judgment.sum, 1e-9)
        val followup = durations.getValue(mapOf("call_type" to "FOLLOWUP", "model" to "query-model",
            "prompt_version" to "judge@1", "outcome" to "error", "error_code" to "TIMEOUT"))
        assertEquals(1L, followup.count)
        // 21초는 20~25초 버킷에 들어가 p95 20초 경보선을 가른다
        assertTrue(followup.boundaries.containsAll(listOf(12.0, 20.0)))
        assertEquals(2, durations.size)
        val tokens = exported.getValue("llm.call.tokens").longSumData.points.associate {
            it.attributes.asMap().entries.associate { (k, v) -> k.key to v.toString() } to it.value }
        // 토큰 없는 FOLLOWUP 호출은 세지 않고, 재전달 중복도 더하지 않는다
        assertEquals(mapOf(
            mapOf("call_type" to "JUDGMENT", "model" to "query-model", "direction" to "input") to 1000L,
            mapOf("call_type" to "JUDGMENT", "model" to "query-model", "direction" to "output") to 2000L,
        ), tokens)
        provider.close()
    }

    @Test fun `shipped application yml prices dotted model names and bills Veo externally`() {
        // application.yml 기본 단가(#651)가 '.'·'-' 모델명 키 그대로 읽히는지, 테스트 단가와 합쳐지는지
        usage.record(event("2026-11-12T01:00:00Z", "JUDGMENT", model = "gpt-6-luna"))
        usage.record(event("2026-11-12T01:00:00Z", "THEME_DRAFT", model = "gpt-6.1-terra"))
        usage.record(event("2026-11-12T01:00:00Z", "KNOWLEDGE_EMBEDDING", model = "text-embedding-3-small", output = 0))
        usage.record(event("2026-11-12T01:00:00Z", "THEME_IMAGE", model = "gpt-image-2.6-sunburst"))
        usage.record(event("2026-11-12T01:00:00Z", "THEME_VIDEO", model = "veo-3.1-fast-generate-001",
            input = null, output = null))
        val byType = usage.summarize(day, day, null).associateBy { it.callType }
        // 입력 1000·출력 2000 토큰, 100만 토큰당 USD
        assertEquals(0, BigDecimal("0.0011").compareTo(byType.getValue("JUDGMENT").costUsd))
        assertEquals(0, BigDecimal("0.011").compareTo(byType.getValue("THEME_DRAFT").costUsd))
        assertEquals(0, BigDecimal("0.00002").compareTo(byType.getValue("KNOWLEDGE_EMBEDDING").costUsd))
        assertEquals(0, BigDecimal("0.068").compareTo(byType.getValue("THEME_IMAGE").costUsd))
        // #764: Veo는 단가 대신 GCP 별도 청구라 비용 합계·미산정에서 빠지고 따로 센다
        assertEquals(0, BigDecimal.ZERO.compareTo(byType.getValue("THEME_VIDEO").costUsd))
        assertEquals(0L, byType.getValue("THEME_VIDEO").unpricedCalls)
        assertEquals(1L, byType.getValue("THEME_VIDEO").externallyBilledCalls)
        val month = usage.monthToDate(Instant.parse("2026-11-12T02:00:00Z"))
        assertEquals(0, BigDecimal("0.08012").compareTo(month.pricedUsd))
        assertEquals(0L, month.unpricedCalls)
    }

    @Test fun `zero priced in-cluster models store zero cost without tokens for any registry version (#764)`() {
        // scoring M2는 토큰 null, 모델명은 레지스트리 이름@버전. application.yml은 이름만 0 단가로 등록
        usage.record(event("2026-11-12T01:00:00Z", "M2", model = "m2-klue-essay@3.1-1112b", input = null, output = null))
        usage.record(event("2026-11-12T01:00:00Z", "M2", model = "m2-klue-narrative@9.9-new", input = null, output = null))
        val row = usage.summarize(day, day, CallType.M2).single()
        assertEquals(0, BigDecimal.ZERO.compareTo(row.costUsd))
        assertEquals(0L, row.unpricedCalls)
        assertEquals(0L, row.externallyBilledCalls)
        assertEquals(0L, usage.monthToDate(Instant.parse("2026-11-12T02:00:00Z")).unpricedCalls)
    }

    @Test fun `externally billed models are separated from unpriced calls while unknown models still count (#764)`() {
        // RunPod Gemma(정확한 이름·@버전 둘 다)는 별도 청구, 같은 call type의 미등록 모델은 여전히 미산정
        usage.record(event("2026-11-12T01:00:00Z", "REPORT_EXPLANATION", model = "gemma-4-26b-a4b-it-qat-awq-int4"))
        usage.record(event("2026-11-12T01:00:00Z", "REPORT_EXPLANATION", model = "gemma-4-26b-a4b-it-qat-awq-int4@local"))
        usage.record(event("2026-11-12T01:00:00Z", "REPORT_EXPLANATION", model = "unregistered-sllm"))
        val row = usage.summarize(day, day, CallType.REPORT_EXPLANATION).single()
        assertEquals(3L, row.calls)
        assertNull(row.costUsd)
        assertEquals(1L, row.unpricedCalls)
        assertEquals(2L, row.externallyBilledCalls)
        val month = usage.monthToDate(Instant.parse("2026-11-12T02:00:00Z"))
        assertEquals(0, BigDecimal.ZERO.compareTo(month.pricedUsd))
        assertEquals(1L, month.unpricedCalls)
    }

    @Test fun `versioned model names fall back to the registered name price`() {
        // 단가 표에 없는 이름@버전은 @ 앞 이름의 단가로 계산
        usage.record(event("2026-11-12T01:00:00Z", model = "query-model@2"))
        usage.record(event("2026-11-12T01:00:00Z", "FOLLOWUP", model = "gpt-6-luna@x"))
        val byType = usage.summarize(day, day, null).associateBy { it.callType }
        assertEquals(0, BigDecimal("0.033").compareTo(byType.getValue("JUDGMENT").costUsd))
        assertEquals(0, BigDecimal("0.0011").compareTo(byType.getValue("FOLLOWUP").costUsd))
    }

    @Test fun `memory query rewrite usage is stored and priced with the default ai model`() {
        // #680: ai 질의 변환(#681)은 기본 모델 gpt-6-luna(#651 단가 입력 0.10·출력 0.50 USD/100만 토큰)로 MEMORY_QUERY를 발행한다
        usage.record(event("2026-11-12T01:00:00Z", "MEMORY_QUERY", model = "gpt-6-luna", input = 300, output = 60))
        val row = usage.summarize(day, day, CallType.MEMORY_QUERY).single()
        assertEquals("MEMORY_QUERY", row.callType)
        assertEquals(1L, row.calls)
        assertEquals(0, BigDecimal("0.00006").compareTo(row.costUsd))
        assertEquals(0L, row.unpricedCalls)
    }

    @Test fun `p50 and p95 are continuous percentiles over successes and failures (#1051)`() {
        listOf(100, 200, 300, 400).forEach { usage.record(event("2026-11-12T01:00:00Z", latency = it)) }
        usage.record(event("2026-11-12T01:00:00Z", success = false, latency = 1000))
        usage.record(event("2026-11-12T01:00:00Z", "FOLLOWUP", latency = 50))
        val byType = usage.summarize(day, day, null).associateBy { it.callType }
        val judgment = byType.getValue("JUDGMENT")
        assertEquals("JUDGMENT", judgment.key)
        assertEquals(0, BigDecimal("400").compareTo(judgment.latencyMs))
        assertEquals(0, BigDecimal("300").compareTo(judgment.p50LatencyMs))
        // 위치 0.95 × (5 - 1) = 3.8 → 400 + 0.8 × (1000 - 400)
        assertEquals(0, BigDecimal("880").compareTo(judgment.p95LatencyMs))
        val followup = byType.getValue("FOLLOWUP")
        assertEquals(0, BigDecimal("50").compareTo(followup.p50LatencyMs))
        assertEquals(0, BigDecimal("50").compareTo(followup.p95LatencyMs))
    }

    @Test fun `every groupBy groups by its own key, keeps the callType filter and leaves callType null (#1051)`() {
        // 11/12 00:00 KST 직전·직후 경계로 DAY 묶음이 KST 날짜를 따르는지 본다
        usage.record(event("2026-11-11T14:59:59.999999Z", latency = 100, model = "model-a"))
        usage.record(event("2026-11-11T15:00:00Z", latency = 200, model = "model-b", prompt = "judge@2"))
        usage.record(event("2026-11-12T01:00:00Z", success = false, latency = 300, model = "model-b", prompt = null))
        usage.record(event("2026-11-12T02:00:00Z", success = false, latency = 400, model = "model-b", errorCode = null))
        usage.record(event("2026-11-12T03:00:00Z", "FOLLOWUP", latency = 500, model = "model-c", prompt = "followup@1"))
        val from = day.minusDays(1)
        fun keys(groupBy: UsageGroupBy, type: CallType? = null) =
            usage.summarize(from, day, type, groupBy).map { Triple(it.key, it.calls, it.failures) }
        assertEquals(listOf(Triple("FOLLOWUP", 1L, 0L), Triple("JUDGMENT", 4L, 2L)), keys(UsageGroupBy.CALL_TYPE))
        assertEquals(listOf(Triple("model-a", 1L, 0L), Triple("model-b", 3L, 2L), Triple("model-c", 1L, 0L)), keys(UsageGroupBy.MODEL))
        assertEquals(listOf(Triple("followup@1", 1L, 0L), Triple("judge@1", 2L, 1L), Triple("judge@2", 1L, 0L), Triple(null, 1L, 1L)),
            keys(UsageGroupBy.PROMPT_VERSION))
        // 성공 호출과 코드 없는 실패는 key null 한 묶음
        assertEquals(listOf(Triple("TIMEOUT", 1L, 1L), Triple(null, 4L, 1L)), keys(UsageGroupBy.ERROR_CODE))
        assertEquals(listOf(Triple("2026-11-11", 1L, 0L), Triple("2026-11-12", 4L, 2L)), keys(UsageGroupBy.DAY))
        assertEquals(listOf(Triple("2026-11-11", 1L, 0L), Triple("2026-11-12", 3L, 2L)), keys(UsageGroupBy.DAY, CallType.JUDGMENT))
        assertEquals(listOf(Triple("model-c", 1L, 0L)), keys(UsageGroupBy.MODEL, CallType.FOLLOWUP))
        UsageGroupBy.entries.filter { it != UsageGroupBy.CALL_TYPE }.forEach { groupBy ->
            assertTrue(usage.summarize(from, day, null, groupBy).all { it.callType == null }, groupBy.name)
        }
        val model = usage.summarize(from, day, null, UsageGroupBy.MODEL).single { it.key == "model-b" }
        assertEquals(0, BigDecimal("300").compareTo(model.p50LatencyMs))
        assertEquals(0, BigDecimal("390").compareTo(model.p95LatencyMs))
        val error = assertFailsWith<BusinessException> { usage.summarize(day, day.plusDays(366), null, UsageGroupBy.DAY) }
        assertEquals("VALIDATION_FAILED", error.code)
    }

    @Test fun `HTTP groupBy defaults to CALL_TYPE, returns the chosen grouping and rejects other values with 400 (#1051)`() {
        val access = tokens.access(session(jdbc, account(jdbc)))
        usage.record(event("2026-11-12T01:00:00Z", latency = 120))
        usage.record(event("2026-11-12T02:00:00Z", latency = 80))
        val path = "/api/v1/admin/ai-usage?from=2026-11-12&to=2026-11-12"
        mvc.get(path) { header("Authorization", "Bearer $access") }.andExpect {
            status { isOk() }; jsonPath("$.groupBy") { value("CALL_TYPE") }
            jsonPath("$.items[0].key") { value("JUDGMENT") }; jsonPath("$.items[0].callType") { value("JUDGMENT") }
            jsonPath("$.items[0].p50LatencyMs") { value(100.0) }; jsonPath("$.items[0].p95LatencyMs") { value(118.0) }
        }
        mvc.get("$path&groupBy=DAY&callType=JUDGMENT") { header("Authorization", "Bearer $access") }.andExpect {
            status { isOk() }; jsonPath("$.groupBy") { value("DAY") }; jsonPath("$.items.length()") { value(1) }
            jsonPath("$.items[0].key") { value("2026-11-12") }; jsonPath("$.items[0].callType") { value(null) }
            jsonPath("$.items[0].calls") { value(2) }
        }
        listOf("day", "call_type", "WEEK", "occurred_at", "MODEL;DROP TABLE llm_usage").forEach { bad ->
            mvc.get(path) { header("Authorization", "Bearer $access"); param("groupBy", bad) }.andExpect {
                status { isBadRequest() }; jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
    }

    @Test fun `reversed periods are rejected`() {
        assertEquals("VALIDATION_FAILED", assertFailsWith<BusinessException> {
            usage.summarize(day.plusDays(1), day, null)
        }.code)
    }
}
