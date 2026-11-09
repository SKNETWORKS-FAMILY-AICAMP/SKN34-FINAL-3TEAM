package com.sagomungchi.core.account

import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.controller.AuthCookies
import com.sagomungchi.core.account.service.AuthService
import com.sagomungchi.core.guardianship.service.PinHasher
import jakarta.servlet.http.Cookie
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.post
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.*

/** #369 admin ID/password login backed by admin_credential rows (created by scripts/admin_account_sql.py). */
@AutoConfigureMockMvc
@TestPropertySource(properties = ["app.auth.cookie-secure=false", "app.auth.web-origin=http://localhost:5173",
    "spring.rabbitmq.listener.simple.auto-startup=false"])
class AdminPasswordLoginIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var hasher: PinHasher
    private lateinit var loginId: String
    private lateinit var admin: UUID

    @BeforeEach fun prepare() {
        loginId = "ops-${UUID.randomUUID()}"
        admin = account(loginId, "ADMIN")
        jdbc.update("INSERT INTO admin_permission(user_id,permission,granted_by,granted_at) VALUES(?,'CONTENT',?,?)", admin, admin, OffsetDateTime.now())
        credential(admin, PASSWORD)
    }

    private fun account(login: String, role: String, status: String = "ACTIVE"): UUID = UUID.randomUUID().also {
        jdbc.update("INSERT INTO user_account(id,role,login_id,password_hash,display_name,status,is_demo,created_at,updated_at) VALUES(?,?,?,NULL,'운영자',?,false,?,?)",
            it, role, login, status, OffsetDateTime.now(), OffsetDateTime.now())
    }
    private fun credential(user: UUID, password: String) = jdbc.update(
        "INSERT INTO admin_credential(user_id,password_hash,failed_count,locked_until,created_at,updated_at) VALUES(?,?,0,NULL,?,?)",
        user, hasher.hash(password), OffsetDateTime.now(), OffsetDateTime.now())
    private fun failedCount() = jdbc.queryForObject("SELECT failed_count FROM admin_credential WHERE user_id=?", Int::class.java, admin)
    private fun code(block: () -> Unit) = assertFailsWith<BusinessException> { block() }.code

    @Test fun `HTTP login sets refresh cookie and starts at admin home with permissions`() {
        val response = mvc.post("/api/v1/auth/admin/login") {
            header("Origin", "http://localhost:5173"); header("X-Requested-With", "XMLHttpRequest")
            contentType = MediaType.APPLICATION_JSON; content = """{"loginId":"$loginId","password":"$PASSWORD"}"""
        }.andExpect {
            status { isOk() }; jsonPath("$.role") { value("ADMIN") }; jsonPath("$.startPath") { value("/admin/home") }
            jsonPath("$.accessToken") { isString() }
        }.andReturn().response
        assertTrue(response.getHeaders("Set-Cookie").any { it.startsWith("${AuthCookies.REFRESH}=") && it.contains("HttpOnly") && it.contains("SameSite=Strict") })
        val issued = auth.adminLogin(loginId, PASSWORD, null)
        assertEquals(setOf("CONTENT"), auth.authenticate(issued.accessToken).permissions)
        assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='ADMIN_PASSWORD_LOGIN'", Int::class.java, admin))
    }

    @Test fun `login without browser origin headers is refused before the body is read`() {
        mvc.post("/api/v1/auth/admin/login") {
            contentType = MediaType.APPLICATION_JSON; content = """{"loginId":"$loginId","password":"$PASSWORD"}"""
        }.andExpect { status { isForbidden() } }
        mvc.post("/api/v1/auth/admin/login") {
            header("Origin", "http://localhost:5173"); header("X-Requested-With", "XMLHttpRequest")
            cookie(Cookie(AuthCookies.REFRESH, "unknown")); contentType = MediaType.APPLICATION_JSON
            content = """{"loginId":"$loginId","password":"wrong-password"}"""
        }.andExpect { status { isUnauthorized() }; jsonPath("$.code") { value("INVALID_CREDENTIALS") } }
    }

    @Test fun `unknown ID wrong password non admin and withdrawn accounts give the same 401`() {
        assertEquals("INVALID_CREDENTIALS", code { auth.adminLogin("nobody-${UUID.randomUUID()}", PASSWORD, null) })
        assertEquals("INVALID_CREDENTIALS", code { auth.adminLogin(loginId, "wrong-password", null) })
        assertEquals("INVALID_CREDENTIALS", code { auth.adminLogin(loginId, "x".repeat(129), null) })
        assertEquals("INVALID_CREDENTIALS", code { auth.adminLogin("", PASSWORD, null) })
        val parentId = "parent-${UUID.randomUUID()}"
        credential(account(parentId, "PARENT"), PASSWORD)
        assertEquals("INVALID_CREDENTIALS", code { auth.adminLogin(parentId, PASSWORD, null) })
        val withdrawnId = "withdrawn-${UUID.randomUUID()}"
        credential(account(withdrawnId, "ADMIN", "WITHDRAWN"), PASSWORD)
        assertEquals("INVALID_CREDENTIALS", code { auth.adminLogin(withdrawnId, PASSWORD, null) })
    }

    @Test fun `fifth failure locks for fifteen minutes and success resets the counter`() {
        repeat(2) { code { auth.adminLogin(loginId, "wrong-password", null) } }
        assertEquals(2, failedCount())
        auth.adminLogin(loginId, PASSWORD, null)
        assertEquals(0, failedCount())
        repeat(4) { assertEquals("INVALID_CREDENTIALS", code { auth.adminLogin(loginId, "wrong-password", null) }) }
        assertEquals("ADMIN_LOGIN_LOCKED", code { auth.adminLogin(loginId, "wrong-password", null) })
        assertEquals("ADMIN_LOGIN_LOCKED", code { auth.adminLogin(loginId, PASSWORD, null) })
        val until = requireNotNull(jdbc.queryForObject("SELECT locked_until FROM admin_credential WHERE user_id=?", OffsetDateTime::class.java, admin))
        assertTrue(until.isAfter(OffsetDateTime.now().plusMinutes(14)) && until.isBefore(OffsetDateTime.now().plusMinutes(16)))
        jdbc.update("UPDATE admin_credential SET locked_until=? WHERE user_id=?", OffsetDateTime.now().minusSeconds(1), admin)
        auth.adminLogin(loginId, PASSWORD, null)
        assertNull(jdbc.queryForObject("SELECT locked_until FROM admin_credential WHERE user_id=?", OffsetDateTime::class.java, admin))
    }

    @Test fun `new login revokes the previous refresh session`() {
        val first = auth.adminLogin(loginId, PASSWORD, null)
        val second = auth.adminLogin(loginId, PASSWORD, first.refreshToken)
        assertFailsWith<BusinessException> { auth.authenticate(first.accessToken) }
        assertEquals("ADMIN", auth.authenticate(second.accessToken).session.role)
    }

    @Test fun `script hash format verifies in core`() {
        // Produced by scripts/admin_account_sql.py's hash function with a fixed salt (bytes 0..15).
        assertTrue(hasher.matches("admin-password-369", "pbkdf2-sha256\$600000\$AAECAwQFBgcICQoLDA0ODw==\$RZntp5pQFkl/FFYNwcUI9CU8+AagdjPdN175RnNu7Ek="))
    }

    private companion object { const val PASSWORD = "correct-horse-369" }
}
