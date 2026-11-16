package com.sagomungchi.core._common.security

import com.sagomungchi.core._common.config.AppProperties
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.context.annotation.Import
import org.springframework.test.context.TestPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RestController
import java.net.URI

@WebMvcTest(controllers = [InternalAuthFilterTest.ProbeController::class])
@Import(InternalAuthFilterTest.ProbeController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(
    properties = [
        "app.internal.token=test-token",
        "app.internal.callers.learning=test-token",
        "app.internal.callers.report-worker=worker-token",
        "app.internal.callers.ai=",
        "app.internal.connect-timeout=1s",
        "app.internal.read-timeout=1s",
    ],
)
class InternalAuthFilterTest(@Autowired private val mockMvc: MockMvc) {
    @RestController
    class ProbeController {
        @GetMapping("/internal/students/{studentId}/profile")
        fun probe(@PathVariable studentId: String): Map<String, String?> {
            val context = UserContextHolder.current()
            context.requireStudent(studentId)
            return mapOf("userId" to context.userId)
        }
    }

    @Test
    fun `토큰 없으면 401 Problem Details`() {
        mockMvc.get("/internal/students/s1/profile").andExpect {
            status { isUnauthorized() }
            jsonPath("$.code") { value("UNAUTHENTICATED") }
            jsonPath("$.traceId") { exists() }
        }
    }

    @Test
    fun `매개변수·퍼센트 인코딩 경로도 토큰 없으면 401`() {
        listOf("/internal;x/students/s1/profile", "/%69nternal/students/s1/profile").forEach { path ->
            mockMvc.perform(MockMvcRequestBuilders.get(URI.create(path)))
                .andExpect(status().isUnauthorized)
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"))
        }
    }

    @Test
    fun `허용 범위 학생이면 컨텍스트 전달`() {
        mockMvc.get("/internal/students/s1/profile") {
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
        mockMvc.get("/internal/students/s9/profile") {
            header("X-Internal-Token", "test-token")
            header("X-Student-Scope", "s1")
        }.andExpect {
            status { isForbidden() }
            jsonPath("$.code") { value("FORBIDDEN") }
        }
    }

    @Test
    fun `없는 경로는 404 Problem Details와 traceparent의 traceId`() {
        mockMvc.get("/internal/payment-usage/unknown") {
            header("X-Internal-Token", "test-token")
            header("traceparent", "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        }.andExpect {
            status { isNotFound() }
            jsonPath("$.code") { value("NOT_FOUND") }
            jsonPath("$.traceId") { value("4bf92f3577b34da6a3ce929d0e0e4736") }
        }
    }

    @Test
    fun `빈 토큰은 빈 호출자 설정과 맞지 않아 401`() {
        mockMvc.get("/internal/students/s1/profile") {
            header("X-Internal-Token", "")
        }.andExpect {
            status { isUnauthorized() }
            jsonPath("$.code") { value("UNAUTHENTICATED") }
        }
    }

    @Test
    fun `맞는 호출자라도 허용 경로 밖이면 403`() {
        mockMvc.get("/internal/payment-usage/reservations") {
            header("X-Internal-Token", "worker-token")
        }.andExpect {
            status { isForbidden() }
            jsonPath("$.code") { value("FORBIDDEN") }
        }
    }

    @Test
    fun `허용 패턴에 점 세그먼트를 끼운 경로는 403`() {
        mockMvc.perform(
            MockMvcRequestBuilders.get(URI.create("/internal/students/%2E%2E/profile"))
                .header("X-Internal-Token", "worker-token"),
        ).andExpect(status().isForbidden)
            .andExpect(jsonPath("$.code").value("FORBIDDEN"))
    }

    @Test
    fun `호출자 허용 경로면 통과`() {
        mockMvc.get("/internal/students/s1/profile") {
            header("X-Internal-Token", "worker-token")
            header("X-Student-Scope", "s1")
        }.andExpect { status { isOk() } }
    }
}
