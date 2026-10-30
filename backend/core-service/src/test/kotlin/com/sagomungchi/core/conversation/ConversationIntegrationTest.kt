package com.sagomungchi.core.conversation

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.messaging.OutboxRelay
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.account.service.AccountAccessService
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.report.parent
import com.sagomungchi.core.report.child
import com.sagomungchi.core.learning.LearningHttpStub
import com.sagomungchi.core.conversation.service.*
import com.sagomungchi.core.conversation.repository.ConversationRepository
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.AfterAll
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.test.web.server.LocalServerPort
import org.springframework.data.redis.core.StringRedisTemplate
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.transaction.support.TransactionTemplate
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.*

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = ["spring.rabbitmq.listener.simple.auto-startup=false", "spring.datasource.hikari.maximum-pool-size=5", "spring.datasource.hikari.minimum-idle=0"])
class ConversationIntegrationTest : IntegrationTestSupport() {
    @LocalServerPort var port: Int = 0
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var service: ConversationService
    @Autowired lateinit var usage: AnalysisUsageService
    @Autowired lateinit var repository: ConversationRepository
    @Autowired lateinit var deletion: ConversationDeletionService
    @Autowired lateinit var accounts: AccountAccessService
    @Autowired lateinit var tx: TransactionTemplate
    @Autowired lateinit var redis: StringRedisTemplate
    @MockitoBean lateinit var entitlement: AnalysisEntitlementProvider
    @MockitoBean lateinit var outbox: OutboxRelay
    private lateinit var user: UUID
    private lateinit var student: UUID
    private lateinit var bearer: String
    private val today get() = LocalDate.now(ZoneId.of("Asia/Seoul"))
    private lateinit var answer: UUID
    private lateinit var attempt: UUID

    companion object {
        private val ai = AnalysisHttpStub()
        private val learning = LearningHttpStub()
        @JvmStatic @DynamicPropertySource fun urls(registry: DynamicPropertyRegistry) {
            registry.add("app.services.ai") { ai.url }; registry.add("app.services.learning") { learning.url }
        }
        @JvmStatic @AfterAll fun stop() { ai.close(); learning.close() }
    }
    @BeforeEach fun setup() {
        user = parent(jdbc); student = child(jdbc, user)
        bearer = tokens.access(session(jdbc, user, "PARENT"))
        answer = UUID.randomUUID(); attempt = UUID.randomUUID()
        `when`(entitlement.entitlement(user, student)).thenReturn(AnalysisEntitlement(UUID.randomUUID(), 30, Instant.now().plusSeconds(3600), true))
        ai.requests.clear(); learning.reset()
        ai.respond = { exchange, request ->
            exchange.event("status", """{"state":"RUNNING","message":"합성 조회"}""")
            exchange.event("delta", """{"text":"임시 원문"}""")
            exchange.event("result", result(json.readTree(request.body).path("scope")))
            exchange.event("done", "{}")
        }
        learning.respond = { request ->
            if (request.target.startsWith("/internal/records/evidence")) LearningHttpStub.Reply(body = evidence())
            else LearningHttpStub.Reply(body = """{"studentId":"$student","hasRecords":true}""")
        }
    }
    @AfterEach fun clear() { UserContextHolder.clear() }
    private fun context() = UserContext(user.toString(), "PARENT", setOf(student.toString()), "00-analysis-trace")
    private fun <T> verified(action: () -> T): T {
        UserContextHolder.set(context())
        try { return action() } finally { UserContextHolder.clear() }
    }
    private fun request(path: String, body: Any? = null, method: String = if (body == null) "GET" else "POST", token: String = bearer) =
        HttpRequest.newBuilder(URI("http://127.0.0.1:$port/api/v1$path"))
            .header("Authorization", "Bearer $token").header("Content-Type", "application/json")
            .header("X-User-Id", "forged").header("X-User-Role", "ADMIN").header("X-Student-Scope", UUID.randomUUID().toString())
            .header("traceparent", "00-analysis-trace")
            .method(method, body?.let { HttpRequest.BodyPublishers.ofString(json.writeValueAsString(it)) } ?: HttpRequest.BodyPublishers.noBody()).build()
    private fun call(path: String, body: Any? = null, method: String = if (body == null) "GET" else "POST", token: String = bearer): HttpResponse<String> =
        HttpClient.newHttpClient().use { it.send(request(path, body, method, token), HttpResponse.BodyHandlers.ofString()) }
    private fun create(): UUID {
        val response = call("/conversations", mapOf("childId" to student))
        assertEquals(201, response.statusCode(), response.body())
        return UUID.fromString(json.readTree(response.body()).path("conversationId").asText())
    }
    private fun message(id: UUID, question: String = "합성 질문", scope: Map<String, Any>? = null) =
        call("/conversations/$id/messages", mapOf("question" to question, "scope" to scope))
    private fun events(body: String) = Regex("(?m)^event:(.*)$").findAll(body).map { it.groupValues[1].trim() }.toList()
    private fun result(scope: JsonNode, verification: Boolean = true, source: String = "LLM"): String = json.writeValueAsString(mapOf(
        "messageId" to "forged-ai-id", "answer" to "확정 합성 답변", "scope" to scope,
        "metrics" to emptyList<Any>(), "evidence" to listOf(mapOf("attemptId" to attempt, "answerId" to answer, "answerVersion" to 1, "quote" to "합성 근거", "available" to true)),
        "verification" to mapOf("numbersMatched" to verification, "quotesMatched" to verification, "contentAllowed" to true), "recordCount" to 5,
        "source" to source, "fallback" to if (source == "TEMPLATE") mapOf("reason" to "AI_UNAVAILABLE", "draftVerification" to null) else null))
    private fun evidence(available: Boolean = true) = json.writeValueAsString(mapOf("items" to listOf(mapOf(
        "answerId" to answer, "attemptId" to attempt, "answerVersion" to 1, "quote" to if (available) "합성 근거" else null,
        "missionTitle" to "합성 미션", "submittedAt" to Instant.now().toString(), "available" to available))))
    private fun rows(id: UUID) = repository.messages(id)

    @Test fun `creation default KST period list detail and stream persistence use core IDs and verified headers`() {
        val id = create()
        val created = json.readTree(call("/conversations/$id").body())
        assertEquals(today.minusDays(6).toString(), created.path("period").path("from").asText())
        assertEquals(today.toString(), created.path("period").path("to").asText())
        assertEquals(1, json.readTree(call("/conversations?childId=$student").body()).path("items").size())
        val response = message(id)
        assertEquals(200, response.statusCode()); assertEquals(listOf("status", "status", "delta", "result", "done"), events(response.body()), response.body())
        assertNull(ai.requests.last().header("Upgrade"))
        assertNull(ai.requests.last().header("HTTP2-Settings"))
        val saved = rows(id).single()
        assertEquals("COMPLETED", saved.status); assertEquals("확정 합성 답변", saved.answer)
        assertFalse(saved.answer!!.contains("임시")); assertTrue(response.body().contains(saved.id.toString())); assertFalse(response.body().contains("forged-ai-id"))
        assertEquals(1, repository.evidence(saved.id).size)
        val usageCalls = org.mockito.Mockito.mockingDetails(entitlement).invocations.filter { it.method.name == "recordAttempt" }
        assertEquals(1, usageCalls.size); assertEquals(user, usageCalls.single().arguments[0]); assertEquals(student, usageCalls.single().arguments[1])
        val received = ai.requests.single()
        assertEquals(student.toString(), received.header("X-Student-Scope")); assertEquals(user.toString(), received.header("X-User-Id"))
        assertEquals("PARENT", received.header("X-User-Role")); assertEquals("test-token", received.header("X-Internal-Token"))
        assertEquals("00-analysis-trace", received.header("traceparent")); assertNull(received.header("Authorization"))
        assertEquals(200, call("/conversations/$id/messages/${saved.id}/evidence").statusCode())
        assertEquals(student.toString(), learning.requests.last().header("X-Student-Scope"))
    }
    @Test fun `foreign conversations message IDs child scope and revoked consent cannot be read or streamed`() {
        val id = create(); message(id)
        val otherUser = parent(jdbc); val otherChild = child(jdbc, otherUser)
        val otherToken = tokens.access(session(jdbc, otherUser, "PARENT"))
        val otherConversation = json.readTree(call("/conversations", mapOf("childId" to otherChild), token = otherToken).body())
        // Provider missing for this child must fail closed rather than mint a conversation.
        assertEquals(0, otherConversation.path("conversationId").size())
        assertEquals(404, call("/conversations/$id", token = otherToken).statusCode())
        assertEquals(404, call("/conversations/$id/messages/${rows(id).single().id}/evidence", token = otherToken).statusCode())
        assertEquals(404, call("/conversations/$id/messages/${UUID.randomUUID()}/retry", emptyMap<String, String>()).statusCode())
        assertEquals(400, message(id, scope = mapOf("childId" to otherChild, "from" to today, "to" to today)).statusCode())
        jdbc.update("UPDATE consent SET status='WITHDRAWN',withdrawn_at=now() WHERE subject_user_id=? AND student_id=?", user, student)
        assertEquals(403, call("/conversations/$id").statusCode()); assertEquals(403, message(id).statusCode())
    }
    @Test fun `free and expired plans block and invalid period never invokes AI`() {
        `when`(entitlement.entitlement(user, student)).thenReturn(AnalysisEntitlement(UUID.randomUUID(), 0, null, false))
        assertEquals(429, call("/conversations", mapOf("childId" to student)).statusCode())
        `when`(entitlement.entitlement(user, student)).thenReturn(AnalysisEntitlement(UUID.randomUUID(), 30, Instant.now().minusSeconds(1), true))
        assertEquals(503, call("/conversations", mapOf("childId" to student)).statusCode())
        assertEquals(400, call("/conversations", mapOf("childId" to student, "from" to today)).statusCode())
        assertTrue(ai.requests.isEmpty())
    }
    @Test fun `same scope history excludes failed and changed-period messages`() {
        val id = create(); message(id, "첫 질문"); message(id, "후속 질문")
        assertEquals(2, json.readTree(ai.requests.last().body).path("history").size())
        message(id, "오늘 질문", mapOf("childId" to student, "from" to today, "to" to today))
        assertEquals(0, json.readTree(ai.requests.last().body).path("history").size())
        assertTrue(rows(id).last().scopeChanged)
    }
    @Test fun `clarification is stored without answer and next request must confirm scope`() {
        val id = create()
        ai.respond = { exchange, _ ->
            exchange.event("clarification", """{"question":"기간을 확인해 주세요","options":[{"label":"오늘","scope":{"childId":"$student","from":"$today","to":"$today"}}]}""")
            exchange.event("done", "{}")
        }
        assertEquals(listOf("status", "clarification", "done"), events(message(id).body()))
        assertEquals("COMPLETED", rows(id).single().status); assertNull(rows(id).single().answer); assertNotNull(rows(id).single().clarification)
    }
    @Test fun `unverified result partial stream invalid order and upstream error stay FAILED with no answer`() {
        val id = create()
        val failures = listOf<(com.sun.net.httpserver.HttpExchange, AnalysisHttpStub.Request) -> Unit>(
            { exchange, request -> exchange.event("status", """{"state":"RUNNING","message":"조회"}"""); exchange.event("result", result(json.readTree(request.body).path("scope"), false)); exchange.event("done", "{}") },
            { exchange, _ -> exchange.event("status", """{"state":"RUNNING","message":"조회"}"""); exchange.event("delta", """{"text":"임시"}""") },
            { exchange, _ -> exchange.event("delta", """{"text":"먼저 도착"}"""); exchange.event("done", "{}") },
            { exchange, _ -> exchange.event("error", """{"code":"AI_UNAVAILABLE","status":503}""") }
        )
        failures.forEach { respond ->
            ai.respond = respond
            val response = message(id)
            assertTrue("error" in events(response.body()), response.body()); assertFalse("result" in events(response.body()))
            assertEquals("FAILED", rows(id).last().status); assertNull(rows(id).last().answer)
        }
    }
    @Test fun `retry keeps message ID increments generation and old failure cannot overwrite successful TEMPLATE`() {
        val id = create()
        ai.respond = { exchange, _ -> exchange.event("error", """{"code":"AI_UNAVAILABLE"}""") }
        message(id); val failed = rows(id).single()
        ai.respond = { exchange, request -> exchange.event("status", """{"state":"RUNNING","message":"조회"}"""); exchange.event("result", result(json.readTree(request.body).path("scope"), source = "TEMPLATE")); exchange.event("done", "{}") }
        val retry = call("/conversations/$id/messages/${failed.id}/retry", emptyMap<String, String>())
        assertTrue("result" in events(retry.body()), retry.body())
        val saved = rows(id).single(); assertEquals(failed.id, saved.id); assertEquals(1, saved.retryCount); assertEquals("COMPLETED", saved.status)
        assertFalse(repository.fail(failed.id, 0, "OLD_FAILURE")); assertEquals("COMPLETED", rows(id).single().status)
        assertTrue(call("/conversations/$id").body().contains("AI_UNAVAILABLE"))
        assertEquals(409, call("/conversations/$id/messages/${failed.id}/retry", emptyMap<String, String>()).statusCode())
    }
    @Test fun `deleted evidence is unavailable and forged answer period never completes`() {
        val id = create(); message(id); val msg = rows(id).single()
        learning.respond = { LearningHttpStub.Reply(body = evidence(false)) }
        val proof = call("/conversations/$id/messages/${msg.id}/evidence")
        assertEquals(200, proof.statusCode()); assertFalse(json.readTree(proof.body()).path("items")[0].path("available").asBoolean())
        assertFalse(proof.body().contains("合成")); assertFalse(proof.body().contains("합성 근거"))
        val response = message(id)
        assertTrue(response.body().contains("EVIDENCE_UNAVAILABLE")); assertEquals("FAILED", rows(id).last().status)
    }
    @Test fun `single running message and duplicate retries are serialized without consuming rejected requests`() {
        val id = create()
        val first = verified { service.prepare(id, "진행 질문", null) }
        assertEquals("ANALYSIS_IN_PROGRESS", verified { assertFailsWith<BusinessException> { service.prepare(id, "중복", null) } }.code)
        service.fail(first, "AI_UNAVAILABLE")
        val executor = Executors.newVirtualThreadPerTaskExecutor()
        try {
            val futures = (1..8).map { executor.submit<Boolean> { verified {
                try { service.prepare(id, null, null, first.message.id); true } catch (_: BusinessException) { false }
            } } }
            assertEquals(1, futures.count { it.get(20, TimeUnit.SECONDS) })
        } finally { executor.close() }
        assertEquals(1, rows(id).size); assertEquals(1, rows(id).single().retryCount)
        assertEquals("2", redis.opsForValue().get("analysis:daily:v1:$student:$today"))
    }
    @Test fun `Redis atomically admits only product daily count across concurrent callers and expires on KST boundary`() {
        `when`(entitlement.entitlement(user, student)).thenReturn(AnalysisEntitlement(UUID.randomUUID(), 3, null, true))
        val executor = Executors.newVirtualThreadPerTaskExecutor()
        try {
            val tasks = (1..30).map { executor.submit<Boolean> { try { usage.consume(user, student); true } catch (_: BusinessException) { false } } }
            assertEquals(3, tasks.count { it.get(5, TimeUnit.SECONDS) })
        } finally { executor.close() }
        val key = "analysis:daily:v1:$student:$today"
        assertEquals("3", redis.opsForValue().get(key)); assertTrue(redis.getExpire(key) in 86400..172800)
    }
    @Test fun `delete racing stream cancels and cannot resurrect rows or deliver post-delete raw text`() {
        val id = create(); val entered = CountDownLatch(1); val release = CountDownLatch(1)
        ai.respond = { exchange, _ ->
            exchange.event("status", """{"state":"RUNNING","message":"조회"}"""); entered.countDown()
            release.await(5, TimeUnit.SECONDS)
            exchange.event("delta", """{"text":"삭제 후 원문 금지"}"""); exchange.event("done", "{}")
        }
        val executor = Executors.newVirtualThreadPerTaskExecutor()
        try {
            val pending = executor.submit<HttpResponse<String>> { message(id) }
            assertTrue(entered.await(3, TimeUnit.SECONDS))
            tx.execute { accounts.lockParent(user); repository.lockStudent(student); jdbc.update("UPDATE student SET status='DELETION_REQUESTED' WHERE id=?", student); deletion.deleteStudent(student) }
            release.countDown()
            val response = pending.get(5, TimeUnit.SECONDS)
            assertFalse(response.body().contains("삭제 후 원문 금지")); assertNull(repository.find(id)); assertTrue(rows(id).isEmpty())
        } finally { release.countDown(); executor.close() }
    }
    @Test fun `client socket close cancels AI and keeps retryable FAILED question`() {
        val id = create(); val entered = CountDownLatch(1)
        ai.respond = { exchange, _ ->
            entered.countDown()
            repeat(100) { exchange.event("status", """{"state":"RUNNING","message":"조회"}"""); Thread.sleep(30) }
        }
        HttpClient.newHttpClient().use { client ->
            val response = client.send(request("/conversations/$id/messages", mapOf("question" to "취소 질문")), HttpResponse.BodyHandlers.ofInputStream())
            assertTrue(entered.await(3, TimeUnit.SECONDS)); response.body().readNBytes(10); response.body().close()
        }
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(6)
        while (rows(id).single().status != "FAILED" && System.nanoTime() < deadline) Thread.sleep(20)
        assertEquals("FAILED", rows(id).single().status); assertNull(rows(id).single().answer)
    }
    @Test fun `current AI history text contract and missing answer version resolve against authoritative learning`() {
        val id = create()
        assertEquals(400, message(id, "x".repeat(1001)).statusCode())
        ai.respond = { exchange, request ->
            exchange.event("status", """{"state":"RUNNING","message":"조회"}""")
            val value = json.readTree(result(json.readTree(request.body).path("scope"))) as com.fasterxml.jackson.databind.node.ObjectNode
            (value.path("evidence")[0] as com.fasterxml.jackson.databind.node.ObjectNode).putNull("answerVersion")
            exchange.event("result", value.toString()); exchange.event("done", "{}")
        }
        assertTrue("result" in events(message(id, "첫 질문").body()))
        assertEquals(1, repository.evidence(rows(id).single().id).single().answerVersion)
        assertTrue("result" in events(message(id, "후속 질문").body()))
        val history = json.readTree(ai.requests.last().body).path("history")
        assertEquals(2, history.size()); assertEquals("첫 질문", history[0].path("text").asText()); assertFalse(history[0].has("content"))
    }
    @Test fun `current AI clarification can end at EOF without done and never invents a scope choice`() {
        val id = create()
        ai.respond = { exchange, request ->
            val scope = json.readTree(request.body).path("scope")
            val current = mapOf("childId" to scope.path("studentId").asText(), "from" to scope.path("from").asText(), "to" to scope.path("to").asText())
            exchange.event("status", """{"state":"RUNNING","message":"확인"}""")
            exchange.event("clarification", json.writeValueAsString(mapOf("reason" to "DIFFERENT_PERIOD", "message" to "상단에서 기간을 확인해 주세요", "current" to current)))
        }
        val response = message(id)
        assertEquals(listOf("status", "status", "clarification", "done"), events(response.body()), response.body())
        assertEquals("COMPLETED", rows(id).single().status); assertNull(rows(id).single().answer)
        assertEquals(0, json.readTree(rows(id).single().clarification).path("options").size())
    }
    @Test fun `normalized conversation paths retain authentication role ownership and SSE protections`() {
        val id = create()
        val studentToken = tokens.access(session(jdbc, user, "STUDENT", student))
        val outsider = parent(jdbc); val outsiderChild = child(jdbc, outsider)
        val outsiderToken = tokens.access(session(jdbc, outsider, "PARENT"))
        for (path in listOf("/conversations/$id", "/conversations;matrix=1/$id", "/%63onversations/$id")) {
            assertEquals(200, call(path).statusCode(), path)
            assertEquals(401, call(path, token = "").statusCode(), path)
            assertEquals(403, call(path, token = studentToken).statusCode(), path)
            assertEquals(404, call(path, token = outsiderToken).statusCode(), path)
            assertEquals(403, call("$path/messages", mapOf("question" to "접근 금지"), token = studentToken).statusCode(), path)
            assertEquals(404, call("$path/messages", mapOf("question" to "접근 금지"), token = outsiderToken).statusCode(), path)
            assertEquals(403, call(path.substringBefore("/$id"), mapOf("childId" to outsiderChild)).statusCode(), path)
        }
        assertTrue(ai.requests.isEmpty())
    }
    @Test fun `AI contentAllowed false is never confirmed and a true retry preserves the attestation`() {
        val id = create(); val allowed = java.util.concurrent.atomic.AtomicBoolean(false)
        ai.respond = { exchange, request ->
            exchange.event("status", """{"state":"RUNNING","message":"조회"}""")
            val data = json.readTree(result(json.readTree(request.body).path("scope"))) as com.fasterxml.jackson.databind.node.ObjectNode
            (data.path("verification") as com.fasterxml.jackson.databind.node.ObjectNode).put("contentAllowed", allowed.get())
            exchange.event("result", data.toString()); exchange.event("done", "{}")
        }
        val failure = message(id)
        assertTrue(failure.body().contains("AI_INVALID_RESPONSE")); assertFalse("result" in events(failure.body()))
        val failed = rows(id).single(); assertEquals("FAILED", failed.status); assertNull(failed.answer)
        allowed.set(true)
        val success = call("/conversations/$id/messages/${failed.id}/retry", emptyMap<String, String>())
        assertTrue("result" in events(success.body()), success.body())
        assertTrue(json.readTree(rows(id).single().verification).path("contentAllowed").booleanValue())
    }
    @Test fun `earlier baseline answer requires membership in selected period including later list pages`() {
        val id = create(); val included = java.util.concurrent.atomic.AtomicBoolean(true)
        val oldAt = today.minusDays(8).atStartOfDay(ZoneId.of("Asia/Seoul")).plusHours(12).toInstant().toString()
        val laterAnswer = UUID.randomUUID()
        fun record(target: UUID): Map<String, Any?> = mapOf("attemptId" to target, "studentId" to student,
            "mission" to mapOf("title" to "합성 미션"), "status" to "IN_PROGRESS", "finishedAt" to null,
            "answers" to if (target == attempt) listOf(
                mapOf("answerId" to answer, "version" to 1, "submittedAt" to oldAt, "text" to "합성 근거", "feedback" to mapOf("status" to "DONE")),
                mapOf("answerId" to laterAnswer, "version" to 2, "submittedAt" to Instant.now().toString(), "text" to "보완 답변", "feedback" to mapOf("status" to "DONE")))
            else listOf(mapOf("answerId" to UUID.randomUUID(), "version" to 1, "submittedAt" to Instant.now().toString(), "text" to "합성 답변", "feedback" to mapOf("status" to "DONE"))))
        learning.respond = { request ->
            when {
                request.target.startsWith("/internal/records/evidence") -> {
                    val data = json.readTree(evidence())
                    (data.path("items")[0] as com.fasterxml.jackson.databind.node.ObjectNode).put("submittedAt", oldAt)
                    LearningHttpStub.Reply(body = data.toString())
                }
                request.target.startsWith("/internal/records/students/$student/attempts?") -> {
                    val page = if (request.target.contains("page=1")) 1 else 0
                    val items = if (!included.get()) emptyList() else if (page == 0) (1..100).map { record(UUID.randomUUID()) } else listOf(record(attempt))
                    val payload = mapOf("studentId" to student, "period" to mapOf("from" to today.minusDays(6), "to" to today),
                        "state" to if (included.get()) "OK" else "NO_RECORD", "inclusionRule" to "기간 내 제출 시도", "page" to page, "size" to 100,
                        "totalElements" to if (included.get()) 101 else 0, "items" to items)
                    LearningHttpStub.Reply(body = json.writeValueAsString(payload))
                }
                else -> LearningHttpStub.Reply(status = 500, body = "{}")
            }
        }
        val success = message(id)
        assertTrue("result" in events(success.body()), success.body()); assertEquals("COMPLETED", rows(id).single().status)
        assertTrue(learning.requests.any { it.target.contains("page=1&size=100") })
        learning.requests.forEach { assertEquals(student.toString(), it.header("X-Student-Scope")) }
        included.set(false)
        val failure = message(id)
        assertTrue(failure.body().contains("AI_INVALID_RESPONSE")); assertFalse("result" in events(failure.body()))
        assertEquals("FAILED", rows(id).last().status); assertNull(rows(id).last().answer)
    }
    @Test fun `example question API checks current child and learning state`() {
        val response = call("/agent/example-questions?childId=$student")
        assertEquals(200, response.statusCode()); assertEquals(5, json.readTree(response.body()).path("items").size())
        assertEquals(403, call("/agent/example-questions?childId=${UUID.randomUUID()}").statusCode())
    }
    @Test fun `five final response categories preserve verification draft failure and notice on reload`() {
        val modes = listOf("LLM","VERIFICATION_FAILED","AI_UNAVAILABLE","NO_RECORD","UNSUPPORTED")
        for(mode in modes) {
            val id=create()
            ai.respond = { exchange, request ->
                exchange.event("status", """{"state":"RUNNING","message":"조회"}""")
                val value=json.readTree(result(json.readTree(request.body).path("scope"))) as com.fasterxml.jackson.databind.node.ObjectNode
                if(mode!="LLM") value.put("source","TEMPLATE")
                if(mode in setOf("VERIFICATION_FAILED","AI_UNAVAILABLE")) {
                    value.set<JsonNode>("fallback",json.valueToTree(mapOf("reason" to mode,"draftVerification" to
                        if(mode=="VERIFICATION_FAILED") mapOf("numbersMatched" to false,"quotesMatched" to true,"contentAllowed" to true) else null)))
                } else if(mode!="LLM") {
                    value.set<JsonNode>("notice",json.valueToTree(mapOf("reason" to mode)))
                    value.set<JsonNode>("evidence",json.createArrayNode())
                    if(mode=="NO_RECORD") value.put("recordCount",0)
                }
                exchange.event("delta","""{"text":"최종 답변이 아닌 초안"}""")
                exchange.event("result",value.toString());exchange.event("done","{}")
            }
            val response=message(id)
            assertTrue("result" in events(response.body()),response.body())
            val saved=rows(id).single();assertEquals("COMPLETED",saved.status)
            val detail=json.readTree(call("/conversations/$id").body()).path("messages")[0]
            assertTrue(detail.path("verification").path("contentAllowed").asBoolean())
            when(mode) {
                "VERIFICATION_FAILED" -> assertFalse(detail.path("fallback").path("draftVerification").path("numbersMatched").asBoolean())
                "AI_UNAVAILABLE" -> assertEquals(mode,detail.path("fallback").path("reason").asText())
                "NO_RECORD","UNSUPPORTED" -> { assertEquals(mode,detail.path("notice").path("reason").asText());assertTrue(detail.path("fallback").isNull) }
            }
        }
    }
    @Test fun `contradictory source metadata and forged quotes are rejected before persistence`() {
        for(mode in listOf("BOTH","DRAFT_PASSED","LLM_NOTICE","UNKNOWN_NOTICE","FORGED_QUOTE")) {
            val id=create()
            ai.respond = { exchange, request ->
                exchange.event("status","""{"state":"RUNNING","message":"조회"}""")
                val value=json.readTree(result(json.readTree(request.body).path("scope"),source="TEMPLATE")) as com.fasterxml.jackson.databind.node.ObjectNode
                when(mode) {
                    "BOTH" -> value.set<JsonNode>("notice",json.valueToTree(mapOf("reason" to "UNSUPPORTED")))
                    "DRAFT_PASSED" -> value.set<JsonNode>("fallback",json.valueToTree(mapOf("reason" to "VERIFICATION_FAILED","draftVerification" to mapOf("numbersMatched" to true,"quotesMatched" to true,"contentAllowed" to true))))
                    "LLM_NOTICE" -> { value.put("source","LLM");value.putNull("fallback");value.set<JsonNode>("notice",json.valueToTree(mapOf("reason" to "UNSUPPORTED"))) }
                    "UNKNOWN_NOTICE" -> { value.putNull("fallback");value.set<JsonNode>("notice",json.valueToTree(mapOf("reason" to "UNKNOWN"))) }
                    "FORGED_QUOTE" -> (value.path("evidence")[0] as com.fasterxml.jackson.databind.node.ObjectNode).put("quote","기록에 없는 인용")
                }
                exchange.event("result",value.toString());exchange.event("done","{}")
            }
            val response=message(id);assertTrue("error" in events(response.body()),mode);assertFalse("result" in events(response.body()))
            assertEquals("FAILED",rows(id).single().status);assertNull(rows(id).single().answer)
        }
    }
    @Test fun `reflection references are checked against learning and remain typed after reload and deletion`() {
        val id=create();val at=Instant.now();val available=java.util.concurrent.atomic.AtomicBoolean(true)
        val suppliedAt=java.util.concurrent.atomic.AtomicReference(at)
        val period=mapOf("from" to today.minusDays(6).toString(),"to" to today.toString())
        val record=mapOf("attemptId" to attempt,"studentId" to student,"mission" to mapOf("title" to "합성 미션"),
            "status" to "COMPLETED","answers" to emptyList<Any>(),
            "reflection" to mapOf("difficulty" to "NORMAL","text" to "돌아보기 합성 원문","createdAt" to at.toString()))
        learning.respond = { request ->
            if(request.target.contains("/attempts/$attempt")) {
                if(available.get()) LearningHttpStub.Reply(body=json.writeValueAsString(record+mapOf("state" to "OK","period" to period)))
                else LearningHttpStub.Reply(404,"""{"code":"NOT_FOUND"}""")
            } else LearningHttpStub.Reply(body=json.writeValueAsString(mapOf("studentId" to student,"state" to "INSUFFICIENT_SAMPLE","period" to period,
                "items" to listOf(record),"inclusionRule" to "P08","page" to 0,"size" to 100,"totalElements" to 1)))
        }
        ai.respond = { exchange, request ->
            exchange.event("status","""{"state":"RUNNING","message":"조회"}""")
            val value=json.readTree(result(json.readTree(request.body).path("scope"))) as com.fasterxml.jackson.databind.node.ObjectNode
            value.put("answer","“돌아보기 합성”이라고 썼어요.")
            value.set<JsonNode>("evidence",json.valueToTree(listOf(mapOf("kind" to "REFLECTION","attemptId" to attempt,"answerId" to null,
                "answerVersion" to null,"quote" to "돌아보기 합성","submittedAt" to suppliedAt.get().toString(),"available" to true))))
            exchange.event("result",value.toString());exchange.event("done","{}")
        }
        val response=message(id);assertTrue("result" in events(response.body()),response.body())
        val savedMessage=rows(id).single();val ref=repository.evidence(savedMessage.id).single()
        assertEquals("REFLECTION",ref.kind);assertNull(ref.answerId);assertNull(ref.answerVersion)
        val proof=json.readTree(call("/conversations/$id/messages/${savedMessage.id}/evidence").body()).path("items")[0]
        assertEquals("REFLECTION",proof.path("kind").asText());assertEquals("돌아보기 합성 원문",proof.path("quote").asText())
        suppliedAt.set(at.plusSeconds(1))
        assertTrue("error" in events(message(id,"시각이 다른 근거").body()))
        assertEquals("FAILED",rows(id).last().status)
        available.set(false)
        val removed=json.readTree(call("/conversations/$id/messages/${savedMessage.id}/evidence").body()).path("items")[0]
        assertFalse(removed.path("available").asBoolean());assertTrue(removed.path("quote").isNull)
    }

    @Test fun `evidence kind constraints retain legacy answers and reject inconsistent reflection references`() {
        val id=create();assertTrue("result" in events(message(id).body()))
        val saved=rows(id).single()
        assertEquals("ANSWER",repository.evidence(saved.id).single().kind)
        for(kind in listOf("REFLECTION","ANSWER","INVALID")) {
            assertFailsWith<org.springframework.dao.DataIntegrityViolationException> {
                tx.executeWithoutResult {
                    jdbc.update("INSERT INTO message_evidence(id,message_id,attempt_id,answer_id,answer_version,kind) VALUES(?,?,?,?,?,?)",
                        UUID.randomUUID(),saved.id,attempt,if(kind=="ANSWER") null else answer,if(kind=="ANSWER") null else 1,kind)
                }
            }
        }
    }

}
