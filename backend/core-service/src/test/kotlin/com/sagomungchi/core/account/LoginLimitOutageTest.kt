package com.sagomungchi.core.account

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.test.context.TestPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.post

/** #1054: 로그인 IP 한도를 셀 Redis에 닿지 않으면 한도 초과(429)가 아니라 503 `LOGIN_UNAVAILABLE`, 관리자·학부모 모두 비밀번호 검사 전에 거절한다 */
@AutoConfigureMockMvc
@TestPropertySource(properties = ["app.auth.cookie-secure=false", "app.auth.web-origin=$ORIGIN",
    "spring.data.redis.host=127.0.0.1", "spring.data.redis.port=1", "spring.data.redis.connect-timeout=500ms"])
class LoginLimitOutageTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var json: ObjectMapper

    @Test fun `Redis outage answers 503 LOGIN_UNAVAILABLE for parent and admin password login`() {
        listOf("parent", "admin").forEach { realm ->
            mvc.post("/api/v1/auth/$realm/login") {
                header("Origin", ORIGIN); header("X-Requested-With", "XMLHttpRequest")
                contentType = MediaType.APPLICATION_JSON
                content = json.writeValueAsString(mapOf("loginId" to "outage1054", "password" to "login-pass-1054"))
            }.andExpect { status { isServiceUnavailable() }; jsonPath("$.code") { value("LOGIN_UNAVAILABLE") } }
        }
    }
}

private const val ORIGIN = "http://localhost:5173"
