package com.sagomungchi.learning.memory

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.memory.controller.MemoryExplanationController
import com.sagomungchi.learning.memory.service.*
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
import java.util.UUID

@WebMvcTest(MemoryExplanationController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(properties=["app.internal.token=test-token","app.internal.connect-timeout=1s","app.internal.read-timeout=1s"])
class MemoryExplanationControllerTest(@Autowired private val mvc: MockMvc) {
    @MockitoBean lateinit var service: MemoryExplanationService
    private val student=UUID.randomUUID()
    private val url="/internal/students/$student/memories/explanations"
    private fun MockHttpServletRequestDsl.auth(scope: UUID=student) {
        header("X-Internal-Token","test-token");header("X-User-Role","STUDENT");header("X-Student-Scope",scope.toString())
        contentType=MediaType.APPLICATION_JSON
    }
    private val attempt=UUID.randomUUID()
    private val valid="""{"query":"질문","attemptIds":["$attempt"]}"""
    @Test fun `세 상태와 실제 인용 식별자 직렬화`() {
        for(state in listOf("GENERATED","INSUFFICIENT","FAILED")) {
            val result=if(state=="GENERATED") MemoryExplanationResult(state,"설명[1].",listOf(MemoryCitation(1,UUID.randomUUID(),java.time.LocalDate.parse("2026-11-02"),attempt))) else MemoryExplanationResult(state)
            given(service.explain(student,"질문",listOf(attempt))).willReturn(result)
            val response=mvc.post(url) { auth();content=valid }.andExpect {
                status { isOk() };jsonPath("$.state") { value(state) };jsonPath("$.citations") { isArray() }
            }.andReturn().response.contentAsString
            System.getenv("MEMORY_EXPLANATION_CONTRACT_DIR")?.let { java.io.File(it,"$state.json").writeText(response) }
        }
    }
    @Test fun `형식 인증 범위 오류는 호출하지 않음`() {
        for(body in listOf("{}",
            """{"query":"질문","attemptIds":[null]}""",
            """{"query":"질문","attemptIds":["${UUID.randomUUID()}","${UUID.randomUUID()}","${UUID.randomUUID()}","${UUID.randomUUID()}"]}""","""{"query":" ","attemptIds":["$attempt"]}""","""{"query":"질문","attemptIds":[]}""",
            """{"query":"질문","attemptIds":["$attempt","$attempt"]}""","""{"query":"질문","attemptIds":["invalid"]}""",
            """{"query":"${"가".repeat(201)}","attemptIds":["$attempt"]}"""))
            mvc.post(url) { auth();content=body }.andExpect { status { isBadRequest() } }
        mvc.post(url) { auth(UUID.randomUUID());content=valid }.andExpect { status { isForbidden() } }
        mvc.post(url) { contentType=MediaType.APPLICATION_JSON;content=valid }.andExpect { status { isUnauthorized() } }
        verifyNoInteractions(service)
    }
    @Test fun `본인 검색 범위 아닌 ID는 422`() {
        given(service.explain(student,"질문",listOf(attempt))).willThrow(BusinessException(HttpStatus.UNPROCESSABLE_ENTITY,"VALIDATION_FAILED","범위 오류"))
        mvc.post(url) { auth();content=valid }.andExpect { status { isUnprocessableEntity() } }
    }
    @Test fun `ai 장애는 503 AI_UNAVAILABLE`() {
        given(service.explain(student,"질문",listOf(attempt))).willThrow(BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"AI_UNAVAILABLE","추억 설명을 잠시 사용할 수 없어요"))
        mvc.post(url) { auth();content=valid }.andExpect { status { isServiceUnavailable() };jsonPath("$.code") { value("AI_UNAVAILABLE") } }
    }
}
