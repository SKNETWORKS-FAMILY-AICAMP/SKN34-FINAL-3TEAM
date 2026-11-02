package com.sagomungchi.learning.judgment.controller

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning.judgment.domain.FeedbackResult
import com.sagomungchi.learning.judgment.domain.ProcessStatus
import com.sagomungchi.learning.judgment.domain.SupportAnswer
import com.sagomungchi.learning.judgment.domain.SupportOriginal
import com.sagomungchi.learning.judgment.domain.SupportTarget
import com.sagomungchi.learning.judgment.domain.SupportTargetType
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.judgment.service.JudgmentService
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.json.JsonCompareMode
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import java.util.UUID

/** 신고 지원 조회 내부 API (api-spec 4.1, #146): core #46이 보내는 역할·범위·X-User-Id 검사와 응답 모양 */
@WebMvcTest(SupportController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(properties = ["app.internal.token=test-token", "app.internal.connect-timeout=1s", "app.internal.read-timeout=1s"])
class SupportControllerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var service: JudgmentService

    private val student = UUID.randomUUID()
    private val attemptId = UUID.randomUUID()
    private val judgmentId = UUID.randomUUID()

    private fun MockHttpServletRequestDsl.caller(role: String, scope: String? = student.toString(), userId: String? = UUID.randomUUID().toString()) {
        header("X-Internal-Token", "test-token")
        header("X-User-Role", role)
        scope?.let { header("X-Student-Scope", it) }
        userId?.let { header("X-User-Id", it) }
    }

    @Test
    fun `대상 확인은 학생·보호자·관리자, 없는 칸은 응답에서 빠짐`() {
        given(service.supportTarget(SupportTargetType.JUDGMENT, judgmentId))
            .willReturn(SupportTarget(student, attemptId, judgmentId, JudgmentResult.PARTIAL))
        given(service.supportTarget(SupportTargetType.ATTEMPT, attemptId)).willReturn(SupportTarget(student, attemptId, null, null))

        listOf("STUDENT" to student.toString(), "PARENT" to "${UUID.randomUUID()},$student", "ADMIN" to student.toString()).forEach { (role, scope) ->
            mockMvc.get("/internal/support/targets/JUDGMENT/$judgmentId") { caller(role, scope) }.andExpect {
                status { isOk() }
                content {
                    json("""{"studentId":"$student","attemptId":"$attemptId","judgmentId":"$judgmentId","previousResult":"PARTIAL"}""", JsonCompareMode.STRICT)
                }
            }
        }
        mockMvc.get("/internal/support/targets/ATTEMPT/$attemptId") { caller("STUDENT") }.andExpect {
            status { isOk() }
            content { json("""{"studentId":"$student","attemptId":"$attemptId"}""", JsonCompareMode.STRICT) }
        }
    }

    @Test
    fun `대상 확인 역할이 아니거나 관리자 범위가 1명이 아니면 403, X-User-Id가 없거나 UUID가 아니면 400`() {
        listOf("SYSTEM" to student.toString(), "ADMIN" to "$student,${UUID.randomUUID()}", "ADMIN" to null).forEach { (role, scope) ->
            mockMvc.get("/internal/support/targets/JUDGMENT/$judgmentId") { caller(role, scope) }.andExpect {
                status { isForbidden() }
                jsonPath("$.code") { value("FORBIDDEN") }
            }
        }
        listOf(null, "parent").forEach { userId ->
            mockMvc.get("/internal/support/targets/JUDGMENT/$judgmentId") { caller("PARENT", userId = userId) }.andExpect {
                status { isBadRequest() }
                jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
        mockMvc.get("/internal/support/targets/ANALYSIS/$judgmentId") { caller("PARENT") }.andExpect { status { isBadRequest() } }
        verifyNoInteractions(service)
    }

    @Test
    fun `원문은 관리자·학생 1명만, 응답은 답변 네 칸`() {
        val answerId = UUID.randomUUID()
        given(service.supportOriginal(attemptId)).willReturn(
            SupportOriginal(student, attemptId, listOf(SupportAnswer(answerId, 1, "첫 답", FeedbackResult.inProgress(ProcessStatus.PENDING)))),
        )

        mockMvc.get("/internal/support/attempts/$attemptId") { caller("ADMIN") }.andExpect {
            status { isOk() }
            content {
                json(
                    """{"studentId":"$student","attemptId":"$attemptId","answers":[{"answerId":"$answerId","version":1,"text":"첫 답",
                       "feedback":{"status":"PENDING","judgment":null,"followup":null,"nextActions":[],"versions":null}}]}""",
                    JsonCompareMode.STRICT,
                )
            }
        }
    }

    @Test
    fun `원문은 관리자가 아니거나 범위가 1명이 아니면 403, X-User-Id 오류 400`() {
        listOf("PARENT" to student.toString(), "STUDENT" to student.toString(), "ADMIN" to "$student,${UUID.randomUUID()}", "ADMIN" to null)
            .forEach { (role, scope) ->
                mockMvc.get("/internal/support/attempts/$attemptId") { caller(role, scope) }.andExpect {
                    status { isForbidden() }
                    jsonPath("$.code") { value("FORBIDDEN") }
                }
            }
        mockMvc.get("/internal/support/attempts/$attemptId") { caller("ADMIN", userId = null) }.andExpect {
            status { isBadRequest() }
            jsonPath("$.code") { value("VALIDATION_FAILED") }
        }
        verifyNoInteractions(service)
    }
}
