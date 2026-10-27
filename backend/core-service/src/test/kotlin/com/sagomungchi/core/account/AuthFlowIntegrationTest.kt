package com.sagomungchi.core.account

import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.client.GoogleOAuthClient
import com.sagomungchi.core.account.controller.AuthCookies
import com.sagomungchi.core.account.domain.GoogleProfile
import com.sagomungchi.core.account.service.AuthService
import com.sagomungchi.core.account.service.TokenService
import jakarta.servlet.http.Cookie
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.ArgumentMatchers.anyString
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.context.annotation.Import
import org.springframework.web.bind.annotation.RestController
import org.springframework.web.bind.annotation.GetMapping
import com.sagomungchi.core._common.security.UserContextHolder
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.Callable
import java.util.concurrent.Executors
import kotlin.test.*

@AutoConfigureMockMvc
@Import(AuthFlowIntegrationTest.ContextProbe::class)
@TestPropertySource(properties = ["app.auth.cookie-secure=false", "app.auth.web-origin=http://localhost:5173",
    "spring.rabbitmq.listener.simple.auto-startup=false"])
class AuthFlowIntegrationTest : IntegrationTestSupport() {
    @RestController
    class ContextProbe {
        @GetMapping("/api/v1/context-probe")
        fun context(): Map<String, Any?> {
            val context = UserContextHolder.current()
            return mapOf("userId" to context.userId, "role" to context.role, "scope" to context.studentScope)
        }
    }
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var mvc: MockMvc
    @MockitoBean lateinit var google: GoogleOAuthClient
    private lateinit var subject: String
    @BeforeEach fun prepare() { subject = UUID.randomUUID().toString() }
    private fun login() = auth.login(GoogleProfile(subject, "$subject@example.test", "보호자"), null)

    @Test fun `device entry paths reach MVC without Bearer while accompanied entry stays protected`() {
        mvc.get("/api/v1/auth/student/profiles").andExpect {
            status { isNotFound() }; jsonPath("$.code") { value("NOT_FOUND") }
        }
        listOf("/api/v1/auth/student/devices", "/api/v1/auth/student/login").forEach { path ->
            mvc.post(path) {
                header("Origin", "http://localhost:5173"); header("X-Requested-With", "XMLHttpRequest")
            }.andExpect { status { isNotFound() }; jsonPath("$.code") { value("NOT_FOUND") } }
        }
        mvc.post("/api/v1/auth/student-sessions") {
            header("Origin", "http://localhost:5173"); header("X-Requested-With", "XMLHttpRequest")
        }.andExpect { status { isUnauthorized() }; jsonPath("$.code") { value("UNAUTHENTICATED") } }
    }
    private fun consent(user: UUID) {
        listOf("TERMS", "PRIVACY").forEach { kind ->
            val id = UUID.randomUUID()
            jdbc.update("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(?,?,?,'안내','본문',true,CURRENT_DATE,?)",
                id, kind, UUID.randomUUID().toString(), OffsetDateTime.now())
            jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,agreed,status,agreed_at) VALUES(?,?,?,true,'AGREED',?)", UUID.randomUUID(), id, user, OffsetDateTime.now())
        }
    }
    private fun child(user: UUID): UUID {
        val id = UUID.randomUUID()
        jdbc.update("INSERT INTO student(id,nickname,grade,birth_year,is_demo,status,created_at,updated_at) VALUES(?,'학생',3,2017,false,'ACTIVE',?,?)", id, OffsetDateTime.now(), OffsetDateTime.now())
        jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',?)", UUID.randomUUID(), user, id, OffsetDateTime.now())
        val existingDocument = jdbc.queryForList("SELECT id FROM consent_document WHERE kind='GUARDIAN' ORDER BY created_at DESC LIMIT 1", UUID::class.java).firstOrNull()
        val document = existingDocument ?: UUID.randomUUID().also { value ->
            jdbc.update("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(?,'GUARDIAN',?,'동의','본문',true,CURRENT_DATE,?)", value, UUID.randomUUID().toString(), OffsetDateTime.now())
        }
        jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(?,?,?,?,true,'AGREED',?)", UUID.randomUUID(), document, user, id, OffsetDateTime.now())
        return id
    }
    @Test fun `Google callback binds browser state and sets only refresh cookie before web redirect`() {
        val state = "browser-state"
        `when`(google.exchange(anyString(), anyString(), anyString())).thenReturn(GoogleProfile(subject, "$subject@example.test", "보호자"))
        val callback = mvc.get("/api/v1/auth/google/callback") {
            param("code", "code"); param("state", state)
            cookie(Cookie(AuthCookies.STATE, tokens.oauthState(state, "nonce", "verifier")))
        }.andExpect {
            status { isFound() }; header { string("Location", "http://localhost:5173/oauth/complete") }
            header { exists("Set-Cookie") }
        }.andReturn().response
        assertTrue(callback.getHeaders("Set-Cookie").any { it.contains("SameSite=Strict") && it.contains("HttpOnly") })
        mvc.get("/api/v1/auth/google/callback") { param("code", "code"); param("state", "forged") }
            .andExpect { status { isFound() }; header { string("Location", "http://localhost:5173/login?oauthError=OAUTH_FAILED") } }
    }
    @Test fun `refresh rotates hashed token keeps absolute expiry and replay revocation commits`() {
        val first = login()
        val next = auth.refresh(first.refreshToken)
        assertNotEquals(first.refreshToken, next.refreshToken)
        assertEquals(requireNotNull(first.refreshExpiresAt).toInstant(), requireNotNull(next.refreshExpiresAt).toInstant())
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM refresh_token WHERE token_hash=?", Int::class.java, first.refreshToken))
        assertEquals("REFRESH_REUSED", assertFailsWith<BusinessException> { auth.refresh(first.refreshToken) }.code)
        assertFailsWith<BusinessException> { auth.authenticate(next.accessToken) }
        assertFailsWith<BusinessException> { auth.refresh(next.refreshToken) }
    }
    @Test fun `two concurrent rotations cannot both succeed and replay ends that session`() {
        val first = login()
        val executor = Executors.newFixedThreadPool(2)
        try {
            val outcomes = executor.invokeAll(List(2) { Callable { runCatching { auth.refresh(first.refreshToken) } } }).map { it.get() }
            assertEquals(1, outcomes.count { it.isSuccess })
            assertEquals("REFRESH_REUSED", (outcomes.single { it.isFailure }.exceptionOrNull() as BusinessException).code)
            assertFailsWith<BusinessException> { auth.authenticate(outcomes.single { it.isSuccess }.getOrThrow().accessToken) }
        } finally { executor.shutdownNow() }
    }
    @Test fun `student transition issues no refresh and cannot restore parent credentials`() {
        val first = login(); consent(first.identity.account.id)
        val id = child(first.identity.account.id)
        val student = auth.enterStudent(first.refreshToken, id, auth.authenticate(first.accessToken))
        assertNull(student.refreshToken)
        assertNull(student.refreshExpiresAt)
        assertEquals("SESSION_CHANGED", assertFailsWith<BusinessException> { auth.authenticate(first.accessToken) }.code)
        assertFailsWith<BusinessException> { auth.refresh(first.refreshToken) }
        assertEquals("STUDENT", auth.authenticate(student.accessToken).session.role)
        assertEquals(setOf(id), student.identity.studentScope)
        mvc.get("/api/v1/me") { header("Authorization", "Bearer ${student.accessToken}") }.andExpect {
            status { isOk() }; jsonPath("$.child.id") { value(id.toString()) }; jsonPath("$.role") { value("STUDENT") }
            jsonPath("$.email") { doesNotExist() }; jsonPath("$.permissions") { doesNotExist() }
        }
        listOf("/api/v1/me/consents", "/api/v1/student-devices", "/api/v1/children").forEach { path ->
            mvc.get(path) { header("Authorization", "Bearer ${student.accessToken}") }.andExpect { status { isForbidden() } }
        }
        mvc.post("/api/v1/auth/logout") {
            header("Origin", "http://localhost:5173"); header("X-Requested-With", "XMLHttpRequest")
            header("Authorization", "Bearer ${student.accessToken}")
        }.andExpect { status { isNoContent() } }
        assertFailsWith<BusinessException> { auth.authenticate(student.accessToken) }
    }
    @Test fun `student HTTP response clears parent refresh cookie and guardian withdrawal blocks student`() {
        val first = login(); consent(first.identity.account.id)
        val id = child(first.identity.account.id)
        val response = mvc.post("/api/v1/auth/student-sessions") {
            header("Origin", "http://localhost:5173"); header("X-Requested-With", "XMLHttpRequest")
            header("Authorization", "Bearer ${first.accessToken}"); cookie(Cookie(AuthCookies.REFRESH, first.refreshToken))
            contentType = org.springframework.http.MediaType.APPLICATION_JSON; content = "{\"childId\":\"$id\"}"
        }.andExpect {
            status { isOk() }; jsonPath("$.role") { value("STUDENT") }; jsonPath("$.refreshToken") { doesNotExist() }
            header { string("Set-Cookie", org.hamcrest.Matchers.containsString("Max-Age=0")) }
        }.andReturn().response
        val access = com.fasterxml.jackson.module.kotlin.jacksonObjectMapper().readTree(response.contentAsString).get("accessToken").asText()
        jdbc.update("UPDATE consent SET status='WITHDRAWN',withdrawn_at=? WHERE student_id=?", OffsetDateTime.now(), id)
        assertEquals("CHILD_NOT_LINKED", assertFailsWith<BusinessException> { auth.authenticate(access) }.code)
    }
    @Test fun `foreign child returns 403 and missing consent blocks protected requests`() {
        val first = login()
        mvc.get("/api/v1/me") { header("Authorization", "Bearer ${first.accessToken}") }.andExpect {
            status { isOk() }; jsonPath("$.nextAction") { value("CONSENT_REQUIRED") }
        }
        mvc.get("/api/v1/children") { header("Authorization", "Bearer ${first.accessToken}") }.andExpect {
            status { isForbidden() }; jsonPath("$.code") { value("CONSENT_REQUIRED") }
        }
        consent(first.identity.account.id)
        mvc.post("/api/v1/auth/student-sessions") {
            header("Origin", "http://localhost:5173"); header("X-Requested-With", "XMLHttpRequest")
            header("Authorization", "Bearer ${first.accessToken}"); cookie(Cookie(AuthCookies.REFRESH, first.refreshToken))
            contentType = org.springframework.http.MediaType.APPLICATION_JSON; content = "{\"childId\":\"${UUID.randomUUID()}\"}"
        }.andExpect { status { isForbidden() }; jsonPath("$.code") { value("CHILD_NOT_LINKED") } }
    }
    @Test fun `cookie endpoint requires exact Origin and custom header logout only revokes current device`() {
        val first = login(); val other = login()
        mvc.post("/api/v1/auth/refresh") { cookie(Cookie(AuthCookies.REFRESH, first.refreshToken)) }.andExpect { status { isForbidden() } }
        mvc.post("/api/v1/auth/logout") {
            header("Origin", "http://localhost:5173"); header("X-Requested-With", "XMLHttpRequest")
            cookie(Cookie(AuthCookies.REFRESH, first.refreshToken))
        }.andExpect { status { isNoContent() }; header { string("Set-Cookie", org.hamcrest.Matchers.containsString("Max-Age=0")) } }
        assertFailsWith<BusinessException> { auth.authenticate(first.accessToken) }
        assertEquals("PARENT", auth.authenticate(other.accessToken).session.role)
    }
    @Test fun `admin permissions are current database values and cannot be supplied in public headers`() {
        val parent = login(); val id = parent.identity.account.id
        jdbc.update("UPDATE user_account SET role='ADMIN' WHERE id=?", id)
        jdbc.update("INSERT INTO admin_permission(user_id,permission,granted_by,granted_at) VALUES(?,'CONTENT',?,?)", id, id, OffsetDateTime.now())
        val admin = login()
        mvc.get("/api/v1/admin/ai-usage") {
            header("Authorization", "Bearer ${admin.accessToken}"); header("X-User-Role", "ADMIN"); header("X-Student-Scope", "forged")
        }.andExpect { status { isForbidden() } }
        assertEquals(setOf("CONTENT"), auth.authenticate(admin.accessToken).permissions)
        jdbc.update("DELETE FROM admin_permission WHERE user_id=?", id)
        assertTrue(auth.authenticate(admin.accessToken).permissions.isEmpty())
    }
    @Test fun `same email never links different Google subject and legacy password account is preserved`() {
        val first = login()
        assertEquals("ACCOUNT_EXISTS", assertFailsWith<BusinessException> {
            auth.login(GoogleProfile("other-$subject", first.identity.account.email, null), null)
        }.code)
        assertEquals(first.identity.account.id, login().identity.account.id)
        val legacy = UUID.randomUUID()
        jdbc.update("INSERT INTO user_account(id,role,login_id,password_hash,status,is_demo,created_at,updated_at) VALUES(?,'PARENT',?,'legacy-hash','ACTIVE',false,?,?)",
            legacy, "legacy-$subject@example.test", OffsetDateTime.now(), OffsetDateTime.now())
        assertFailsWith<BusinessException> { auth.login(GoogleProfile("new-$subject", "legacy-$subject@example.test", null), null) }
        assertEquals("legacy-hash", jdbc.queryForObject("SELECT password_hash FROM user_account WHERE id=?", String::class.java, legacy))
    }
    @Test fun `public caller cannot forge internal context and request thread is cleared`() {
        val first = login(); consent(first.identity.account.id)
        val id = child(first.identity.account.id)
        mvc.get("/api/v1/context-probe") {
            header("Authorization", "Bearer ${first.accessToken}")
            header("X-User-Id", "attacker"); header("X-User-Role", "ADMIN"); header("X-Student-Scope", "foreign")
        }.andExpect {
            status { isOk() }; jsonPath("$.userId") { value(first.identity.account.id.toString()) }
            jsonPath("$.role") { value("PARENT") }; jsonPath("$.scope[0]") { value(id.toString()) }
        }
        assertNull(UserContextHolder.currentOrNull())
        val invalid = first.accessToken.dropLast(8) + "AAAAAAAA"
        mvc.get("/api/v1/me") { header("Authorization", "Bearer $invalid") }
            .andExpect { status { isUnauthorized() }; jsonPath("$.code") { value("UNAUTHENTICATED") } }
    }
    @Test fun `consent withdrawal immediately blocks protected APIs`() {
        val first = login(); consent(first.identity.account.id)
        jdbc.update("UPDATE consent SET status='WITHDRAWN',withdrawn_at=? WHERE subject_user_id=?", OffsetDateTime.now(), first.identity.account.id)
        mvc.get("/api/v1/context-probe") { header("Authorization", "Bearer ${first.accessToken}") }
            .andExpect { status { isForbidden() }; jsonPath("$.code") { value("CONSENT_REQUIRED") } }
    }
}
