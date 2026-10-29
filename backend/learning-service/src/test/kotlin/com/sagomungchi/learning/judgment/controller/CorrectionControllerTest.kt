package com.sagomungchi.learning.judgment.controller

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning.judgment.domain.CorrectionCommand
import com.sagomungchi.learning.judgment.domain.JudgmentCorrection
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.judgment.service.JudgmentService
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.http.MediaType
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.json.JsonCompareMode
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.post
import java.time.Instant
import java.util.UUID

@WebMvcTest(CorrectionController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(
    properties = [
        "app.internal.token=test-token",
        "app.internal.connect-timeout=1s",
        "app.internal.read-timeout=1s",
    ],
)
class CorrectionControllerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var service: JudgmentService

    private val student = UUID.randomUUID()
    private val admin = UUID.randomUUID()
    private val judgmentId = UUID.randomUUID()
    private val reportId = UUID.randomUUID()
    private val key = UUID.randomUUID()
    private val body = """{"reportId":"$reportId","reason":"규칙 판정 오류","corrected":"CORRECT"}"""

    private fun MockHttpServletRequestDsl.asAdmin(
        role: String = "ADMIN",
        scope: String? = student.toString(),
        userId: String? = admin.toString(),
        idempotencyKey: String? = key.toString(),
        content: String = body,
        token: String = "test-token",
    ) {
        header("X-Internal-Token", token)
        header("X-User-Role", role)
        scope?.let { header("X-Student-Scope", it) }
        userId?.let { header("X-User-Id", it) }
        idempotencyKey?.let { header("Idempotency-Key", it) }
        contentType = MediaType.APPLICATION_JSON
        this.content = content
    }

    @Test
    fun `정정 결과와 영향 확인 상태 (core #46 계약 CorrectionResult)`() {
        val correctionId = UUID.randomUUID()
        val createdAt = Instant.parse("2026-10-29T01:02:03.456789Z")
        given(service.correct(judgmentId, CorrectionCommand(reportId, "규칙 판정 오류", JudgmentResult.CORRECT, admin), key)).willReturn(
            JudgmentCorrection(correctionId, judgmentId, reportId, "규칙 판정 오류", JudgmentResult.HELD, JudgmentResult.CORRECT, admin, key, createdAt),
        )

        mockMvc.post("/internal/judgments/$judgmentId/corrections") { asAdmin() }.andExpect {
            status { isOk() }
            content {
                json(
                    """{"correctionId":"$correctionId","previousResult":"HELD","corrected":"CORRECT","createdAt":"2026-10-29T01:02:03.456789Z",
                       "impact":{"conversation":"UNKNOWN","aggregation":"NOT_APPLIED","report":"UNKNOWN"}}""",
                    JsonCompareMode.STRICT,
                )
            }
        }
    }

    @Test
    fun `관리자가 아니거나 범위가 학생 1명이 아니면 403`() {
        listOf(
            mapOf("role" to "STUDENT"),
            mapOf("role" to "SYSTEM"),
            mapOf("scope" to null),
            mapOf("scope" to "$student,${UUID.randomUUID()}"),
        ).forEach { case ->
            mockMvc.post("/internal/judgments/$judgmentId/corrections") {
                asAdmin(role = case["role"] ?: "ADMIN", scope = if ("scope" in case) case["scope"] else student.toString())
            }.andExpect {
                status { isForbidden() }
                jsonPath("$.code") { value("FORBIDDEN") }
            }
        }
        verifyNoInteractions(service)
    }

    @Test
    fun `관리자 ID·멱등 키가 없거나 UUID가 아니면 400`() {
        listOf<MockHttpServletRequestDsl.() -> Unit>(
            { asAdmin(userId = null) },
            { asAdmin(userId = "admin") },
            { asAdmin(idempotencyKey = null) },
            { asAdmin(idempotencyKey = "key-1") },
        ).forEach { request ->
            mockMvc.post("/internal/judgments/$judgmentId/corrections", dsl = request).andExpect {
                status { isBadRequest() }
                jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
        verifyNoInteractions(service)
    }

    @Test
    fun `사유가 비었거나 정정 결과·신고 ID 형식이 틀리면 400`() {
        listOf(
            """{"reportId":"$reportId","reason":" ","corrected":"CORRECT"}""",
            """{"reportId":"$reportId","corrected":"CORRECT"}""",
            """{"reportId":"$reportId","reason":"사유","corrected":"WRONG"}""",
            """{"reportId":"report-1","reason":"사유","corrected":"CORRECT"}""",
        ).forEach { invalid ->
            mockMvc.post("/internal/judgments/$judgmentId/corrections") { asAdmin(content = invalid) }.andExpect {
                status { isBadRequest() }
                jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
        verifyNoInteractions(service)
    }

    @Test
    fun `내부 토큰이 틀리면 401`() {
        mockMvc.post("/internal/judgments/$judgmentId/corrections") { asAdmin(token = "wrong") }.andExpect {
            status { isUnauthorized() }
        }
        verifyNoInteractions(service)
    }
}
