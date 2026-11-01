package com.sagomungchi.core.learning

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.IdempotencyService
import com.sagomungchi.core.account.domain.GoogleProfile
import com.sagomungchi.core.account.service.AuthService
import com.sagomungchi.core.learning.client.LearningClient
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.*
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.*

/** Real auth/filter/JWT, HTTP client and PostgreSQL. Only learning is a contract double.
 * Committed data is necessary to test separate connections; unique fixtures are explicitly removed.
 * The database is the disposable PostgresRepositoryTest DB, never the running compose DB.
 */
@AutoConfigureMockMvc
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class LearningProxyIntegrationTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var client: LearningClient
    @Autowired lateinit var idempotency: IdempotencyService
    private lateinit var user: UUID
    private lateinit var child: UUID
    private lateinit var access: String
    private lateinit var subject: String
    private val documents = mutableListOf<UUID>()
    private val attempt = UUID.randomUUID()
    private val answerPath get() = "/api/v1/attempts/$attempt/answers"
    private val body = "{ \"inputType\":\"NARRATIVE\", \"text\":\"내 생각\" }"

    companion object {
        private val stub = LearningHttpStub()
        @JvmStatic @DynamicPropertySource fun learning(registry: DynamicPropertyRegistry) {
            registry.add("app.services.learning") { stub.url }
        }
        @JvmStatic @AfterAll fun stopLearning() { stub.close() }
    }

    @BeforeEach fun prepare() {
        stub.reset(); client.circuit.reset()
        subject = UUID.randomUUID().toString()
        val parent = auth.login(GoogleProfile(subject, "$subject@example.test", "테스트 보호자"), null)
        user = parent.identity.account.id
        child = UUID.randomUUID()
        jdbc.update("INSERT INTO student(pin_failed_count,id,nickname,grade,birth_year,is_demo,status,created_at,updated_at) VALUES(0,?,'테스트 학생',3,2017,false,'ACTIVE',now(),now())", child)
        jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',now())", UUID.randomUUID(), user, child)
        listOf("TERMS", "PRIVACY", "GUARDIAN").forEach { kind ->
            val document = UUID.randomUUID(); documents.add(document)
            // Latest required policy, plus existing policies, are all granted to this unique fixture.
            jdbc.update("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(?,?,?,'합성 동의','본문',true,CURRENT_DATE,now())", document, kind, subject)
        }
        jdbc.queryForList("SELECT id,kind FROM consent_document WHERE required=true").forEach { doc ->
            jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(?,?,?,?,true,'AGREED',now())",
                UUID.randomUUID(), doc["id"], user, if (doc["kind"] == "GUARDIAN") child else null)
        }
        access = auth.enterStudent(parent.refreshToken, child, auth.authenticate(parent.accessToken)).accessToken
    }

    @AfterEach fun cleanup() {
        if (::user.isInitialized) {
            jdbc.update("DELETE FROM idempotency_record WHERE user_id=?", user)
            jdbc.update("DELETE FROM consent WHERE subject_user_id=?", user)
            jdbc.update("DELETE FROM refresh_token WHERE user_id=?", user)
            jdbc.update("DELETE FROM auth_session WHERE user_id=?", user)
            jdbc.update("DELETE FROM guardianship WHERE parent_user_id=?", user)
            jdbc.update("DELETE FROM user_account WHERE id=?", user)
            jdbc.update("DELETE FROM student WHERE id=?", child)
        }
        documents.forEach { jdbc.update("DELETE FROM consent_document WHERE id=?", it) }; documents.clear()
        assertNull(UserContextHolder.currentOrNull())
    }

    private fun call(method: String, path: String, key: UUID? = null, content: String? = null, bearer: String = access,
                     ifMatch: String? = null) = mvc.perform(request(org.springframework.http.HttpMethod.valueOf(method), path)
        .header("Authorization", "Bearer $bearer").header("X-User-Id", "forged-user").header("X-User-Role", "ADMIN")
        .header("X-Student-Scope", UUID.randomUUID().toString()).header("X-Internal-Token", "forged-token")
        .also { req ->
            key?.let { req.header("Idempotency-Key", it) }
            ifMatch?.let { req.header("If-Match", it) }
            content?.let { req.contentType(MediaType.APPLICATION_JSON).content(it) }
        })

    @Test fun `attempt details disable storage while preserving draft ETag across completion changes`() {
        listOf(
            "{\"finishedAt\":null,\"status\":\"IN_PROGRESS\"}",
            "{\"finishedAt\":\"2026-10-30T08:09:12Z\",\"status\":\"IN_PROGRESS\"}",
            "{\"finishedAt\":\"2026-10-30T08:09:12Z\",\"status\":\"COMPLETED\"}",
        ).forEach { detail ->
            stub.respond = { LearningHttpStub.Reply(body = detail,
                headers = mapOf("Content-Type" to "application/json", "ETag" to "\"2\"")) }
            call("GET", "/api/v1/attempts/$attempt").andExpect(status().isOk())
                .andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(header().string("ETag", "\"2\""))
                .andExpect(content().string(detail))
        }
    }

    @Test fun `all ten routes forward verified context method body and ETag`() {
        val mission = UUID.randomUUID()
        val routes = listOf("GET" to "/missions", "GET" to "/missions/$mission", "POST" to "/missions/$mission/attempts",
            "GET" to "/attempts/$attempt", "PUT" to "/attempts/$attempt/draft", "POST" to "/attempts/$attempt/hints",
            "POST" to "/attempts/$attempt/answers", "POST" to "/attempts/$attempt/finish", "POST" to "/attempts/$attempt/self-assessment",
            "POST" to "/attempts/$attempt/reflection")
        stub.respond = { LearningHttpStub.Reply(if (it.target.endsWith("/answers")) 201 else 200, "{ \"raw\": \"생각\" }", mapOf("Content-Type" to "application/json", "ETag" to "\"8\"")) }
        routes.forEach { (method, path) ->
            val hasBody = path.endsWith("/draft") || path.endsWith("/answers") || path.endsWith("/self-assessment") || path.endsWith("/reflection")
            call(method, "/api/v1$path", if (path.endsWith("/answers")) UUID.randomUUID() else null,
                if (hasBody) body else null, ifMatch = if (method == "PUT") "\"7\"" else null)
                .andExpect(status().`is`(if (path.endsWith("/answers")) 201 else 200))
                .andExpect(header().string("ETag", "\"8\""))
                .andExpect(content().string("{ \"raw\": \"생각\" }"))
            val received = stub.requests.last()
            assertEquals(method, received.method)
            val expectedQuery = when {
                method == "GET" && path == "/missions" -> "?grade=3&demo=false&page=0&size=20"
                method == "GET" && path.startsWith("/missions/") -> "?grade=3&demo=false"
                method == "POST" && path == "/missions/$mission/attempts" -> "?grade=3&demo=false"
                else -> ""
            }
            assertEquals("/internal$path$expectedQuery", received.target)
            assertEquals(user.toString(), received.header("X-User-Id")); assertEquals("STUDENT", received.header("X-User-Role"))
            assertEquals(child.toString(), received.header("X-Student-Scope")); assertEquals("repository-test-token", received.header("X-Internal-Token"))
            assertNull(received.header("Authorization"))
            if (hasBody) assertEquals(body, received.body)
            if (method == "PUT") assertEquals("\"7\"", received.header("If-Match"))
            if (path.endsWith("/answers")) assertNotNull(received.header("Idempotency-Key"))
        }
    }

    @Test fun `parent admin invalid token withdrawn link and cached foreign student cannot bypass auth`() {
        val parent = auth.login(GoogleProfile(subject, "$subject@example.test", null), null)
        call("GET", "/api/v1/missions", bearer = parent.accessToken).andExpect(status().isForbidden())
        call("GET", "/api/v1/missions", bearer = "forged").andExpect(status().isUnauthorized())
        val key = UUID.randomUUID()
        call("POST", answerPath, key, body).andExpect(status().isOk())
        jdbc.update("UPDATE guardianship SET status='UNLINKED',unlinked_at=now() WHERE parent_user_id=?", user)
        call("POST", answerPath, key, body).andExpect(status().isForbidden())
        jdbc.update("UPDATE user_account SET role='ADMIN' WHERE id=?", user)
        val admin = auth.login(GoogleProfile(subject, "$subject@example.test", null), null)
        call("GET", "/api/v1/missions", bearer = admin.accessToken).andExpect(status().isForbidden())
        assertEquals(1, stub.requests.size)
    }

    @Test fun `mission queries and attempt start use current verified profile and ignore client overrides`() {
        val mission = UUID.randomUUID()
        val routes = listOf("GET" to "/missions", "GET" to "/missions/$mission", "POST" to "/missions/$mission/attempts")
        // The same signed session must use current core data, never client values or a cached profile.
        listOf(5 to true, 3 to false).forEach { (grade, demo) ->
            jdbc.update("UPDATE student SET grade=?,is_demo=? WHERE id=?", grade, demo, child)
            routes.forEach { (method, path) ->
                val forgedQuery = "grade=6&grade=4&demo=${!demo}&demo=${!demo}&studentId=${UUID.randomUUID()}&page=1&size=2"
                call(method, "/api/v1$path?$forgedQuery").andExpect(status().isOk())
                val pagination = if (path == "/missions") "&page=1&size=2" else ""
                assertEquals("/internal$path?grade=$grade&demo=$demo$pagination", stub.requests.last().target)
                assertEquals(child.toString(), stub.requests.last().header("X-Student-Scope"))
            }
        }
        assertEquals(6, stub.requests.size)
    }

    @Test fun `attempt start preserves learning 201 for a newly created attempt`() {
        val mission = UUID.randomUUID()
        val response = "{ \"attemptId\":\"$attempt\", \"status\":\"IN_PROGRESS\" }"
        stub.respond = { LearningHttpStub.Reply(201, response) }

        call("POST", "/api/v1/missions/$mission/attempts?grade=6&demo=true")
            .andExpect(status().isCreated()).andExpect(content().string(response))

        assertEquals("/internal/missions/$mission/attempts?grade=3&demo=false", stub.requests.single().target)
    }

    @Test fun `attempt start preserves learning 200 for an existing in-progress attempt`() {
        val mission = UUID.randomUUID()
        val response = "{ \"attemptId\":\"$attempt\", \"status\":\"IN_PROGRESS\" }"
        stub.respond = { LearningHttpStub.Reply(200, response) }

        call("POST", "/api/v1/missions/$mission/attempts?grade=6&demo=true")
            .andExpect(status().isOk()).andExpect(content().string(response))

        assertEquals("/internal/missions/$mission/attempts?grade=3&demo=false", stub.requests.single().target)
    }

    @Test fun `mission queries and attempt start reject invalid session and unlinked student before forwarding`() {
        val mission = UUID.randomUUID()
        val routes = listOf("GET" to "/missions", "GET" to "/missions/$mission", "POST" to "/missions/$mission/attempts")
        routes.forEach { (method, path) ->
            call(method, "/api/v1$path?grade=5&demo=true", bearer = "forged").andExpect(status().isUnauthorized())
        }
        jdbc.update("UPDATE guardianship SET status='UNLINKED',unlinked_at=now() WHERE parent_user_id=?", user)
        routes.forEach { (method, path) ->
            call(method, "/api/v1$path?grade=5&demo=true").andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("CHILD_NOT_LINKED"))
        }
        assertTrue(stub.requests.isEmpty())
    }

    @Test fun `same key returns first exact status bytes and headers different body endpoint or scope is 422`() {
        val key = UUID.randomUUID()
        stub.respond = { LearningHttpStub.Reply(201, "{ \"answerId\":\"synthetic-answer\", \"version\":1 }",
            mapOf("Content-Type" to "application/json", "ETag" to "\"1\"", "Location" to "/answers/synthetic-answer")) }
        val first = call("POST", answerPath, key, body).andExpect(status().isCreated()).andReturn().response
        stub.respond = { error("A completed core record must not call learning") }
        val replay = call("POST", answerPath, key, body).andExpect(status().isCreated()).andReturn().response
        assertContentEquals(first.contentAsByteArray, replay.contentAsByteArray)
        assertEquals(first.getHeader("Location"), replay.getHeader("Location")); assertEquals(first.getHeader("ETag"), replay.getHeader("ETag"))
        call("POST", answerPath, key, "{}").andExpect(status().isUnprocessableEntity()).andExpect(jsonPath("$.code").value("IDEMPOTENCY_KEY_REUSED"))
        call("POST", "/api/v1/attempts/${UUID.randomUUID()}/answers", key, body).andExpect(status().isUnprocessableEntity())
        // Same account entering another child must not receive the first child's cached result.
        val session = auth.authenticate(access).session.id
        val otherChild = UUID.randomUUID()
        jdbc.update("INSERT INTO student(pin_failed_count,id,nickname,grade,birth_year,is_demo,status,created_at,updated_at) VALUES(0,?,'다른 학생',3,2017,false,'ACTIVE',now(),now())", otherChild)
        try {
            jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',now())", UUID.randomUUID(), user, otherChild)
            jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) SELECT ?,id,?,?,true,'AGREED',now() FROM consent_document WHERE kind='GUARDIAN' ORDER BY created_at DESC LIMIT 1", UUID.randomUUID(), user, otherChild)
            // Use a new signed token generated by the actual service's accompanied entry.
            val parent = auth.login(GoogleProfile(subject, "$subject@example.test", null), null)
            val otherAccess = auth.enterStudent(parent.refreshToken, otherChild, auth.authenticate(parent.accessToken)).accessToken
            call("POST", answerPath, key, body, bearer = otherAccess).andExpect(status().isUnprocessableEntity())
        } finally {
            jdbc.update("DELETE FROM consent WHERE student_id=?", otherChild)
            jdbc.update("DELETE FROM refresh_token WHERE user_id=?", user)
            jdbc.update("DELETE FROM auth_session WHERE user_id=? AND id<>?", user, session)
            jdbc.update("DELETE FROM guardianship WHERE student_id=?", otherChild)
            jdbc.update("DELETE FROM student WHERE id=?", otherChild)
        }
        assertEquals(1, stub.requests.size)
    }

    @Test fun `concurrent same key is 409 while first runs then replays once`() {
        val key = UUID.randomUUID(); val entered = CountDownLatch(1); val release = CountDownLatch(1)
        stub.respond = { entered.countDown(); check(release.await(10, TimeUnit.SECONDS)); LearningHttpStub.Reply(201) }
        Executors.newVirtualThreadPerTaskExecutor().use { executor ->
            val first = executor.submit<Int> { call("POST", answerPath, key, body).andReturn().response.status }
            try {
                assertTrue(entered.await(5, TimeUnit.SECONDS))
                call("POST", answerPath, key, body).andExpect(status().isConflict())
                    .andExpect(jsonPath("$.code").value("IDEMPOTENCY_IN_PROGRESS")).andExpect(header().string("Retry-After", "1"))
                call("POST", answerPath, key, "{}").andExpect(status().isUnprocessableEntity())
            } finally { release.countDown() }
            assertEquals(201, first.get(5, TimeUnit.SECONDS))
        }
        call("POST", answerPath, key, body).andExpect(status().isCreated())
        assertEquals(1, stub.requests.size)
    }

    @Test fun `learning committed but core result storage failed retries same downstream key without duplicate effect`() {
        val key = UUID.randomUUID(); val writes = AtomicInteger(); var saved: LearningHttpStub.Reply? = null
        stub.respond = { request ->
            assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND state='idle in transaction'", Int::class.java))
            assertEquals(key.toString(), request.header("Idempotency-Key"))
            saved ?: LearningHttpStub.Reply(201, "{\"version\":${writes.incrementAndGet()}}").also { saved = it }
        }
        // A real PostgreSQL write failure, restricted to this fixture/key; no production fault hook.
        jdbc.execute("ALTER TABLE idempotency_record ADD CONSTRAINT issue38_fail_store CHECK (idempotency_key<>'$key' OR response_status IS NULL) NOT VALID")
        try {
            call("POST", answerPath, key, body).andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("IDEMPOTENCY_UNAVAILABLE"))
        } finally { jdbc.execute("ALTER TABLE idempotency_record DROP CONSTRAINT issue38_fail_store") }
        call("POST", answerPath, key, body).andExpect(status().isCreated()).andExpect(jsonPath("$.version").value(1))
        call("POST", answerPath, key, body).andExpect(status().isCreated())
        assertEquals(2, stub.requests.size); assertEquals(1, writes.get())
    }

    @Test fun `unconfirmed 5xx retries expired records are replaced and retained for 24 hours`() {
        val key = UUID.randomUUID()
        stub.respond = { LearningHttpStub.Reply(503, "{\"code\":\"LEARNING_BUSY\"}", mapOf("Content-Type" to "application/problem+json")) }
        call("POST", answerPath, key, body).andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.code").value("LEARNING_BUSY"))
        assertNull(jdbc.queryForObject("SELECT response_status FROM idempotency_record WHERE idempotency_key=?", Int::class.javaObjectType, key))
        stub.respond = { LearningHttpStub.Reply(201) }
        call("POST", answerPath, key, body).andExpect(status().isCreated())
        val retention = jdbc.queryForObject("SELECT extract(epoch FROM expires_at-created_at) FROM idempotency_record WHERE idempotency_key=?", Double::class.java, key)!!
        assertTrue(retention in 86399.0..86401.0)
        jdbc.update("UPDATE idempotency_record SET expires_at=now()-interval '1 second' WHERE idempotency_key=?", key)
        call("POST", answerPath, key, body).andExpect(status().isCreated())
        assertEquals(3, stub.requests.size)
        jdbc.update("UPDATE idempotency_record SET expires_at=now()-interval '1 second' WHERE idempotency_key=?", key)
        assertEquals(1, idempotency.deleteExpired())
    }

    @Test fun `first learning client error is replayed without a second call`() {
        val key = UUID.randomUUID()
        val error = "{ \"status\":422,\"code\":\"ANSWER_INCOMPLETE\",\"errors\":[\"text\"] }"
        stub.respond = { LearningHttpStub.Reply(422, error, mapOf("Content-Type" to "application/problem+json")) }
        call("POST", answerPath, key, body).andExpect(status().isUnprocessableEntity()).andExpect(content().string(error))
        stub.respond = { LearningHttpStub.Reply(201) }
        call("POST", answerPath, key, body).andExpect(status().isUnprocessableEntity()).andExpect(content().string(error))
        assertEquals(1, stub.requests.size)
    }

    @Test fun `draft conflict and learning problem details extension and arbitrary error status are preserved`() {
        val problem = "{ \"type\":\"about:blank\",\"title\":\"초안 충돌\",\"status\":409,\"code\":\"ATTEMPT_DRAFT_CONFLICT\",\"latest\":{\"version\":8} }"
        stub.respond = { LearningHttpStub.Reply(409, problem, mapOf("Content-Type" to "application/problem+json", "ETag" to "\"8\"")) }
        call("PUT", "/api/v1/attempts/$attempt/draft", content = "{\"content\":{\"memo\":\"생각\"}}", ifMatch = "\"7\"")
            .andExpect(status().isConflict()).andExpect(content().string(problem)).andExpect(header().string("ETag", "\"8\""))
        listOf(400, 403, 404, 409, 422, 429, 499, 503).forEach { code ->
            stub.respond = { LearningHttpStub.Reply(code, "{\"status\":$code,\"code\":\"LEARNING_ERROR\",\"extra\":[1]}",
                mapOf("Content-Type" to "application/problem+json", "Retry-After" to "4")) }
            call("GET", "/api/v1/attempts/$attempt").andExpect(status().`is`(code))
                .andExpect(jsonPath("$.extra[0]").value(1)).andExpect(header().string("Retry-After", "4"))
        }
    }

    @Test fun `invalid request metadata and JSON never call learning`() {
        call("POST", answerPath, content = body).andExpect(status().isBadRequest())
        call("POST", answerPath, UUID.randomUUID(), "{").andExpect(status().isBadRequest())
        call("POST", answerPath, UUID.randomUUID(), "null").andExpect(status().isBadRequest())
        call("PUT", "/api/v1/attempts/$attempt/draft", content = "{}").andExpect(status().isBadRequest())
        call("GET", "/api/v1/attempts/not-uuid").andExpect(status().isBadRequest())
        assertTrue(stub.requests.isEmpty())
        client.circuit.transitionToOpenState()
        call("GET", "/api/v1/missions").andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.code").value("LEARNING_CIRCUIT_OPEN")).andExpect(header().string("Retry-After", "30"))
        assertTrue(stub.requests.isEmpty())
    }
}
