package com.sagomungchi.core.report

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.messaging.OutboxRelay
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.payment.client.PremiumUsageClient
import com.sagomungchi.core.payment.service.RefundService
import com.sagomungchi.core.report.service.ReportEntitlementService
import com.sagomungchi.core.report.service.ReportJobService
import com.sun.net.httpserver.HttpServer
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.ArgumentMatchers.any
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.context.annotation.Import
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import java.net.InetSocketAddress
import java.time.Clock
import java.time.Instant
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.test.*

/** Real product/subscription, authorization, transactions and Outbox; only report HTTP and usage evidence are doubles. */
@AutoConfigureMockMvc
@Import(ReportHttpTest.HttpTransactionProbe::class)
@TestPropertySource(properties = ["spring.rabbitmq.listener.simple.auto-startup=false",
    "app.payment.free-product-id=00000000-0000-4000-8000-000000000129"])
class ReportEntitlementIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var entitlement: ReportEntitlementService
    @Autowired lateinit var jobs: ReportJobService
    @Autowired lateinit var refunds: RefundService
    @MockitoBean lateinit var outboxRelay: OutboxRelay
    @MockitoBean lateinit var usage: PremiumUsageClient
    @MockitoBean(name = "paymentClock") lateinit var clock: Clock

    companion object {
        private val free = UUID.fromString("00000000-0000-4000-8000-000000000129")
        private data class Request(val path: String, val narrative: String?, val scope: String?)
        private val requests = CopyOnWriteArrayList<Request>()
        @Volatile private var detail = "{}"
        @Volatile private var duringRequest: ((String) -> Unit)? = null
        private val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
            createContext("/internal/reports") { exchange ->
                val path = exchange.requestURI.path
                val flag = exchange.requestHeaders.getFirst("X-Report-Narrative-Enabled")
                requests.add(Request(path, flag, exchange.requestHeaders.getFirst("X-Student-Scope")))
                try {
                    duringRequest?.invoke(path)
                    // Deliberately return full detail even for false to exercise core's final free projection.
                    val body = if (path.contains("/files/"))
                        """{"url":"https://storage.example.test/${if (flag == "true") "full" else "free"}","expiresAt":"2026-11-01T01:00:00Z"}"""
                    else detail
                    val bytes = body.toByteArray(Charsets.UTF_8)
                    exchange.responseHeaders.set("Content-Type", "application/json")
                    exchange.sendResponseHeaders(200, bytes.size.toLong())
                    exchange.responseBody.use { it.write(bytes) }
                } catch (error: Throwable) {
                    exchange.sendResponseHeaders(500, -1)
                    exchange.close()
                    throw error
                }
            }
            start()
        }
        @JvmStatic @DynamicPropertySource fun reportUrl(registry: DynamicPropertyRegistry) {
            registry.add("app.services.report") { "http://127.0.0.1:${server.address.port}" }
        }
        @JvmStatic @AfterAll fun stop() { server.stop(0) }
    }

    private lateinit var owner: UUID
    private lateinit var student: UUID
    private lateinit var report: UUID
    private lateinit var bearer: String
    private lateinit var premium: UUID
    private var at = Instant.parse("2026-10-29T01:00:00Z")

    @BeforeEach fun prepare() {
        at = Instant.parse("2026-10-29T01:00:00Z")
        `when`(clock.instant()).thenAnswer { at }
        owner = parent(jdbc); student = child(jdbc, owner)
        report = completedJob(jdbc, student).second
        bearer = tokens.access(session(jdbc, owner, "PARENT"))
        premium = UUID.randomUUID()
        product(free, false); product(premium, true)
        requests.clear(); duringRequest = null
        detail = json.writeValueAsString(mapOf(
            "reportId" to report, "childId" to student, "period" to WEEK, "status" to "COMPLETED", "revision" to 1,
            "narrative" to mapOf("text" to "합성 서술"), "eveningQuestion" to "합성 질문",
            "metrics" to listOf(mapOf("count" to 3)), "thinkingTypes" to listOf(mapOf("count" to 2, "summary" to "합성 요약"))))
    }

    private fun product(id: UUID, paid: Boolean) {
        jdbc.update("""INSERT INTO product(id,code,name,price,billing_cycle,child_limit,features,limits,active,created_at)
            VALUES(?,?,?,?,'MONTHLY',1,'{}',?::jsonb,true,now())
            ON CONFLICT(id) DO UPDATE SET limits=excluded.limits,active=true""", id, "issue129-$id", "합성 상품",
            if (paid) 14900 else 0, """{"dailyConversations":${if (paid) 30 else 0},"reportNarrative":$paid}""")
    }

    private fun subscribe(): UUID {
        val id = UUID.randomUUID()
        val snapshot = json.writeValueAsString(mapOf("id" to premium, "code" to "issue129-$premium", "name" to "합성 상품",
            "price" to 14900, "billingCycle" to "MONTHLY", "childLimit" to 1, "features" to emptyMap<String, Any>(),
            "limits" to mapOf("dailyConversations" to 30, "reportNarrative" to true), "active" to true))
        jdbc.update("""INSERT INTO subscription(id,parent_user_id,student_id,product_id,status,period_start,period_end,
            auto_renew,created_at,updated_at,product_snapshot,revision)
            VALUES(?,?,?,?,'ACTIVE','2026-10-28','2026-11-28',false,now(),now(),?::jsonb,0)""",
            id, owner, student, premium, snapshot)
        return id
    }

    private fun used() = jdbc.queryForObject("SELECT count(*) FROM payment_premium_usage WHERE student_id=? AND status='USED'", Int::class.java, student)
    private fun views() = jdbc.queryForObject("SELECT count(*) FROM report_view WHERE user_id=?", Int::class.java, owner)
    private fun read() = mvc.get("/api/v1/reports/$report") {
        header("Authorization", "Bearer $bearer"); header("X-Report-Narrative-Enabled", "true")
    }
    private fun download(format: String = "pdf") = mvc.get("/api/v1/reports/$report/download?format=$format") {
        header("Authorization", "Bearer $bearer"); header("X-Report-Narrative-Enabled", "true")
    }

    @Test fun `free client cannot forge entitlement and receives numeric detail and free pdf md`() {
        read().andExpect { status { isOk() }; jsonPath("$.narrative") { value(null) }
            jsonPath("$.eveningQuestion") { value(null) }; jsonPath("$.thinkingTypes[0].summary") { doesNotExist() }
            jsonPath("$.thinkingTypes[0].count") { value(2) }; jsonPath("$.metrics[0].count") { value(3) } }
        listOf("pdf", "md").forEach { download(it).andExpect { status { isOk() }; jsonPath("$.url") { value("https://storage.example.test/free") } } }
        assertTrue(requests.all { it.narrative == "false" && it.scope == student.toString() })
        assertEquals(0, used()); assertEquals(3, views())
    }

    @Test fun `premium receives full detail and exact returned revision file with usage recorded`() {
        subscribe()
        val actual = UUID.randomUUID()
        detail = detail.replace(report.toString(), actual.toString())
        read().andExpect { status { isOk() }; jsonPath("$.narrative.text") { value("합성 서술") }
            jsonPath("$.thinkingTypes[0].summary") { value("합성 요약") } }
        download().andExpect { status { isOk() }; jsonPath("$.url") { value("https://storage.example.test/full") } }
        assertEquals("/internal/reports/$actual/files/pdf", requests.last().path)
        assertTrue(requests.all { it.narrative == "true" })
        assertEquals(1, used()); assertEquals(2, views())
    }

    @Test fun `entitlement loss during detail removes every AI field and records no premium usage`() {
        subscribe()
        duringRequest = { jdbc.update("UPDATE subscription SET status='CANCELED' WHERE student_id=?", student) }
        read().andExpect { status { isOk() }; jsonPath("$.narrative") { value(null) }
            jsonPath("$.eveningQuestion") { value(null) }; jsonPath("$.thinkingTypes[0].summary") { doesNotExist() } }
        assertEquals("true", requests.single().narrative); assertEquals(0, used()); assertEquals(1, views())
    }

    @Test fun `upgrade during a free request never records premium usage or returns a full file`() {
        duringRequest = { duringRequest = null; subscribe() }
        read().andExpect { status { isOk() }; jsonPath("$.narrative") { value(null) } }
        assertEquals(0, used())
        jdbc.update("UPDATE subscription SET status='CANCELED' WHERE student_id=?", student)
        duringRequest = { path -> if (path.contains("/files/")) { duringRequest = null; subscribe() } }
        download().andExpect { status { isOk() }; jsonPath("$.url") { value("https://storage.example.test/free") } }
        assertEquals(0, used()); assertEquals(2, views())
    }

    @Test fun `refund while full file is being signed blocks URL and usage at final parent lock`() {
        val sub = subscribe(); val order = UUID.randomUUID(); val payment = UUID.randomUUID()
        jdbc.update("""INSERT INTO payment_order(id,order_no,parent_user_id,student_id,product_id,subscription_id,kind,amount,created_at,product_snapshot)
            VALUES(?,?,?,?,?,?,'INITIAL',14900,now(),(SELECT product_snapshot FROM subscription WHERE id=?))""", order, "issue129-$order", owner, student, premium, sub, sub)
        jdbc.update("""INSERT INTO payment(id,order_id,amount,status,approved_at,updated_at,entitlement_status)
            VALUES(?,?,14900,'APPROVED','2026-10-28T01:00:00Z',now(),'APPLIED')""", payment, order)
        jdbc.update("""INSERT INTO payment_charge_attempt(id,order_id,attempt_no,pg_order_no,idempotency_key,status,started_at,updated_at)
            VALUES(?,?,0,?,?,'APPROVED',now(),now())""", UUID.randomUUID(), order, "issue129-$order", UUID.randomUUID())
        `when`(usage.used(any(UUID::class.java) ?: UUID(0, 0), any(OffsetDateTime::class.java) ?: OffsetDateTime.MIN)).thenReturn(false)
        duringRequest = { path -> if (path.contains("/files/")) { duringRequest = null; refunds.request(owner, payment, "합성 환불") } }
        download().andExpect { status { isForbidden() }; jsonPath("$.code") { value("REPORT_PREMIUM_REQUIRED") }; jsonPath("$.url") { doesNotExist() } }
        assertTrue(requests.all { it.narrative == "true" }); assertEquals(0, used()); assertEquals(0, views())
    }

    @Test fun `real provider preserves grace and ends entitlement after grace or paid period`() {
        subscribe(); assertTrue(entitlement.narrativeEnabled(student))
        at = Instant.parse("2026-11-28T01:00:00Z")
        assertFalse(entitlement.narrativeEnabled(student))
        jdbc.update("UPDATE subscription SET status='RENEWAL_FAILED',grace_until='2026-12-01' WHERE student_id=?", student)
        assertTrue(entitlement.narrativeEnabled(student))
        at = Instant.parse("2026-12-01T00:00:01Z")
        assertFalse(entitlement.narrativeEnabled(student))
    }

    @Test fun `scheduled and regenerated commands use real product flag in atomic job and outbox`() {
        for (paid in listOf(false, true)) {
            if (paid) subscribe()
            val week = com.sagomungchi.core.report.domain.ReportPeriod(WEEK.from.minusWeeks(if (paid) 2 else 1), WEEK.to.minusWeeks(if (paid) 2 else 1))
            val job = jobs.scheduled(owner, student, week)!!
            assertNull(jobs.scheduled(owner, student, week))
            assertCommand(job.jobId, paid)
            val source = completedJob(jdbc, student, com.sagomungchi.core.report.domain.ReportPeriod(week.from.minusWeeks(10), week.to.minusWeeks(10))).second
            val result = mvc.post("/api/v1/reports/$source/regenerate") { header("Authorization", "Bearer $bearer") }
                .andExpect { status { isAccepted() } }.andReturn().response.contentAsString
            assertCommand(UUID.fromString(json.readTree(result)["jobId"].asText()), paid)
        }
    }

    @Test fun `missing free product fails reads and generation without HTTP view job or outbox`() {
        jdbc.update("UPDATE product SET active=false WHERE id=?", free)
        try {
            read().andExpect { status { isServiceUnavailable() }; jsonPath("$.code") { value("PAYMENT_FREE_PRODUCT_UNAVAILABLE") } }
            download().andExpect { status { isServiceUnavailable() } }
            assertEquals("PAYMENT_FREE_PRODUCT_UNAVAILABLE", assertFailsWith<BusinessException> {
                jobs.scheduled(owner, student, com.sagomungchi.core.report.domain.ReportPeriod(WEEK.from.minusWeeks(1), WEEK.to.minusWeeks(1)))
            }.code)
            mvc.post("/api/v1/reports/$report/regenerate") { header("Authorization", "Bearer $bearer") }.andExpect { status { isServiceUnavailable() } }
            assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM report_job WHERE student_id=?", Int::class.java, student))
            assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE subject=?", Int::class.java, student.toString()))
            assertTrue(requests.isEmpty()); assertEquals(0, views())
        } finally { jdbc.update("UPDATE product SET active=true WHERE id=?", free) }
    }

    @Test fun `malformed product entitlement fails explicitly instead of returning free content`() {
        subscribe()
        jdbc.update("UPDATE subscription SET product_snapshot=jsonb_set(product_snapshot,'{limits,reportNarrative}','null') WHERE student_id=?", student)
        read().andExpect { status { isServiceUnavailable() }; jsonPath("$.code") { value("PAYMENT_PRODUCT_UNAVAILABLE") } }
        assertTrue(requests.isEmpty()); assertEquals(0, views())
    }

    private fun assertCommand(job: UUID, paid: Boolean) {
        val envelope = json.readTree(jdbc.queryForObject("SELECT payload::text FROM outbox_event WHERE subject=? AND payload->'data'->>'jobId'=?", String::class.java, student.toString(), job.toString()))
        assertEquals(paid, envelope["data"]["narrativeEnabled"].booleanValue())
        assertEquals("QUEUED", jdbc.queryForObject("SELECT status FROM report_job WHERE id=?", String::class.java, job))
    }
}
