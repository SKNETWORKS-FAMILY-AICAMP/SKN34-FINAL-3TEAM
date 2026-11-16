package com.sagomungchi.core.conversation

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.messaging.OutboxRelay
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.conversation.repository.ConversationRepository
import com.sagomungchi.core.conversation.service.AnalysisEntitlement
import com.sagomungchi.core.conversation.service.AnalysisEntitlementProvider
import com.sagomungchi.core.learning.LearningHttpStub
import com.sagomungchi.core.report.WEEK
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.completedJob
import com.sagomungchi.core.report.domain.ReportPeriod
import com.sagomungchi.core.report.domain.ReportPeriodType
import com.sagomungchi.core.report.parent
import com.sun.net.httpserver.HttpServer
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.test.web.server.LocalServerPort
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import java.net.InetSocketAddress
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Instant
import java.time.LocalDate
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.test.*

/** P25 daily report pinned conversation (#392): creation checks, per-message pinned revision and the shared daily quota. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = ["spring.rabbitmq.listener.simple.auto-startup=false", "spring.datasource.hikari.maximum-pool-size=5", "spring.datasource.hikari.minimum-idle=0"])
class ReportConversationIntegrationTest : IntegrationTestSupport() {
    @LocalServerPort var port: Int = 0
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var repository: ConversationRepository
    @MockitoBean lateinit var entitlement: AnalysisEntitlementProvider
    @MockitoBean lateinit var outbox: OutboxRelay
    private lateinit var user: UUID
    private lateinit var student: UUID
    private lateinit var bearer: String
    private lateinit var daily: UUID
    private val day = LocalDate.parse("2026-11-08")

    companion object {
        private data class ReportRequest(val path: String, val query: String?, val scope: String?)
        private val ai = AnalysisHttpStub()
        private val learning = LearningHttpStub()
        private val reportRequests = CopyOnWriteArrayList<ReportRequest>()
        @Volatile private var reportBody: (ReportRequest) -> String = { "{}" }
        @Volatile private var reportCode = 200
        private val report = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
            createContext("/internal/reports") { exchange ->
                val request = ReportRequest(exchange.requestURI.path, exchange.requestURI.rawQuery, exchange.requestHeaders.getFirst("X-Student-Scope"))
                reportRequests.add(request)
                val bytes = reportBody(request).toByteArray(Charsets.UTF_8)
                exchange.responseHeaders.set("Content-Type", "application/json")
                exchange.sendResponseHeaders(reportCode, bytes.size.toLong())
                exchange.responseBody.use { it.write(bytes) }
            }
            start()
        }
        @JvmStatic @DynamicPropertySource fun urls(registry: DynamicPropertyRegistry) {
            registry.add("app.services.ai") { ai.url }; registry.add("app.services.learning") { learning.url }
            registry.add("app.services.report") { "http://127.0.0.1:${report.address.port}" }
        }
        @JvmStatic @AfterAll fun stop() { ai.close(); learning.close(); report.stop(0) }
    }

    @BeforeEach fun setup() {
        user = parent(jdbc); student = child(jdbc, user)
        bearer = tokens.access(session(jdbc, user, "PARENT"))
        daily = completedJob(jdbc, student, ReportPeriod(day, day, ReportPeriodType.DAILY)).second
        `when`(entitlement.entitlement(user, student)).thenReturn(AnalysisEntitlement(UUID.randomUUID(), 30, Instant.now().plusSeconds(3600), true))
        ai.requests.clear(); learning.reset(); reportRequests.clear(); reportCode = 200
        reportBody = { request -> detail(UUID.fromString(request.path.substringAfterLast('/')), request.query?.substringAfter("revision=")?.toInt() ?: 2) }
        ai.respond = { exchange, request ->
            exchange.event("status", """{"state":"RUNNING","message":"합성 조회"}""")
            exchange.event("result", result(json.readTree(request.body).path("scope")))
            exchange.event("done", "{}")
        }
        learning.respond = { LearningHttpStub.Reply(body = """{"studentId":"$student","hasRecords":true}""") }
    }

    private fun detail(reportId: UUID, revision: Int, child: UUID = student) = json.writeValueAsString(mapOf(
        "reportId" to reportId, "childId" to child, "periodType" to "DAILY", "period" to mapOf("from" to day, "to" to day),
        "revision" to revision, "status" to "COMPLETED", "state" to "OK", "revisions" to (1..revision).map { mapOf("revision" to it) },
        "inclusionRule" to "합성", "metrics" to listOf(mapOf("label" to "푼 문제", "value" to null, "count" to 3, "numerator" to 3, "denominator" to 3)),
        "thinkingTypes" to emptyList<Any>(), "changes" to emptyList<Any>(), "reflections" to emptyList<Any>(), "quotes" to emptyList<Any>(),
        "eveningQuestion" to null, "narrative" to null,
        "problems" to listOf(mapOf("missionId" to UUID.randomUUID(), "title" to "합성 미션", "context" to "THEME_DAY", "judgment" to "PARTIAL",
            "followups" to listOf(mapOf("question" to "왜?", "answer" to "아이 원문")), "finalAnswer" to "아이 최종 원문",
            "elements" to listOf(mapOf("label" to "근거", "satisfied" to true)), "reflection" to null,
            "quotes" to listOf(mapOf("answerId" to UUID.randomUUID(), "text" to "아이 인용", "verified" to true))))))
    private fun result(scope: JsonNode): String = json.writeValueAsString(mapOf(
        "messageId" to "ai-id", "answer" to "확정 합성 답변", "scope" to scope, "metrics" to emptyList<Any>(), "evidence" to emptyList<Any>(),
        "verification" to mapOf("numbersMatched" to true, "quotesMatched" to true, "contentAllowed" to true), "recordCount" to 3,
        "source" to "LLM", "fallback" to null))
    private fun call(path: String, body: Any): HttpResponse<String> = HttpClient.newHttpClient().use {
        it.send(HttpRequest.newBuilder(URI("http://127.0.0.1:$port/api/v1$path")).header("Authorization", "Bearer $bearer")
            .header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body))).build(),
            HttpResponse.BodyHandlers.ofString())
    }
    private fun create(reportId: UUID = daily) = call("/conversations", mapOf("childId" to student, "reportId" to reportId))
    private fun code(response: HttpResponse<String>) = json.readTree(response.body()).path("code").asText()
    private fun attempts() = org.mockito.Mockito.mockingDetails(entitlement).invocations.count { it.method.name == "recordAttempt" }

    @Test fun `daily report pins child day and latest revision and every message reads that revision`() {
        val created = create()
        assertEquals(201, created.statusCode(), created.body())
        val body = json.readTree(created.body())
        assertEquals(daily.toString(), body.path("reportId").asText()); assertEquals(2, body.path("reportRevision").asInt())
        assertEquals(day.toString(), body.path("period").path("from").asText()); assertEquals(day.toString(), body.path("period").path("to").asText())
        assertEquals(listOf("/internal/reports/$daily"), reportRequests.map { it.path }); assertNull(reportRequests.single().query)
        assertEquals(student.toString(), reportRequests.single().scope)
        // A later regeneration must not move the pinned revision.
        reportRequests.clear()
        reportBody = { request -> detail(daily, request.query?.substringAfter("revision=")?.toInt() ?: 3) }

        val id = UUID.fromString(body.path("conversationId").asText())
        val response = call("/conversations/$id/messages", mapOf("question" to "그날 어땠어?", "scope" to mapOf("childId" to student, "from" to day, "to" to day)))
        assertEquals(200, response.statusCode()); assertTrue(response.body().contains("event:result"), response.body())
        assertEquals("revision=2", reportRequests.single().query)
        val sent = json.readTree(ai.requests.single().body)
        val report = sent.path("report")
        assertEquals(daily.toString(), report.path("reportId").asText()); assertEquals(2, report.path("revision").asInt())
        assertEquals(day.toString(), report.path("date").asText())
        assertEquals("""[{"label":"푼 문제","count":3}]""", report.path("metrics").toString())
        assertEquals("""[{"title":"합성 미션","context":"THEME_DAY","judgment":"PARTIAL","elements":[{"label":"근거","satisfied":true}]}]""",
            report.path("problems").toString())
        assertFalse(sent.toString().contains("아이 원문") || sent.toString().contains("아이 인용") || sent.toString().contains("아이 최종 원문"))
        assertEquals(day.toString(), sent.path("scope").path("from").asText()); assertEquals(day.toString(), sent.path("scope").path("to").asText())
        assertEquals(1, attempts(), "a pinned question shares the daily analysis quota")
        assertFalse(repository.messages(id).single().scopeChanged)
    }

    @Test fun `weekly other child unknown reports are rejected and free plan is limited before report`() {
        val weekly = completedJob(jdbc, student, WEEK).second
        val sibling = child(jdbc, user)
        val siblingDaily = completedJob(jdbc, sibling, ReportPeriod(day, day, ReportPeriodType.DAILY)).second
        for (reportId in listOf(weekly, siblingDaily, UUID.randomUUID())) {
            val response = create(reportId)
            assertEquals(422, response.statusCode(), response.body()); assertEquals("CONVERSATION_REPORT_INVALID", code(response))
        }
        assertTrue(reportRequests.isEmpty())

        reportBody = { detail(daily, 1).replace("\"COMPLETED\"", "\"FAILED\"") }
        assertEquals("CONVERSATION_REPORT_INVALID", code(create()))

        `when`(entitlement.entitlement(user, student)).thenReturn(AnalysisEntitlement(UUID.randomUUID(), 0, null, false))
        reportRequests.clear()
        val free = create()
        assertEquals(429, free.statusCode()); assertEquals("USAGE_LIMIT_REACHED", code(free)); assertTrue(reportRequests.isEmpty())
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM conversation WHERE student_id=?", Int::class.java, student))
    }

    @Test fun `pinned conversation keeps its day and report failures fail the message`() {
        val mixed = call("/conversations", mapOf("childId" to student, "reportId" to daily, "from" to day, "to" to day))
        assertEquals(400, mixed.statusCode(), mixed.body())
        val id = UUID.fromString(json.readTree(create().body()).path("conversationId").asText())

        val moved = call("/conversations/$id/messages", mapOf("question" to "전날은?", "scope" to mapOf("childId" to student, "from" to day.minusDays(1), "to" to day)))
        assertEquals(400, moved.statusCode(), moved.body()); assertEquals(0, attempts())
        assertTrue(ai.requests.isEmpty())

        reportCode = 503
        val failed = call("/conversations/$id/messages", mapOf("question" to "그날은?"))
        assertTrue(failed.body().contains("REPORT_UNAVAILABLE"), failed.body())
        assertEquals("FAILED", repository.messages(id).single().status)
        assertTrue(ai.requests.isEmpty())
    }
}
