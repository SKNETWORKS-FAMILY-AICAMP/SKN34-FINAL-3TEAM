package com.sagomungchi.core.report

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.messaging.OutboxRelay
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.report.domain.ReportLifecycleEvent
import com.sagomungchi.core.report.domain.ReportJobStatus
import com.sagomungchi.core.report.service.ReportEntitlementService
import com.sagomungchi.core.report.service.ReportLifecycleService
import com.sun.net.httpserver.HttpServer
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.boot.test.context.TestConfiguration
import org.springframework.boot.web.client.RestClientCustomizer
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Import
import org.springframework.http.HttpStatus
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import org.springframework.transaction.support.TransactionSynchronizationManager
import java.net.InetSocketAddress
import java.nio.file.Files
import java.nio.file.Path
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.test.*

/** The provider is a test-only HTTP server. JWT, MVC, client, permissions, repositories and DB are real. */
@AutoConfigureMockMvc
@Import(ReportHttpTest.HttpTransactionProbe::class)
@TestPropertySource(properties = ["spring.rabbitmq.listener.simple.auto-startup=false"])
class ReportHttpTest : IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var lifecycle: ReportLifecycleService
    @MockitoBean lateinit var entitlement: ReportEntitlementService
    @MockitoBean lateinit var outboxRelay: OutboxRelay

    @TestConfiguration
    class HttpTransactionProbe {
        @Bean fun reportTransactionProbe() = RestClientCustomizer { builder ->
            builder.requestInterceptor { request, body, execution ->
                check(!TransactionSynchronizationManager.isActualTransactionActive()) { "External HTTP inside a transaction" }
                execution.execute(request, body)
            }
        }
    }
    companion object {
        private data class Request(val path: String, val query: String?, val scope: String?, val user: String?, val role: String?, val trace: String?, val token: String?)
        private val requests = CopyOnWriteArrayList<Request>()
        @Volatile private var response = "{}"
        @Volatile private var code = 200
        private val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
            createContext("/internal/reports") { exchange ->
                val h = exchange.requestHeaders
                requests.add(Request(exchange.requestURI.path, exchange.requestURI.rawQuery, h.getFirst("X-Student-Scope"),
                    h.getFirst("X-User-Id"), h.getFirst("X-User-Role"), h.getFirst("traceparent"), h.getFirst("X-Internal-Token")))
                val bytes = response.toByteArray(Charsets.UTF_8)
                exchange.responseHeaders.set("Content-Type", "application/json")
                exchange.sendResponseHeaders(code, bytes.size.toLong())
                exchange.responseBody.use { it.write(bytes) }
            }
            start()
        }
        @JvmStatic @DynamicPropertySource fun reportUrl(registry: DynamicPropertyRegistry) {
            registry.add("app.services.report") { "http://127.0.0.1:${server.address.port}" }
        }
        @JvmStatic @AfterAll fun stop() { server.stop(0) }
    }

    private lateinit var user: UUID
    private lateinit var student: UUID
    private lateinit var report: UUID
    private lateinit var token: String
    @BeforeEach fun prepare() {
        user = parent(jdbc); student = child(jdbc, user); child(jdbc, user)
        report = completedJob(jdbc, student).second
        token = tokens.access(session(jdbc, user, "PARENT"))
        requests.clear(); response = "{}"; code = 200
    }

    @Test fun `list narrows scope passes filter and authenticated headers without recording views`() {
        response = json.writeValueAsString(mapOf("items" to listOf(detail())))
        mvc.get("/api/v1/children/$student/reports?status=COMPLETED") {
            header("Authorization", "Bearer $token"); header("traceparent", "00-test-trace")
            header("X-Student-Scope", UUID.randomUUID().toString()); header("X-User-Id", "forged")
        }.andExpect { status { isOk() }; jsonPath("$.items[0].reportId") { value(report.toString()) } }
        val request = requests.single()
        assertEquals("studentId=$student&status=COMPLETED", request.query)
        assertEquals(student.toString(), request.scope); assertEquals(user.toString(), request.user)
        assertEquals("PARENT", request.role); assertEquals("test-token", request.token)
        assertEquals("00-test-trace", request.trace); assertEquals(0, views())
    }

    @Test fun `detail passes revision preserves full payload and records actual returned revision id`() {
        val actualReport = UUID.randomUUID()
        val body = detail(actualReport, revision = 2)
        response = json.writeValueAsString(body)
        val result = mvc.get("/api/v1/reports/$report?revision=2") { header("Authorization", "Bearer $token") }
            .andExpect { status { isOk() }; jsonPath("$.revision") { value(2) }; jsonPath("$.state") { value("NO_RECORD") } }
            .andReturn().response.contentAsString
        assertEquals(json.readTree(response), json.readTree(result))
        assertEquals("revision=2", requests.single().query)
        assertEquals(actualReport, jdbc.queryForObject("SELECT report_id FROM report_view WHERE user_id=?", UUID::class.java, user))
        mvc.get("/api/v1/reports/$report") { header("Authorization", "Bearer $token") }.andExpect { status { isOk() } }
        assertEquals(2, views()); assertNull(requests.last().query)
        val dir = Path.of("build/contracts"); Files.createDirectories(dir)
        Files.writeString(dir.resolve("report-detail.json"), result)
    }

    @Test fun `evidence and pdf md downloads use exact internal routes and do not count as views`() {
        val item = UUID.randomUUID(); response = """{"available":false,"answerId":null}"""
        mvc.get("/api/v1/reports/$report/evidence/$item") { header("Authorization", "Bearer $token") }
            .andExpect { status { isOk() }; jsonPath("$.available") { value(false) } }
        assertEquals("/internal/reports/$report/evidence/$item", requests.single().path)
        response = """{"url":"https://storage.example.test/report?signature=test","expiresAt":"2026-11-01T01:00:00Z"}"""
        listOf("pdf", "md").forEach { format ->
            mvc.get("/api/v1/reports/$report/download?format=$format") { header("Authorization", "Bearer $token") }
                .andExpect { status { isOk() }; jsonPath("$.url") { value("https://storage.example.test/report?signature=test") } }
            assertEquals("/internal/reports/$report/files/$format", requests.last().path)
        }
        assertTrue(requests.all { it.scope == student.toString() }); assertEquals(0, views())
    }

    @Test fun `other guardian and withdrawn guardian cannot list read evidence download or regenerate`() {
        val other = parent(jdbc); val otherToken = tokens.access(session(jdbc, other, "PARENT"))
        assertDenied(otherToken)
        jdbc.update("UPDATE consent SET status='WITHDRAWN',withdrawn_at=CURRENT_TIMESTAMP WHERE student_id=?", student)
        assertDenied(token)
        assertEquals(0, requests.size); assertEquals(0, views())
    }

    @Test fun `anonymous student and administrator cannot read parent reports`() {
        mvc.get("/api/v1/reports/$report").andExpect { status { isUnauthorized() } }
        val studentToken = tokens.access(session(jdbc, user, "STUDENT", student))
        mvc.get("/api/v1/reports/$report") { header("Authorization", "Bearer $studentToken") }.andExpect { status { isForbidden() } }
        val admin = account(jdbc); val adminToken = tokens.access(session(jdbc, admin))
        mvc.get("/api/v1/reports/$report") { header("Authorization", "Bearer $adminToken") }.andExpect { status { isForbidden() } }
        assertTrue(requests.isEmpty())
    }

    @Test fun `new required guardian document blocks existing session through merged child access service`() {
        jdbc.update("""INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at)
            VALUES(?,'GUARDIAN',?,'개정 안내','검증용 개정 본문',true,CURRENT_DATE,CURRENT_TIMESTAMP)""",
            UUID.randomUUID(), UUID.randomUUID().toString())
        assertDenied(token)
        assertTrue(requests.isEmpty()); assertEquals(0, views())
    }

    @Test fun `SERVICE_OPS admin can regenerate repeatedly but other admin permissions cannot`() {
        val ops = account(jdbc); val opsToken = tokens.access(session(jdbc, ops))
        val content = account(jdbc, permission = "CONTENT"); val contentToken = tokens.access(session(jdbc, content))
        mvc.post("/api/v1/reports/$report/regenerate") { header("Authorization", "Bearer $contentToken") }.andExpect { status { isForbidden() } }
        repeat(2) {
            val result = mvc.post("/api/v1/reports/$report/regenerate") { header("Authorization", "Bearer $opsToken") }
                .andExpect { status { isAccepted() }; jsonPath("$.status") { value("QUEUED") } }.andReturn().response.contentAsString
            val job = UUID.fromString(json.readTree(result)["jobId"].asText())
            lifecycle.apply(ReportLifecycleEvent(UUID.randomUUID(), job, student, UUID.randomUUID(), ReportJobStatus.COMPLETED))
        }
        assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM report_job WHERE student_id=? AND trigger='ADMIN_RETRY'", Int::class.java, student))
        assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM job_execution WHERE triggered_by=?", Int::class.java, ops))
        assertEquals(0, views()); assertTrue(requests.isEmpty())
    }

    @Test fun `missing entitlement returns 503 without new job or outbox`() {
        `when`(entitlement.narrativeEnabled(student)).thenThrow(BusinessException(HttpStatus.SERVICE_UNAVAILABLE,
            "REPORT_ENTITLEMENT_UNAVAILABLE", "상품 계약 미연결"))
        mvc.post("/api/v1/reports/$report/regenerate") { header("Authorization", "Bearer $token") }
            .andExpect { status { isServiceUnavailable() }; jsonPath("$.code") { value("REPORT_ENTITLEMENT_UNAVAILABLE") } }
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM report_job WHERE student_id=?", Int::class.java, student))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE subject=?", Int::class.java, student.toString()))
    }

    @Test fun `invalid parameters unknown report provider outage malformed JSON and mismatched child never record view`() {
        listOf("/reports/$report?revision=0", "/reports/$report/download?format=html", "/children/$student/reports?status=UNKNOWN",
            "/children/$student/reports?status=QUEUED").forEach { path ->
            mvc.get("/api/v1$path") { header("Authorization", "Bearer $token") }.andExpect { status { isBadRequest() } }
        }
        mvc.get("/api/v1/reports/${UUID.randomUUID()}") { header("Authorization", "Bearer $token") }.andExpect { status { isNotFound() } }
        assertTrue(requests.isEmpty())
        code = 503
        mvc.get("/api/v1/reports/$report") { header("Authorization", "Bearer $token") }.andExpect { status { isServiceUnavailable() }; jsonPath("$.code") { value("REPORT_UNAVAILABLE") } }
        response = """{"status":503,"code":"DATA_UNAVAILABLE"}"""
        mvc.get("/api/v1/reports/$report/evidence/${UUID.randomUUID()}") { header("Authorization", "Bearer $token") }
            .andExpect { status { isServiceUnavailable() }; jsonPath("$.code") { value("DATA_UNAVAILABLE") } }
        code = 409; response = """{"status":409,"code":"DELETION_IN_PROGRESS"}"""
        mvc.get("/api/v1/children/$student/reports") { header("Authorization", "Bearer $token") }
            .andExpect { status { isConflict() }; jsonPath("$.code") { value("DELETION_IN_PROGRESS") } }
        response = """{"status":409,"code":"OTHER"}"""
        mvc.get("/api/v1/reports/$report") { header("Authorization", "Bearer $token") }.andExpect { status { isServiceUnavailable() }; jsonPath("$.code") { value("REPORT_UNAVAILABLE") } }
        code = 200; response = "not-json"
        mvc.get("/api/v1/reports/$report") { header("Authorization", "Bearer $token") }.andExpect { status { isBadGateway() } }
        response = json.writeValueAsString(detail().toMutableMap().also { it["childId"] = UUID.randomUUID() })
        mvc.get("/api/v1/reports/$report") { header("Authorization", "Bearer $token") }.andExpect { status { isBadGateway() } }
        response = """{"url":"javascript:alert(1)","expiresAt":"2026-11-01T01:00:00Z"}"""
        mvc.get("/api/v1/reports/$report/download?format=pdf") { header("Authorization", "Bearer $token") }.andExpect { status { isBadGateway() } }
        code = 404
        mvc.get("/api/v1/reports/$report") { header("Authorization", "Bearer $token") }.andExpect { status { isNotFound() } }
        assertEquals(0, views())
    }

    private fun assertDenied(bearer: String) {
        listOf("/children/$student/reports", "/reports/$report", "/reports/$report/evidence/${UUID.randomUUID()}", "/reports/$report/download?format=pdf").forEach { path ->
            mvc.get("/api/v1$path") { header("Authorization", "Bearer $bearer") }.andExpect { status { isForbidden() } }
        }
        mvc.post("/api/v1/reports/$report/regenerate") { header("Authorization", "Bearer $bearer") }.andExpect { status { isForbidden() } }
    }
    private fun views() = jdbc.queryForObject("SELECT count(*) FROM report_view WHERE user_id=?", Int::class.java, user)
    private fun detail(id: UUID = report, revision: Int = 1): Map<String, Any?> = mapOf(
        "reportId" to id, "childId" to student, "period" to WEEK, "status" to "COMPLETED", "state" to "NO_RECORD", "revision" to revision,
        "revisions" to listOf(mapOf("revision" to revision, "generatedAt" to "2026-10-26T07:00:00+09:00")),
        "inclusionRule" to "기간 내 제출 기록", "metrics" to emptyList<Any>(), "thinkingTypes" to emptyList<Any>(),
        "changes" to emptyList<Any>(), "reflections" to emptyList<Any>(), "quotes" to emptyList<Any>(),
        "eveningQuestion" to null, "narrative" to null, "verification" to mapOf("numbersMatched" to true, "quotesMatched" to true),
        "versions" to mapOf("prompt" to null, "model" to null), "generatedAt" to "2026-10-26T07:00:00+09:00")
}
