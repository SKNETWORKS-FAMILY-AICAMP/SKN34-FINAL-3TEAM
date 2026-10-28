package com.sagomungchi.core.learning

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core._common.security.UserContextHolder
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
import kotlin.test.*

/** Real auth/filter/JWT, HTTP client and PostgreSQL. Only learning is a contract double.
 * Committed data is necessary to test separate connections; unique fixtures are explicitly removed.
 * The database is the disposable PostgresRepositoryTest DB, never the running compose DB.
 */
@AutoConfigureMockMvc
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class DashboardIntegrationTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var client: LearningClient
    private lateinit var user: UUID
    private lateinit var child: UUID
    private lateinit var access: String
    private lateinit var subject: String
    private val documents = mutableListOf<UUID>()
    private val attempt = UUID.randomUUID()

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
        jdbc.update("INSERT INTO student(id,nickname,grade,birth_year,is_demo,status,created_at,updated_at) VALUES(?,'테스트 학생',3,2017,false,'ACTIVE',now(),now())", child)
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

    private fun parentToken() = auth.login(GoogleProfile(subject, "$subject@example.test", null), null).accessToken
    private val period = "\"period\":{\"from\":\"2026-10-01\",\"to\":\"2026-10-07\"}"
    private fun attemptJson(id: UUID = attempt, owner: UUID = child) = """{"attemptId":"$id","studentId":"$owner","mission":{"title":"mission"},"status":"IN_PROGRESS","answers":[],"helped":false,"draft":{"version":1,"content":{"memo":"PRIVATE-MEMO","answer":{}}},"nested":{"memo":"PRIVATE-NESTED"}}"""
    private fun reply(resource: String, parent: Boolean = false, state: String = "NO_RECORD"): String {
        val identity = "studentId"
        val base = "\"$identity\":\"$child\",\"state\":\"$state\",$period"
        return when (resource) {
            "home" -> """{$base,"resume":${attemptJson()},"missions":[]}"""
            "summary" -> """{$base,"inclusionRule":"P08","metrics":[{"label":"sample","value":null,"count":3,"numerator":3,"denominator":4,"formula":"provider formula",$period,"sourceType":"RECORD","state":"INSUFFICIENT_SAMPLE"}]}"""
            "attempts" -> """{$base,"inclusionRule":"P08","items":[${attemptJson()}],"page":0,"size":20,"totalElements":1}"""
            "thinking-types" -> {
                val types = listOf("ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT").joinToString(",") {
                    """{"type":"$it","state":"NO_RECORD","missions":[]}"""
                }
                """{$base,"items":[$types]}"""
            }
            "detail" -> attemptJson().dropLast(1) + ",\"state\":\"OK\",$period}"
            else -> """{$base,"items":[]}"""
        }
    }

    @Test fun `seven routes authenticate and forward one student with trace and internal token`() {
        val parent = parentToken()
        val routes = listOf(
            Triple("/students/me/home", "home", false),
            Triple("/students/me/attempts", "attempts", false),
            Triple("/students/me/thinking-activities", "thinking-activities", false),
            Triple("/children/$child/summary", "summary", true),
            Triple("/children/$child/thinking-types", "thinking-types", true),
            Triple("/children/$child/attempts", "attempts", true),
            Triple("/children/$child/attempts/$attempt", "detail", true))
        routes.forEach { (path, resource, isParent) ->
            stub.respond = { request -> LearningHttpStub.Reply(body = if (request.target.startsWith("/internal/attempts/")) attemptJson() else reply(resource, isParent)) }
            val result = call("GET", "/api/v1$path?from=2026-10-01&to=2026-10-07", bearer = if (isParent) parent else access)
                .andExpect(status().isOk()).andExpect(jsonPath("$.period.from").value("2026-10-01"))
                .andReturn().response.contentAsString
            val received = if (resource == "home") stub.requests[stub.requests.size - 2] else stub.requests.last()
            if (resource == "home") assertEquals("/internal/attempts/$attempt", stub.requests.last().target)
            val suffix = if (resource == "detail") "attempts/$attempt" else resource
            assertTrue(received.target.startsWith("/internal/records/students/$child/$suffix?from=2026-10-01&to=2026-10-07"))
            assertEquals(child.toString(), received.header("X-Student-Scope"))
            assertEquals(user.toString(), received.header("X-User-Id"))
            assertEquals(if (isParent) "PARENT" else "STUDENT", received.header("X-User-Role"))
            assertEquals("repository-test-token", received.header("X-Internal-Token"))
            assertNull(received.header("Authorization"))
            if (resource == "home") { assertTrue(result.contains("PRIVATE-MEMO")); assertTrue(received.target.endsWith("&grade=3&demo=false")) }
            if (isParent || resource == "attempts") { assertFalse(result.contains("PRIVATE")); assertFalse(result.contains("\"draft\"")); assertFalse(result.contains("\"memo\"")) }
        }
    }

    @Test fun `parent forwards only selected child from multiple authorized children and restores context`() {
        val other = UUID.randomUUID()
        jdbc.update("INSERT INTO student(id,nickname,grade,birth_year,is_demo,status,created_at,updated_at) VALUES(?,'other',3,2017,false,'ACTIVE',now(),now())", other)
        jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',now())", UUID.randomUUID(), user, other)
        jdbc.queryForList("SELECT id FROM consent_document WHERE kind='GUARDIAN'").forEach { doc ->
            jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(?,?,?,?,true,'AGREED',now())", UUID.randomUUID(), doc["id"], user, other)
        }
        try {
            val token = parentToken()
            stub.respond = { LearningHttpStub.Reply(body = reply("summary", true)) }
            val trace = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
            mvc.perform(get("/api/v1/children/$child/summary").header("Authorization", "Bearer $token").header("traceparent", trace))
                .andExpect(status().isOk())
            assertEquals(child.toString(), stub.requests.single().header("X-Student-Scope"))
            assertEquals(trace, stub.requests.single().header("traceparent"))
            assertNull(UserContextHolder.currentOrNull())
        } finally {
            jdbc.update("DELETE FROM consent WHERE student_id=?", other)
            jdbc.update("DELETE FROM guardianship WHERE student_id=?", other)
            jdbc.update("DELETE FROM student WHERE id=?", other)
        }
    }

    @Test fun `unauthenticated foreign child wrong roles inactive child and withdrawn consent never call learning`() {
        val parent = parentToken()
        mvc.perform(get("/api/v1/students/me/home")).andExpect(status().isUnauthorized())
        call("GET", "/api/v1/students/me/home", bearer = parent).andExpect(status().isForbidden())
        call("GET", "/api/v1/children/$child/summary").andExpect(status().isForbidden())
        call("GET", "/api/v1/children/${UUID.randomUUID()}/summary", bearer = parent).andExpect(status().isForbidden())
        jdbc.update("UPDATE student SET status='DELETION_REQUESTED' WHERE id=?", child)
        call("GET", "/api/v1/children/$child/summary", bearer = parent).andExpect(status().isForbidden())
        jdbc.update("UPDATE student SET status='ACTIVE' WHERE id=?", child)
        jdbc.update("UPDATE consent SET status='WITHDRAWN',agreed=false,withdrawn_at=now() WHERE student_id=?", child)
        call("GET", "/api/v1/children/$child/summary", bearer = parent).andExpect(status().isForbidden())
        call("GET", "/api/v1/students/me/home").andExpect(status().isForbidden())
        assertTrue(stub.requests.isEmpty())
    }

    @Test fun `dates page and status are validated and only accepted parameters forwarded`() {
        stub.respond = { LearningHttpStub.Reply(body = reply("attempts")) }
        val path = "/api/v1/students/me/attempts"
        listOf("from=2026-10-01", "to=2026-10-07", "from=2026-02-30&to=2026-03-01", "from=2026-10-08&to=2026-10-01", "page=-1", "size=0", "size=101", "status=FAILED", "page=abc").forEach {
            call("GET", "$path?$it").andExpect(status().isBadRequest())
        }
        assertTrue(stub.requests.isEmpty())
        call("GET", "$path?from=2026-10-01&to=2026-10-07&page=2&size=100&status=COMPLETED&studentId=forged&grade=6")
            .andExpect(status().isOk())
        assertEquals("/internal/records/students/$child/attempts?from=2026-10-01&to=2026-10-07&page=2&size=100&status=COMPLETED", stub.requests.single().target)
    }

    @Test fun `learning metric period and every query state are preserved without computation`() {
        val parent = parentToken()
        listOf("NO_RECORD", "INSUFFICIENT_SAMPLE", "OK", "PROCESSING", "FAILED").forEach { state ->
            stub.respond = { LearningHttpStub.Reply(body = reply("summary", true, state)) }
            call("GET", "/api/v1/children/$child/summary", bearer = parent)
                .andExpect(status().isOk()).andExpect(jsonPath("$.state").value(state))
                .andExpect(jsonPath("$.metrics[0].value").doesNotExist())
                .andExpect(jsonPath("$.metrics[0].count").value(3))
                .andExpect(jsonPath("$.metrics[0].denominator").value(4))
                .andExpect(jsonPath("$.metrics[0].formula").value("provider formula"))
                .andExpect(jsonPath("$.period.to").value("2026-10-07"))
        }
    }

    @Test fun `provider failures keep HTTP errors and sanitize private extensions`() {
        val parent = parentToken()
        listOf(403, 404, 503, 504).forEach { code ->
            stub.respond = { LearningHttpStub.Reply(code, """{"status":$code,"code":"QUERY_FAILED","memo":"PRIVATE","latest":{"draft":{"content":{"memo":"PRIVATE"}}},"extensions":[{"memo":"PRIVATE-ARRAY"},{"values":[{"draft":{"content":{"memo":"PRIVATE-DEEP"}}}]}],"retryable":true}""", mapOf("Content-Type" to "application/problem+json")) }
            val response = call("GET", "/api/v1/children/$child/summary", bearer = parent)
                .andExpect(status().`is`(code)).andExpect(jsonPath("$.code").value("QUERY_FAILED"))
                .andExpect(jsonPath("$.retryable").value(true)).andReturn().response.contentAsString
            assertFalse(response.contains("PRIVATE")); assertFalse(response.contains("NO_RECORD"))
        }
    }

    @Test fun `metric decimal precision survives privacy serialization`() {
        val number = "0.12345678901234567890123456789"
        stub.respond = { LearningHttpStub.Reply(body = reply("summary", true).replace("\"value\":null", "\"value\":$number")) }
        val response = call("GET", "/api/v1/children/$child/summary", bearer = parentToken())
            .andExpect(status().isOk()).andReturn().response.contentAsString
        assertTrue(response.contains("\"value\":$number"))
    }

    @Test fun `malformed foreign and premature reveal success fail explicitly`() {
        val parent = parentToken()
        listOf("broken", "{}", reply("summary", true).replace(child.toString(), UUID.randomUUID().toString())).forEach { body ->
            stub.respond = { LearningHttpStub.Reply(body = body) }
            call("GET", "/api/v1/children/$child/summary", bearer = parent)
                .andExpect(status().isBadGateway()).andExpect(jsonPath("$.code").value("LEARNING_CONTRACT_INVALID"))
        }
        stub.respond = { LearningHttpStub.Reply(body = reply("detail").replace("\"answers\":[]", "\"answers\":[],\"reveal\":\"secret answer\"")) }
        call("GET", "/api/v1/children/$child/attempts/$attempt", bearer = parent).andExpect(status().isBadGateway())
        stub.respond = { LearningHttpStub.Reply(body = reply("detail").replace("\"answers\":[]", "\"answers\":[],\"finishedAt\":\"\",\"reveal\":\"secret answer\"")) }
        call("GET", "/api/v1/children/$child/attempts/$attempt", bearer = parent).andExpect(status().isBadGateway())
    }

    @Test fun `empty home preserves no record while resume retains unsubmitted draft`() {
        stub.respond = { request -> LearningHttpStub.Reply(body = if (request.target.startsWith("/internal/attempts/")) attemptJson() else reply("home")) }
        call("GET", "/api/v1/students/me/home").andExpect(status().isOk())
            .andExpect(jsonPath("$.state").value("NO_RECORD"))
            .andExpect(jsonPath("$.resume.answers").isEmpty())
            .andExpect(jsonPath("$.resume.draft.content.memo").value("PRIVATE-MEMO"))
            .andExpect(jsonPath("$.student.id").value(child.toString()))
        stub.respond = { LearningHttpStub.Reply(body = """{"studentId":"$child","state":"NO_RECORD",$period,"resume":null,"missions":[]}""") }
        call("GET", "/api/v1/students/me/home").andExpect(status().isOk()).andExpect(jsonPath("$.resume").doesNotExist())
    }

    @Test fun `invalid metrics and incomplete thinking types are contract errors not empty results`() {
        val parent = parentToken()
        val valid = reply("summary", true)
        listOf(
            valid.replace("\"count\":3", "\"count\":null"),
            valid.replace("\"denominator\":4", "\"denominator\":-1"),
            valid.replace("\"value\":null,", ""),
            valid.replace("\"formula\":\"provider formula\"", "\"formula\":4"),
            valid.replace("\"sourceType\":\"RECORD\"", "\"sourceType\":\"UNKNOWN\"")
        ).forEach { payload ->
            stub.respond = { LearningHttpStub.Reply(body = payload) }
            call("GET", "/api/v1/children/$child/summary", bearer = parent)
                .andExpect(status().isBadGateway()).andExpect(jsonPath("$.code").value("LEARNING_CONTRACT_INVALID"))
        }
        listOf(reply("thinking-activities", true), reply("thinking-types", true).replace("CREATE", "ANALYZE")).forEach { payload ->
            stub.respond = { LearningHttpStub.Reply(body = payload) }
            call("GET", "/api/v1/children/$child/thinking-types", bearer = parent).andExpect(status().isBadGateway())
        }
        stub.respond = { LearningHttpStub.Reply(body = reply("thinking-types", true)) }
        call("GET", "/api/v1/children/$child/thinking-types", bearer = parent)
            .andExpect(status().isOk()).andExpect(jsonPath("$.childId").value(child.toString()))
            .andExpect(jsonPath("$.studentId").doesNotExist()).andExpect(jsonPath("$.items.length()").value(5))
    }

    @Test fun `unlinked guardian and foreign attempt in a valid child envelope are rejected`() {
        val parent = parentToken()
        stub.respond = { LearningHttpStub.Reply(body = reply("attempts", true).replace(attemptJson(), attemptJson(owner = UUID.randomUUID()))) }
        call("GET", "/api/v1/children/$child/attempts", bearer = parent).andExpect(status().isBadGateway())
        stub.reset()
        jdbc.update("UPDATE guardianship SET status='UNLINKED',unlinked_at=now() WHERE student_id=?", child)
        call("GET", "/api/v1/children/$child/summary", bearer = parent).andExpect(status().isForbidden())
        assertTrue(stub.requests.isEmpty())
    }

    @Test fun `student home uses existing private attempt API and does not hide its failure or foreign response`() {
        stub.respond = { request -> if (request.target.startsWith("/internal/attempts/"))
            LearningHttpStub.Reply(503, """{"code":"LEARNING_UNAVAILABLE","status":503}""")
            else LearningHttpStub.Reply(body = reply("home")) }
        call("GET", "/api/v1/students/me/home").andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.resume").doesNotExist())
        assertEquals(child.toString(), stub.requests.last().header("X-Student-Scope"))
        assertEquals("STUDENT", stub.requests.last().header("X-User-Role"))
        stub.respond = { request -> LearningHttpStub.Reply(body = if (request.target.startsWith("/internal/attempts/"))
            attemptJson(owner = UUID.randomUUID()) else reply("home")) }
        call("GET", "/api/v1/students/me/home").andExpect(status().isBadGateway())
        stub.respond = { request -> LearningHttpStub.Reply(body = if (request.target.startsWith("/internal/attempts/"))
            attemptJson().replace("\"version\":1,", "") else reply("home")) }
        call("GET", "/api/v1/students/me/home").andExpect(status().isBadGateway())
    }
}
