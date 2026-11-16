package com.sagomungchi.core.account

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.controller.AuthCookies
import com.sagomungchi.core.account.domain.GoogleProfile
import com.sagomungchi.core.account.domain.ReauthPurpose
import com.sagomungchi.core.account.service.AccountWithdrawalService
import com.sagomungchi.core.account.service.AuthService
import com.sagomungchi.core.account.service.ReauthenticationService
import com.sagomungchi.core.account.service.dto.IssuedAuth
import com.sagomungchi.core.guardianship.service.PinHasher
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.ResultActionsDsl
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import org.springframework.test.web.servlet.put
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.*

/** #415 parent ID/password signup, login and password re-confirmation (parent_credential). */
@AutoConfigureMockMvc
@TestPropertySource(properties = ["app.auth.cookie-secure=false", "app.auth.web-origin=http://localhost:5173",
    "app.auth.signup-limit-per-ip=3", "spring.rabbitmq.listener.simple.auto-startup=false"])
class ParentPasswordLoginIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var reauth: ReauthenticationService
    @Autowired lateinit var withdrawals: AccountWithdrawalService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var hasher: PinHasher

    private fun newId() = "p" + UUID.randomUUID().toString().replace("-", "").take(20)
    private fun newIp() = "10.${(1..250).random()}.${(1..250).random()}.${(1..250).random()}"
    private fun signup(id: String, password: String = PASSWORD, name: String = "보호자", ip: String = newIp(), browser: Boolean = true): ResultActionsDsl =
        mvc.post("/api/v1/auth/parent/signup") {
            if (browser) { header("Origin", ORIGIN); header("X-Requested-With", "XMLHttpRequest") }
            with { it.remoteAddr = ip; it }
            contentType = MediaType.APPLICATION_JSON
            content = json.writeValueAsString(mapOf("loginId" to id, "password" to password, "name" to name))
        }
    private fun login(id: String, password: String = PASSWORD) = mvc.post("/api/v1/auth/parent/login") {
        header("Origin", ORIGIN); header("X-Requested-With", "XMLHttpRequest"); contentType = MediaType.APPLICATION_JSON
        content = json.writeValueAsString(mapOf("loginId" to id, "password" to password))
    }
    private fun registered(id: String = newId()): IssuedAuth { signup(id).andExpect { status { isOk() } }; return auth.parentLogin(id, PASSWORD, null) }
    private fun userId(id: String) = jdbc.queryForObject("SELECT id FROM user_account WHERE login_id=?", UUID::class.java, id)!!
    private fun failedCount(user: UUID) = jdbc.queryForObject("SELECT failed_count FROM parent_credential WHERE user_id=?", Int::class.java, user)
    private fun code(block: () -> Unit) = assertFailsWith<BusinessException> { block() }.code
    private fun agreeRequired(user: UUID) = listOf("TERMS", "PRIVACY").forEach { kind ->
        val doc = jdbc.queryForObject("""SELECT id FROM consent_document WHERE kind=? AND effective_from <= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date
            ORDER BY effective_from DESC, created_at DESC, id DESC LIMIT 1""", UUID::class.java, kind)
        jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(?,?,?,NULL,true,'AGREED',?)",
            UUID.randomUUID(), doc, user, OffsetDateTime.now())
    }

    @Test fun `signup sets refresh cookie, starts consent onboarding and me reports the password method`() {
        val id = newId()
        val response = signup(id.uppercase()).andExpect {
            status { isOk() }; jsonPath("$.role") { value("PARENT") }; jsonPath("$.nextAction") { value("CONSENT_REQUIRED") }
            jsonPath("$.startPath") { value("/parent/onboarding") }; jsonPath("$.accessToken") { isString() }
        }.andReturn().response
        assertTrue(response.getHeaders("Set-Cookie").any { it.startsWith("${AuthCookies.REFRESH}=") && it.contains("HttpOnly") })
        val token = json.readTree(response.contentAsString)["accessToken"].asText()
        mvc.get("/api/v1/me") { header("Authorization", "Bearer $token") }.andExpect {
            status { isOk() }; jsonPath("$.authMethod") { value("PASSWORD") }; jsonPath("$.loginId") { value(id) }
            jsonPath("$.email") { value(null as Any?) }; jsonPath("$.name") { value("보호자") }
        }
        val user = userId(id)
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM parent_credential WHERE user_id=? AND password_hash LIKE 'pbkdf2-sha256$%'", Int::class.java, user))
        assertNull(jdbc.queryForObject("SELECT password_hash FROM user_account WHERE id=?", String::class.java, user))
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='PARENT_PASSWORD_SIGNUP'", Int::class.java, user))
    }

    @Test fun `signup validates input, refuses taken IDs case-insensitively and needs browser headers`() {
        val id = newId()
        signup(id, browser = false).andExpect { status { isForbidden() } }
        signup("ab").andExpect { status { isBadRequest() }; jsonPath("$.code") { value("VALIDATION_FAILED") } }
        signup("user@example.com").andExpect { status { isBadRequest() } }
        signup(id, password = "short").andExpect { status { isBadRequest() } }
        signup(id, password = "x".repeat(129)).andExpect { status { isBadRequest() } }
        signup(id, name = " ").andExpect { status { isBadRequest() } }
        signup(id).andExpect { status { isOk() } }
        signup(id.uppercase()).andExpect { status { isConflict() }; jsonPath("$.code") { value("LOGIN_ID_TAKEN") } }
    }

    @Test fun `signups per IP are limited, duplicate IDs do not count`() {
        val ip = newIp()
        val first = newId()
        signup(first, ip = ip).andExpect { status { isOk() } }
        repeat(3) { signup(first, ip = ip).andExpect { status { isConflict() } } }
        repeat(2) { signup(newId(), ip = ip).andExpect { status { isOk() } } }
        signup(newId(), ip = ip).andExpect { status { isTooManyRequests() }; jsonPath("$.code") { value("SIGNUP_RATE_LIMITED") } }
        signup(newId(), ip = newIp()).andExpect { status { isOk() } }
    }

    @Test fun `login uses the shared 5 failure 15 minute lock and replaces the previous session`() {
        val id = newId(); val first = registered(id); val user = userId(id)
        login(id, "wrong-password").andExpect { status { isUnauthorized() }; jsonPath("$.code") { value("INVALID_CREDENTIALS") } }
        login("nobody${UUID.randomUUID().toString().take(8)}").andExpect { status { isUnauthorized() }; jsonPath("$.code") { value("INVALID_CREDENTIALS") } }
        login(id.uppercase()).andExpect { status { isOk() }; jsonPath("$.role") { value("PARENT") } }
        assertEquals(0, failedCount(user))
        val second = auth.parentLogin(id, PASSWORD, first.refreshToken)
        assertFailsWith<BusinessException> { auth.authenticate(first.accessToken) }
        assertEquals("PARENT", auth.authenticate(second.accessToken).session.role)
        repeat(4) { assertEquals("INVALID_CREDENTIALS", code { auth.parentLogin(id, "wrong-password", null) }) }
        assertEquals("LOGIN_LOCKED", code { auth.parentLogin(id, "wrong-password", null) })
        login(id).andExpect { status { isLocked() }; jsonPath("$.code") { value("LOGIN_LOCKED") } }
        jdbc.update("UPDATE parent_credential SET locked_until=? WHERE user_id=?", OffsetDateTime.now().minusSeconds(1), user)
        auth.parentLogin(id, PASSWORD, null)
        // registered(), the HTTP upper-case login, the session replacement and the post-lock login.
        assertEquals(4, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='PARENT_PASSWORD_LOGIN'", Int::class.java, user))
    }

    @Test fun `Google parents and admins cannot use parent password login`() {
        val subject = UUID.randomUUID().toString()
        val google = auth.login(GoogleProfile(subject, "$subject@example.test", "구글"), null)
        // Google login IDs are emails, which the parent ID rule never accepts.
        assertEquals("INVALID_CREDENTIALS", code { auth.parentLogin("$subject@example.test", PASSWORD, null) })
        assertEquals("REAUTH_METHOD_MISMATCH", code { reauth.withPassword(google.identity, ReauthPurpose.WITHDRAWAL, null, null, PASSWORD) })
        val adminId = newId(); val admin = UUID.randomUUID()
        jdbc.update("INSERT INTO user_account(id,role,login_id,password_hash,display_name,status,is_demo,created_at,updated_at) VALUES(?,'ADMIN',?,NULL,'운영','ACTIVE',false,now(),now())", admin, adminId)
        jdbc.update("INSERT INTO parent_credential(user_id,password_hash,failed_count,locked_until,created_at,updated_at) VALUES(?,?,0,NULL,now(),now())", admin, hasher.hash(PASSWORD))
        assertEquals("INVALID_CREDENTIALS", code { auth.parentLogin(adminId, PASSWORD, null) })
    }

    @Test fun `password re-confirmation issues a grant that sets the guardian password`() {
        val p = registered(); val user = p.identity.account.id
        agreeRequired(user)
        val identity = auth.authenticate(p.accessToken)
        mvc.post("/api/v1/me/reauth/password") {
            header("Origin", ORIGIN); header("X-Requested-With", "XMLHttpRequest"); header("Authorization", "Bearer ${p.accessToken}")
            contentType = MediaType.APPLICATION_JSON; content = """{"purpose":"GUARDIAN_PASSWORD","password":"wrong-password"}"""
        }.andExpect { status { isForbidden() }; jsonPath("$.code") { value("REAUTH_PASSWORD_INVALID") } }
        assertEquals(1, failedCount(user))
        assertEquals("VALIDATION_FAILED", code { reauth.withPassword(identity, ReauthPurpose.PIN_CHANGE, null, null, PASSWORD) })
        val body = mvc.post("/api/v1/me/reauth/password") {
            header("Origin", ORIGIN); header("X-Requested-With", "XMLHttpRequest"); header("Authorization", "Bearer ${p.accessToken}")
            contentType = MediaType.APPLICATION_JSON; content = """{"purpose":"GUARDIAN_PASSWORD","password":"$PASSWORD"}"""
        }.andExpect { status { isOk() }; jsonPath("$.reauthToken") { isString() }; jsonPath("$.expiresAt") { isString() } }
            .andReturn().response.contentAsString
        assertEquals(0, failedCount(user))
        val token = json.readTree(body)["reauthToken"].asText()
        val set = { t: String -> mvc.put("/api/v1/me/guardian-password") {
            header("Authorization", "Bearer ${p.accessToken}"); header("X-Reauth-Token", t)
            contentType = MediaType.APPLICATION_JSON; content = """{"password":"2580"}"""
        } }
        set(token).andExpect { status { isOk() }; jsonPath("$.set") { value(true) } }
        // The grant is one-time, exactly as for Google re-confirmation.
        set(token).andExpect { status { isForbidden() }; jsonPath("$.code") { value("REAUTH_REQUIRED") } }
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='PASSWORD_REAUTHENTICATED'", Int::class.java, user))
    }

    @Test fun `re-confirmation failures share the login lock`() {
        val id = newId(); val p = registered(id)
        repeat(4) { assertEquals("REAUTH_PASSWORD_INVALID", code { reauth.withPassword(p.identity, ReauthPurpose.WITHDRAWAL, null, null, "wrong-password") }) }
        assertEquals("LOGIN_LOCKED", code { reauth.withPassword(p.identity, ReauthPurpose.WITHDRAWAL, null, null, "wrong-password") })
        assertEquals("LOGIN_LOCKED", code { auth.parentLogin(id, PASSWORD, null) })
    }

    @Test fun `completed withdrawal deletes the credential and releases the ID`() {
        val id = newId(); val p = registered(id); val user = p.identity.account.id
        val token = reauth.withPassword(p.identity, ReauthPurpose.WITHDRAWAL, null, null, PASSWORD).reauthToken
        // No children, so the request completes the withdrawal at once.
        withdrawals.request(auth.authenticate(p.accessToken), token)
        assertEquals("WITHDRAWN", jdbc.queryForObject("SELECT status FROM user_account WHERE id=?", String::class.java, user))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM parent_credential WHERE user_id=?", Int::class.java, user))
        signup(id).andExpect { status { isOk() } }
    }

    private companion object {
        const val ORIGIN = "http://localhost:5173"
        const val PASSWORD = "parent-pass-415"
    }
}
