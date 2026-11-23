package com.sagomungchi.learning.wordhelp

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.domain.AttemptStatus
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.service.MissionService
import com.sagomungchi.learning.wordhelp.client.WordHelpAiClient
import com.sagomungchi.learning.wordhelp.controller.WordHelpController
import com.sagomungchi.learning.wordhelp.service.WordHelpService
import org.junit.jupiter.api.Test
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.CsvSource
import org.junit.jupiter.params.provider.EnumSource
import org.mockito.BDDMockito.given
import org.mockito.Mockito.mock
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.context.annotation.Import
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.post
import java.time.Instant
import java.util.UUID

/** 낱말 물어보기 경로 (#599, api-spec 4.1): 학생 본인 요청만, 질문 1~100자, ai 장애 코드·retryable 그대로 */
@WebMvcTest(WordHelpController::class)
@EnableConfigurationProperties(AppProperties::class)
@Import(WordHelpService::class, WordHelpAiClient::class)
@TestPropertySource(properties = ["app.internal.token=test-token", "app.internal.connect-timeout=1s", "app.internal.read-timeout=1s"])
class WordHelpControllerTest(@Autowired private val mockMvc: MockMvc, @Autowired private val mapper: ObjectMapper) {
    @MockitoBean lateinit var attempts: AttemptService
    @MockitoBean lateinit var missions: MissionService
    @MockitoBean lateinit var factory: InternalRestClientFactory

    private val student = UUID.randomUUID()
    private val attemptId = UUID.randomUUID()

    private fun givenOwnAttempt() {
        val version = UUID.randomUUID()
        val now = Instant.parse("2026-11-13T00:00:00Z")
        given(attempts.find(attemptId)).willReturn(
            Attempt(attemptId, student, UUID.randomUUID(), version, UUID.randomUUID(), 4, AttemptStatus.IN_PROGRESS, now, now, null, now),
        )
        val mission = mock(MissionView::class.java)
        given(mission.question).willReturn("분수를 써 보세요.")
        given(mission.subject).willReturn("수학")
        given(missions.getVersion(version)).willReturn(mission)
    }

    private fun MockHttpServletRequestDsl.asStudent(role: String = "STUDENT", body: String = """{"question":" 분수가 뭐야? "}""") {
        header("X-Internal-Token", "test-token")
        header("X-User-Role", role)
        header("X-Student-Scope", student.toString())
        contentType = MediaType.APPLICATION_JSON
        content = body
    }

    @Test fun `정상 AI 응답을 공개 형식으로 반환한다`() {
        givenOwnAttempt()
        val senses = """[
            {"definition":"뜻","source":"온용어","attribution":"우리말샘 / 국립국어원",
             "sourceUrl":"https://kli.korean.go.kr/term/trgtWord/indexTrgtWord.do?trgtWordNo=1",
             "license":"https://creativecommons.org/licenses/by-sa/2.0/kr/"},
            {"definition":"두 번째 뜻","source":"표준국어대사전"},
            {"definition":"세 번째 뜻","source":"표준국어대사전"}
        ]"""
        val server = stubWordHelpAi(factory, mapper, wordHelpAiBody(senses = senses))
        mockMvc.post("/internal/attempts/$attemptId/word-help") { asStudent() }.andExpect {
            status { isOk() }
            jsonPath("$.state") { value("EXPLAINED") }
            jsonPath("$.headword") { value("분수") }
            jsonPath("$.text") { value("쉬운 말") }
            jsonPath("$.senses.length()") { value(3) }
            jsonPath("$.senses[0].definition") { value("뜻") }
            jsonPath("$.senses[0].source") { value("온용어") }
            jsonPath("$.senses[0].attribution") { value("우리말샘 / 국립국어원") }
            jsonPath("$.senses[0].sourceUrl") { value("https://kli.korean.go.kr/term/trgtWord/indexTrgtWord.do?trgtWordNo=1") }
            jsonPath("$.senses[0].license") { value("https://creativecommons.org/licenses/by-sa/2.0/kr/") }
            jsonPath("$.senses[1].source") { value("표준국어대사전") }
            jsonPath("$.versions") { doesNotExist() }
        }
        server.verify()
    }

    @Test fun `빈 질문·100자 초과는 400, 학생이 아니면 403이고 서비스를 부르지 않는다`() {
        mockMvc.post("/internal/attempts/$attemptId/word-help") { asStudent(body = """{"question":"  "}""") }.andExpect { status { isBadRequest() } }
        mockMvc.post("/internal/attempts/$attemptId/word-help") { asStudent(body = """{"question":"${"가".repeat(101)}"}""") }.andExpect { status { isBadRequest() } }
        mockMvc.post("/internal/attempts/$attemptId/word-help") { asStudent(role = "PARENT") }.andExpect { status { isForbidden() } }
        verifyNoInteractions(attempts, missions, factory)
    }

    @ParameterizedTest
    @CsvSource("DICTIONARY_UNAVAILABLE,true,사전 조회 실패", "AI_UNAVAILABLE,false,낱말 설명 처리 실패")
    fun `ai 장애는 코드와 retryable을 그대로 전달`(code: String, retryable: Boolean, title: String) {
        givenOwnAttempt()
        val server = stubWordHelpAi(factory, mapper, """{"code":"$code","retryable":$retryable}""", HttpStatus.SERVICE_UNAVAILABLE)
        mockMvc.post("/internal/attempts/$attemptId/word-help") { asStudent() }.andExpect {
            status { isServiceUnavailable() }
            jsonPath("$.code") { value(code) }
            jsonPath("$.retryable") { value(retryable) }
            jsonPath("$.title") { value(title) }
            jsonPath("$.detail") { value("잠시 후 다시 물어봐 주세요.") }
        }
        server.verify()
    }

    @ParameterizedTest
    @EnumSource(InvalidWordHelpResponse::class)
    fun `계약 밖 AI 응답을 502 Problem으로 반환한다`(response: InvalidWordHelpResponse) {
        givenOwnAttempt()
        val server = stubWordHelpAi(factory, mapper, response.json)
        mockMvc.post("/internal/attempts/$attemptId/word-help") { asStudent() }.andExpect {
            status { isBadGateway() }
            jsonPath("$.code") { value("AI_BAD_RESPONSE") }
            jsonPath("$.retryable") { value(false) }
            jsonPath("$.detail") { value("잠시 후 다시 물어봐 주세요.") }
        }
        server.verify()
    }
}
