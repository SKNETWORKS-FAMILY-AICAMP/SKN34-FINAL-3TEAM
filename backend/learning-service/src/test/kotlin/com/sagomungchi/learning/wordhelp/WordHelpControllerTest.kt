package com.sagomungchi.learning.wordhelp

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning.wordhelp.client.WordHelpAiException
import com.sagomungchi.learning.wordhelp.client.WordHelpAiResponse
import com.sagomungchi.learning.wordhelp.client.WordSense
import com.sagomungchi.learning.wordhelp.controller.WordHelpController
import com.sagomungchi.learning.wordhelp.service.WordHelpService
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.http.MediaType
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.post
import java.util.UUID

/** 낱말 물어보기 경로 (#599, api-spec 4.1): 학생 본인 요청만, 질문 1~100자, ai 장애 코드·retryable 그대로 */
@WebMvcTest(WordHelpController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(properties = ["app.internal.token=test-token", "app.internal.connect-timeout=1s", "app.internal.read-timeout=1s"])
class WordHelpControllerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var service: WordHelpService

    private val student = UUID.randomUUID()
    private val attemptId = UUID.randomUUID()

    private fun MockHttpServletRequestDsl.asStudent(role: String = "STUDENT", body: String = """{"question":" 분수가 뭐야? "}""") {
        header("X-Internal-Token", "test-token")
        header("X-User-Role", role)
        header("X-Student-Scope", student.toString())
        contentType = MediaType.APPLICATION_JSON
        content = body
    }

    @Test fun `질문을 다듬어 넘기고 결과를 그대로 돌려준다`() {
        given(service.help(attemptId, "분수가 뭐야?")).willReturn(
            WordHelpAiResponse("EXPLAINED", "분수", "쉬운 말", "예문", listOf(
                WordSense("뜻", "온용어", "우리말샘 / 국립국어원",
                    "https://kli.korean.go.kr/term/trgtWord/indexTrgtWord.do?trgtWordNo=1",
                    "https://creativecommons.org/licenses/by-sa/2.0/kr/"),
            )))
        mockMvc.post("/internal/attempts/$attemptId/word-help") { asStudent() }.andExpect {
            status { isOk() }
            jsonPath("$.state") { value("EXPLAINED") }
            jsonPath("$.senses[0].source") { value("온용어") }
            jsonPath("$.senses[0].attribution") { value("우리말샘 / 국립국어원") }
            jsonPath("$.senses[0].sourceUrl") { value("https://kli.korean.go.kr/term/trgtWord/indexTrgtWord.do?trgtWordNo=1") }
            jsonPath("$.senses[0].license") { value("https://creativecommons.org/licenses/by-sa/2.0/kr/") }
            jsonPath("$.versions") { doesNotExist() }
        }
    }

    @Test fun `빈 질문·100자 초과는 400, 학생이 아니면 403이고 서비스를 부르지 않는다`() {
        mockMvc.post("/internal/attempts/$attemptId/word-help") { asStudent(body = """{"question":"  "}""") }.andExpect { status { isBadRequest() } }
        mockMvc.post("/internal/attempts/$attemptId/word-help") { asStudent(body = """{"question":"${"가".repeat(101)}"}""") }.andExpect { status { isBadRequest() } }
        mockMvc.post("/internal/attempts/$attemptId/word-help") { asStudent(role = "PARENT") }.andExpect { status { isForbidden() } }
        verifyNoInteractions(service)
    }

    @Test fun `ai 장애는 코드와 retryable을 그대로 전달`() {
        given(service.help(attemptId, "분수가 뭐야?")).willThrow(WordHelpAiException(503, "DICTIONARY_UNAVAILABLE", retryable = true))
        mockMvc.post("/internal/attempts/$attemptId/word-help") { asStudent() }.andExpect {
            status { isServiceUnavailable() }
            jsonPath("$.code") { value("DICTIONARY_UNAVAILABLE") }
            jsonPath("$.retryable") { value(true) }
        }
    }
}
