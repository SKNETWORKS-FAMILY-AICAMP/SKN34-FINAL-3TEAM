package com.sagomungchi.core.account

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.post
import java.util.UUID
import kotlin.test.assertEquals

/** #415·#816: 가입 횟수를 셀 Redis에 닿지 않으면 한도 초과(429)가 아니라 503 `SIGNUP_UNAVAILABLE`, 계정은 만들지 않는다 */
@AutoConfigureMockMvc
@TestPropertySource(properties = ["app.auth.cookie-secure=false", "app.auth.web-origin=$ORIGIN",
    "spring.data.redis.host=127.0.0.1", "spring.data.redis.port=1", "spring.data.redis.connect-timeout=500ms"])
class SignupLimitOutageTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper

    @Test fun `Redis outage answers 503 SIGNUP_UNAVAILABLE and creates no account`() {
        val id = "p" + UUID.randomUUID().toString().replace("-", "").take(20)
        mvc.post("/api/v1/auth/parent/signup") {
            header("Origin", ORIGIN); header("X-Requested-With", "XMLHttpRequest")
            contentType = MediaType.APPLICATION_JSON
            content = json.writeValueAsString(mapOf("loginId" to id, "password" to "parent-pass-816", "name" to "보호자"))
        }.andExpect { status { isServiceUnavailable() }; jsonPath("$.code") { value("SIGNUP_UNAVAILABLE") } }
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM user_account WHERE login_id=?", Int::class.java, id))
    }
}

private const val ORIGIN = "http://localhost:5173"
