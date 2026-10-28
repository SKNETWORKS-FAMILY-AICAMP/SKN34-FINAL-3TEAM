package com.sagomungchi.core.learning

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.SseEmitters
import com.sagomungchi.core.account.domain.GoogleProfile
import com.sagomungchi.core.account.service.AuthService
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.test.web.server.LocalServerPort
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Real embedded Tomcat, PublicAuthFilter, JWT/session/consent DB and internal HTTP.
 * #38's test-only HTTP server supplies the unimplemented #25 contract, never production results. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = [
    "app.internal.token=repository-test-token", "app.auth.jwt-secret=dGVzdC1hdXRoLXNlY3JldC0zMi1ieXRlcy1sb25nLWtleSE=",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test", "spring.rabbitmq.listener.simple.auto-startup=false",
])
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class FeedbackIntegrationTest : PostgresRepositoryTest() {
    @LocalServerPort var port: Int = 0
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var streams: SseEmitters
    private lateinit var user: UUID
    private lateinit var child: UUID
    private lateinit var access: String
    private lateinit var subject: String
    private val documents = mutableListOf<UUID>()
    private val answer = UUID.randomUUID()
    private val trace = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"

    companion object {
        private val learning = LearningHttpStub()
        @JvmStatic @DynamicPropertySource fun learningUrl(registry: DynamicPropertyRegistry) {
            registry.add("app.services.learning") { learning.url }
        }
        @JvmStatic @AfterAll fun stopLearning() { learning.close() }
    }

    @BeforeEach fun prepare() {
        learning.reset()
        subject = UUID.randomUUID().toString()
        val parent = auth.login(GoogleProfile(subject, "$subject@example.test", "합성 보호자"), null)
        user = parent.identity.account.id
        child = UUID.randomUUID()
        jdbc.update("INSERT INTO student(id,nickname,grade,birth_year,is_demo,status,created_at,updated_at) VALUES(?,'합성 학생',3,2017,false,'ACTIVE',now(),now())", child)
        jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',now())", UUID.randomUUID(), user, child)
        listOf("TERMS", "PRIVACY", "GUARDIAN").forEach { kind ->
            val document = UUID.randomUUID(); documents.add(document)
            jdbc.update("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(?,?,?,'합성 동의','본문',true,CURRENT_DATE,now())", document, kind, subject)
        }
        jdbc.queryForList("SELECT id,kind FROM consent_document WHERE required=true").forEach { doc ->
            jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(?,?,?,?,true,'AGREED',now())",
                UUID.randomUUID(), doc["id"], user, if (doc["kind"] == "GUARDIAN") child else null)
        }
        access = auth.enterStudent(parent.refreshToken, child, auth.authenticate(parent.accessToken)).accessToken
    }

    @AfterEach fun cleanup() {
        assertNull(UserContextHolder.currentOrNull())
        awaitEmptyConnections()
        jdbc.update("DELETE FROM consent WHERE subject_user_id=?", user)
        jdbc.update("DELETE FROM refresh_token WHERE user_id=?", user)
        jdbc.update("DELETE FROM auth_session WHERE user_id=?", user)
        jdbc.update("DELETE FROM guardianship WHERE parent_user_id=?", user)
        jdbc.update("DELETE FROM user_account WHERE id=?", user)
        jdbc.update("DELETE FROM student WHERE id=?", child)
        documents.forEach { jdbc.update("DELETE FROM consent_document WHERE id=?", it) }; documents.clear()
    }

    private fun request(bearer: String = access, id: String = answer.toString()) = HttpRequest.newBuilder()
        .uri(URI("http://127.0.0.1:$port/api/v1/answers/$id/feedback"))
        .header("Authorization", "Bearer $bearer").header("Accept", "text/event-stream")
        .header("X-User-Id", "forged").header("X-User-Role", "ADMIN").header("X-Student-Scope", UUID.randomUUID().toString())
        .header("X-Internal-Token", "forged").header("traceparent", trace).POST(HttpRequest.BodyPublishers.noBody()).build()

    private fun call(bearer: String = access, id: String = answer.toString()): HttpResponse<String> =
        HttpClient.newHttpClient().use { it.send(request(bearer, id), HttpResponse.BodyHandlers.ofString()) }

    private fun events(body: String) = Regex("(?m)^event:(.*)$").findAll(body).map { it.groupValues[1].trim() }.toList()
    private fun done(result: String = "PARTIAL") = """{"status":"DONE","judgment":{"result":"$result","heldReason":${if (result == "HELD") "\"TOO_SHORT\"" else "null"}},"followup":null,"nextActions":["FINISH"],"versions":{"mission":"m@1","rubric":"r@1","model":null,"prompt":null},"extra":"보존"}"""

    @Test fun `DONE and HELD preserve result and verified internal headers`() {
        listOf("PARTIAL", "HELD").forEach { result ->
            learning.respond = { LearningHttpStub.Reply(200, done(result)) }
            val response = call()
            assertEquals(200, response.statusCode())
            assertTrue(response.headers().firstValue("Content-Type").orElse("").startsWith("text/event-stream"))
            assertEquals("no-store", response.headers().firstValue("Cache-Control").orElse(""))
            assertEquals("no", response.headers().firstValue("X-Accel-Buffering").orElse(""))
            assertEquals(listOf("status", "result", "done"), events(response.body()))
            assertTrue(response.body().contains("\"result\":\"$result\""))
            assertTrue(response.body().contains("\"extra\":\"보존\""))
            val received = learning.requests.last()
            assertEquals("POST", received.method); assertEquals("/internal/answers/$answer/feedback", received.target)
            assertEquals(user.toString(), received.header("X-User-Id")); assertEquals("STUDENT", received.header("X-User-Role"))
            assertEquals(child.toString(), received.header("X-Student-Scope")); assertEquals(trace, received.header("traceparent"))
            assertEquals("repository-test-token", received.header("X-Internal-Token"))
            assertNull(received.header("Authorization")); assertNull(received.header("Idempotency-Key"))
        }
    }

    @Test fun `same answer retries after failure and forwards RUNNING then DONE without core cache`() {
        val calls = AtomicInteger()
        learning.respond = {
            when (calls.incrementAndGet()) {
                1 -> LearningHttpStub.Reply(503, """{"type":"about:blank","title":"처리 실패","status":503,"code":"AI_UNAVAILABLE","retryable":true,"extra":[1]}""")
                2 -> LearningHttpStub.Reply(200, """{"status":"RUNNING","message":"이미 처리 중"}""")
                else -> LearningHttpStub.Reply(200, done())
            }
        }
        val failed = call().body()
        assertEquals(listOf("status", "error", "done"), events(failed))
        assertTrue(failed.contains("AI_UNAVAILABLE")); assertTrue(failed.contains("\"extra\":[1]"))
        val running = call().body()
        assertEquals(listOf("status", "status", "done"), events(running)); assertTrue(running.contains("이미 처리 중"))
        repeat(2) { assertEquals(listOf("status", "result", "done"), events(call().body())) }
        assertEquals(4, calls.get())
    }

    @Test fun `invalid successful payload is explicit failure and scope errors preserve extensions`() {
        listOf("null", "{", "{}", "[]", "{\"status\":\"FAILED\"}").forEach { payload ->
            learning.respond = { LearningHttpStub.Reply(200, payload) }
            val body = call().body()
            assertEquals(listOf("status", "error", "done"), events(body)); assertTrue(body.contains("LEARNING_INVALID_RESPONSE"))
        }
        learning.respond = { LearningHttpStub.Reply(403, """{"status":403,"code":"FORBIDDEN","detail":"학생 범위 밖","extra":"scope"}""") }
        val body = call().body()
        assertEquals(listOf("status", "error", "done"), events(body))
        assertTrue(body.contains("\"retryable\":false")); assertTrue(body.contains("\"extra\":\"scope\""))
    }

    @Test fun `actual auth rejects invalid token parent admin invalid id and revoked student before HTTP`() {
        assertEquals(401, call("invalid").statusCode())
        assertEquals(400, call(id = "not-a-uuid").statusCode())
        val parent = auth.login(GoogleProfile(subject, "$subject@example.test", null), null)
        assertEquals(403, call(parent.accessToken).statusCode())
        jdbc.update("UPDATE user_account SET role='ADMIN' WHERE id=?", user)
        val admin = auth.login(GoogleProfile(subject, "$subject@example.test", null), null)
        assertEquals(403, call(admin.accessToken).statusCode())
        jdbc.update("UPDATE user_account SET role='PARENT' WHERE id=?", user)
        jdbc.update("UPDATE guardianship SET status='UNLINKED',unlinked_at=now() WHERE student_id=?", child)
        assertEquals(403, call().statusCode())
        assertTrue(learning.requests.isEmpty())
    }

    @Test fun `heartbeat is sent after 15 seconds and disconnected request still completes learning`() {
        val entered = CountDownLatch(1); val release = CountDownLatch(1); val completed = CountDownLatch(1)
        learning.respond = {
            entered.countDown()
            check(release.await(50, TimeUnit.SECONDS))
            completed.countDown()
            LearningHttpStub.Reply(200, done())
        }
        try {
            HttpClient.newHttpClient().use { http ->
                val start = System.nanoTime()
                val response = http.send(request(), HttpResponse.BodyHandlers.ofInputStream())
                assertTrue(entered.await(5, TimeUnit.SECONDS))
                val reader = response.body().bufferedReader()
                var line: String?
                do { line = reader.readLine() } while (line != null && line != ": ping")
                assertEquals(": ping", line)
                assertTrue(Duration.ofNanos(System.nanoTime() - start).toMillis() >= 14_000)
                reader.close() // Real client socket/body termination while the downstream operation is blocked.
            }
            assertFalse(completed.await(200, TimeUnit.MILLISECONDS))
            release.countDown()
            assertTrue(completed.await(5, TimeUnit.SECONDS))
        } finally { release.countDown() }
        awaitEmptyConnections()
        assertEquals(1, learning.requests.size)
        learning.respond = { LearningHttpStub.Reply(200, done()) }
        assertEquals(listOf("status", "result", "done"), events(call().body()))
    }

    @Test fun `80 second downstream timeout emits retryable error and closes stream`() {
        val release = CountDownLatch(1)
        learning.respond = { check(release.await(100, TimeUnit.SECONDS)); LearningHttpStub.Reply(200, done()) }
        try {
            val start = System.nanoTime()
            val response = call()
            val seconds = Duration.ofNanos(System.nanoTime() - start).seconds
            assertTrue(seconds in 78..89, "actual seconds: $seconds")
            assertEquals(listOf("status", "error", "done"), events(response.body()))
            assertTrue(response.body().contains("LEARNING_TIMEOUT")); assertTrue(response.body().contains("\"status\":504"))
            assertTrue(response.body().contains("\"retryable\":true"))
            assertEquals(1, learning.requests.size)
        } finally { release.countDown() }
    }

    private fun awaitEmptyConnections() {
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5)
        while (streams.activeConnections != 0 && System.nanoTime() < deadline) Thread.sleep(10)
        assertEquals(0, streams.activeConnections); assertEquals(0, streams.pendingHeartbeats)
    }
}
