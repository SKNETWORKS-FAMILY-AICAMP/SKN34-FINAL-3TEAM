package com.sagomungchi.learning.answer.controller

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.answer.domain.Answer
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.domain.Assignment
import com.sagomungchi.learning.answer.domain.Essay
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.mission.domain.InputType
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.post
import java.time.Instant
import java.util.UUID

@WebMvcTest(AnswerController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(
    properties = [
        "app.internal.token=test-token",
        "app.internal.connect-timeout=1s",
        "app.internal.read-timeout=1s",
    ],
)
class AnswerControllerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var service: AnswerService

    private val student = UUID.randomUUID()
    private val attemptId = UUID.randomUUID()
    private val key = UUID.randomUUID()
    private val now = Instant.parse("2026-10-27T01:00:00Z")

    private fun answer(command: SubmitCommand) = Answer.next(
        previous = null, attemptId = attemptId, followupId = command.followupId, inputType = command.inputType,
        content = command.content, plainText = "", dictatedByGuardian = command.dictatedByGuardian,
        idempotencyKey = key, now = now,
    )

    private fun MockHttpServletRequestDsl.submission(body: String, role: String = "STUDENT", idempotencyKey: String? = key.toString()) {
        header("X-Internal-Token", "test-token")
        header("X-User-Role", role)
        header("X-Student-Scope", student.toString())
        idempotencyKey?.let { header("Idempotency-Key", it) }
        contentType = MediaType.APPLICATION_JSON
        content = body
    }

    @Test
    fun `제출은 201과 판정 PENDING, 메모 같은 모르는 필드는 무시`() {
        val command = SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "내 답"), dictatedByGuardian = false, followupId = null)
        given(service.submit(attemptId, key, command)).willReturn(answer(command))

        mockMvc.post("/internal/attempts/$attemptId/answers") {
            submission("""{"inputType":"NARRATIVE","text":"내 답","memo":"메모"}""")
        }.andExpect {
            status { isCreated() }
            jsonPath("$.attemptId") { value(attemptId.toString()) }
            jsonPath("$.version") { value(1) }
            jsonPath("$.followupId") { value(null) }
            jsonPath("$.submittedAt") { value("2026-10-27T01:00:00Z") }
            jsonPath("$.feedback.status") { value("PENDING") }
        }
    }

    @Test
    fun `입력 방식별 필드와 보호자 대필·되묻기 연결을 그대로 넘김`() {
        val followupId = UUID.randomUUID()
        val essay = SubmitCommand(
            InputType.ESSAY, AnswerContent(essay = Essay("찬성", listOf("안전", "편리"), "그래도 필요")),
            dictatedByGuardian = true, followupId = followupId,
        )
        val classification = SubmitCommand(
            InputType.CLASSIFICATION, AnswerContent(assignments = listOf(Assignment("a", "g1"))),
            dictatedByGuardian = false, followupId = null,
        )
        given(service.submit(attemptId, key, essay)).willReturn(answer(essay))
        given(service.submit(attemptId, key, classification)).willReturn(answer(classification))

        mockMvc.post("/internal/attempts/$attemptId/answers") {
            submission(
                """{"inputType":"ESSAY","essay":{"claim":"찬성","reasons":["안전","편리"],"rebuttal":"그래도 필요"},
                   "dictatedByGuardian":true,"followupId":"$followupId"}""",
            )
        }.andExpect {
            status { isCreated() }
            jsonPath("$.followupId") { value(followupId.toString()) }
        }
        mockMvc.post("/internal/attempts/$attemptId/answers") {
            submission("""{"inputType":"CLASSIFICATION","assignments":[{"choiceId":"a","categoryId":"g1"}]}""")
        }.andExpect { status { isCreated() } }
    }

    @Test
    fun `Idempotency-Key가 없거나 UUID가 아니거나 입력 방식이 없으면 400`() {
        listOf(null, "not-a-uuid").forEach { idempotencyKey ->
            mockMvc.post("/internal/attempts/$attemptId/answers") {
                submission("""{"inputType":"NARRATIVE","text":"답"}""", idempotencyKey = idempotencyKey)
            }.andExpect {
                status { isBadRequest() }
                jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
        listOf("""{"text":"답"}""", """{"inputType":"DRAWING","text":"답"}""").forEach { body ->
            mockMvc.post("/internal/attempts/$attemptId/answers") { submission(body) }.andExpect {
                status { isBadRequest() }
                jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
        verifyNoInteractions(service)
    }

    @Test
    fun `업무 오류는 코드와 안내 문구 그대로`() {
        val blank = SubmitCommand(InputType.NARRATIVE, AnswerContent(text = " "), dictatedByGuardian = false, followupId = null)
        given(service.submit(attemptId, key, blank)).willThrow(BusinessException(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INCOMPLETE", "답변 미완성", "내 생각을 먼저 적어 주세요."))

        mockMvc.post("/internal/attempts/$attemptId/answers") { submission("""{"inputType":"NARRATIVE","text":" "}""") }.andExpect {
            status { isUnprocessableEntity() }
            jsonPath("$.code") { value("ANSWER_INCOMPLETE") }
            jsonPath("$.detail") { value("내 생각을 먼저 적어 주세요.") }
        }
    }

    @Test
    fun `학생이 아니면 403`() {
        mockMvc.post("/internal/attempts/$attemptId/answers") {
            submission("""{"inputType":"NARRATIVE","text":"답"}""", role = "PARENT")
        }.andExpect {
            status { isForbidden() }
            jsonPath("$.code") { value("FORBIDDEN") }
        }
        verifyNoInteractions(service)
    }
}
