package com.sagomungchi.core.account

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.parent
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.HttpMethod
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
import java.util.UUID
import kotlin.test.*

/** #1035 첫 사용 안내 완료 기록: 미완료 null·기록·재기록 시 처음 시각 유지·역할별 경로 403. */
@AutoConfigureMockMvc
@TestPropertySource(properties=["spring.rabbitmq.listener.simple.auto-startup=false"])
class OnboardingIntegrationTest: IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    private lateinit var user: UUID
    private lateinit var student: UUID
    private lateinit var parentToken: String
    private lateinit var studentToken: String
    private lateinit var siblingToken: String

    @BeforeEach fun prepare() {
        user = parent(jdbc); student = child(jdbc, user); val sibling = child(jdbc, user)
        parentToken = tokens.access(session(jdbc, user, "PARENT"))
        studentToken = tokens.access(session(jdbc, user, "STUDENT", student))
        siblingToken = tokens.access(session(jdbc, user, "STUDENT", sibling))
    }

    private fun call(method: String, path: String, token: String, expected: Int = 200): JsonNode {
        val response = mvc.perform(request(HttpMethod.valueOf(method), path).header("Authorization", "Bearer $token")).andReturn().response
        assertEquals(expected, response.status, response.contentAsString)
        val body = json.readTree(response.contentAsString)
        if (expected == 200) {
            assertEquals("no-store", response.getHeader("Cache-Control"))
            assertEquals(setOf("completedAt"), body.fieldNames().asSequence().toSet())
        }
        return body
    }

    private fun recordsOnceAndKeepsFirstTime(path: String, token: String) {
        assertTrue(call("GET", path, token)["completedAt"].isNull)
        val first = call("PUT", path, token)["completedAt"]
        assertFalse(first.isNull)
        assertEquals(first, call("GET", path, token)["completedAt"])
        assertEquals(first, call("PUT", path, token)["completedAt"])
        assertEquals(first, call("GET", path, token)["completedAt"])
    }

    @Test fun `parent record is null until completed and keeps the first time`() {
        recordsOnceAndKeepsFirstTime("/api/v1/me/onboarding", parentToken)
        // 학부모 기록은 같은 계정 아래 학생 기록과 따로다.
        assertTrue(call("GET", "/api/v1/students/me/onboarding", studentToken)["completedAt"].isNull)
    }

    @Test fun `student record is per student and keeps the first time`() {
        recordsOnceAndKeepsFirstTime("/api/v1/students/me/onboarding", studentToken)
        assertTrue(call("GET", "/api/v1/students/me/onboarding", siblingToken)["completedAt"].isNull)
        assertTrue(call("GET", "/api/v1/me/onboarding", parentToken)["completedAt"].isNull)
    }

    @Test fun `each path rejects the other roles`() {
        val admin = tokens.access(session(jdbc, account(jdbc), "ADMIN"))
        for (method in listOf("GET", "PUT")) {
            for (token in listOf(studentToken, admin))
                assertEquals("FORBIDDEN", call(method, "/api/v1/me/onboarding", token, 403)["code"].asText())
            for (token in listOf(parentToken, admin))
                assertEquals("FORBIDDEN", call(method, "/api/v1/students/me/onboarding", token, 403)["code"].asText())
        }
        assertNull(jdbc.queryForObject("SELECT onboarding_completed_at FROM user_account WHERE id=?", java.time.OffsetDateTime::class.java, user))
        assertNull(jdbc.queryForObject("SELECT onboarding_completed_at FROM student WHERE id=?", java.time.OffsetDateTime::class.java, student))
    }

    @Test fun `parent without required consents is not allowed before READY`() {
        val pending = tokens.access(session(jdbc, account(jdbc, "PARENT", null), "PARENT"))
        for (method in listOf("GET", "PUT"))
            assertEquals("CONSENT_REQUIRED", call(method, "/api/v1/me/onboarding", pending, 403)["code"].asText())
    }
}
