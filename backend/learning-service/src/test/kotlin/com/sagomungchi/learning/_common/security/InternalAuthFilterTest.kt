package com.sagomungchi.learning._common.security

import com.sagomungchi.learning._common.config.AppProperties
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.context.annotation.Import
import org.springframework.test.context.TestPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RestController

@WebMvcTest
@Import(InternalAuthFilterTest.ProbeController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(
    properties = [
        "app.internal.token=test-token",
        "app.internal.connect-timeout=1s",
        "app.internal.read-timeout=1s",
    ],
)
class InternalAuthFilterTest(@Autowired private val mockMvc: MockMvc) {
    @RestController
    class ProbeController {
        @GetMapping("/internal/probe/students/{studentId}")
        fun probe(@PathVariable studentId: String): Map<String, String?> {
            val context = UserContextHolder.current()
            context.requireStudent(studentId)
            return mapOf("userId" to context.userId)
        }
    }

    @Test
    fun `토큰 없으면 401 Problem Details`() {
        mockMvc.get("/internal/probe/students/s1").andExpect {
            status { isUnauthorized() }
            jsonPath("$.code") { value("UNAUTHENTICATED") }
            jsonPath("$.traceId") { exists() }
        }
    }

    @Test
    fun `허용 범위 학생이면 컨텍스트 전달`() {
        mockMvc.get("/internal/probe/students/s1") {
            header("X-Internal-Token", "test-token")
            header("X-User-Id", "p1")
            header("X-Student-Scope", "s1,s2")
        }.andExpect {
            status { isOk() }
            jsonPath("$.userId") { value("p1") }
        }
    }

    @Test
    fun `범위 밖 학생이면 403`() {
        mockMvc.get("/internal/probe/students/s9") {
            header("X-Internal-Token", "test-token")
            header("X-Student-Scope", "s1")
        }.andExpect {
            status { isForbidden() }
            jsonPath("$.code") { value("FORBIDDEN") }
        }
    }

    @Test
    fun `없는 경로는 404 Problem Details와 traceparent의 traceId`() {
        mockMvc.get("/internal/unknown") {
            header("X-Internal-Token", "test-token")
            header("traceparent", "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        }.andExpect {
            status { isNotFound() }
            jsonPath("$.code") { value("NOT_FOUND") }
            jsonPath("$.traceId") { value("4bf92f3577b34da6a3ce929d0e0e4736") }
        }
    }
}
