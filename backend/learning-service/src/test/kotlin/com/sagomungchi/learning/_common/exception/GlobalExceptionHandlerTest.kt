package com.sagomungchi.learning._common.exception

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning.attempt.controller.AttemptController
import com.sagomungchi.learning.attempt.service.AttemptService
import org.junit.jupiter.api.Test
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.http.MediaType
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.delete
import org.springframework.test.web.servlet.put
import java.util.UUID

/**
 * Spring MVC 기본 예외의 Problem Details 모양 (api-spec 1.3, 이슈 #137): 405·415도 problem+json에 code·traceId.
 * 실제 학생 경로(AttemptController)로 보냄
 */
@WebMvcTest(AttemptController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(properties = ["app.internal.token=test-token", "app.internal.connect-timeout=1s", "app.internal.read-timeout=1s"])
class GlobalExceptionHandlerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var service: AttemptService

    private val student = UUID.randomUUID()
    private val attemptId = UUID.randomUUID()
    private val traceId = "4bf92f3577b34da6a3ce929d0e0e4736"

    private fun MockHttpServletRequestDsl.asStudent() {
        header("X-Internal-Token", "test-token")
        header("X-User-Role", "STUDENT")
        header("X-Student-Scope", student.toString())
        header("traceparent", "00-$traceId-00f067aa0ba902b7-01")
    }

    @Test
    fun `지원하지 않는 메서드는 405 METHOD_NOT_ALLOWED Problem Details`() {
        mockMvc.delete("/internal/attempts/$attemptId") { asStudent() }.andExpect {
            status { isMethodNotAllowed() }
            content { contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON) }
            header { exists("Allow") }
            jsonPath("$.status") { value(405) }
            jsonPath("$.code") { value("METHOD_NOT_ALLOWED") }
            jsonPath("$.type") { value("https://sagomungchi.dev/errors/method-not-allowed") }
            jsonPath("$.instance") { value("/internal/attempts/$attemptId") }
            jsonPath("$.traceId") { value(traceId) }
        }
        verifyNoInteractions(service)
    }

    @Test
    fun `JSON이 아닌 본문은 415 UNSUPPORTED_MEDIA_TYPE Problem Details`() {
        mockMvc.put("/internal/attempts/$attemptId/draft") {
            asStudent()
            header("If-Match", "\"0\"")
            contentType = MediaType.TEXT_PLAIN
            content = "초안"
        }.andExpect {
            status { isUnsupportedMediaType() }
            content { contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON) }
            jsonPath("$.status") { value(415) }
            jsonPath("$.code") { value("UNSUPPORTED_MEDIA_TYPE") }
            jsonPath("$.type") { value("https://sagomungchi.dev/errors/unsupported-media-type") }
            jsonPath("$.instance") { value("/internal/attempts/$attemptId/draft") }
            jsonPath("$.traceId") { value(traceId) }
        }
        verifyNoInteractions(service)
    }
}
