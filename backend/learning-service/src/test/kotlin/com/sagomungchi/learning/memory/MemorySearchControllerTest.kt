package com.sagomungchi.learning.memory

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.memory.controller.MemorySearchController
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

@WebMvcTest(MemorySearchController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(properties=["app.internal.token=test-token","app.internal.connect-timeout=1s","app.internal.read-timeout=1s"])
class MemorySearchControllerTest(@Autowired private val mvc: MockMvc) {
    @MockitoBean lateinit var service: MemorySearchService
    private val student=UUID.randomUUID()
    private val url="/internal/students/$student/memories/search"
    private fun MockHttpServletRequestDsl.auth(scope: UUID=student) {
        header("X-Internal-Token","test-token");header("X-User-Role","STUDENT");header("X-Student-Scope",scope.toString())
        contentType=MediaType.APPLICATION_JSON
    }
    @Test fun `세 가지 상태와 cards 응답 계약`() {
        for(state in listOf("NO_RECORDS","NO_RESULTS","RESULTS")) {
            given(service.search(student,"동물")).willReturn(MemorySearchResult(state))
            mvc.post(url) { auth();content="""{"query":" 동물 "}""" }.andExpect {
                status { isOk() };jsonPath("$.state") { value(state) };jsonPath("$.cards") { isArray() }
            }
        }
    }
    @Test fun `잘못된 질문과 다른 학생 거부`() {
        for(body in listOf("{}","""{"query":" "}""","""{"query":"${"가".repeat(201)}"}""")) {
            mvc.post(url) { auth();content=body }.andExpect { status { isBadRequest() } }
        }
        mvc.post(url) { auth(UUID.randomUUID());content="""{"query":"동물"}""" }.andExpect { status { isForbidden() } }
        verifyNoInteractions(service)
    }
    @Test fun `AI 장애는 503 계약 유지`() {
        given(service.search(student,"동물")).willThrow(BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"AI_UNAVAILABLE","일시 실패"))
        mvc.post(url) { auth();content="""{"query":"동물"}""" }.andExpect { status { isServiceUnavailable() } }
    }

    @Test fun `검색 카드의 날짜 식별자 인용 점수 직렬화`() {
        val theme=UUID.randomUUID();val mission=UUID.randomUUID();val attempt=UUID.randomUUID()
        given(service.search(student,"동물")).willReturn(MemorySearchResult("RESULTS",listOf(
            MemoryCard(theme,java.time.LocalDate.parse("2026-11-02"),"동물 이야기",null,
                listOf(MemoryMission(mission,"집 만들기",attempt,"동물을 도와요")),0.75))))
        val response=mvc.post(url) { auth();content="""{"query":"동물"}""" }.andExpect {
            status { isOk() };jsonPath("$.cards[0].weekStart") { value("2026-11-02") }
            jsonPath("$.cards[0].missions[0].attemptId") { value(attempt.toString()) }
            jsonPath("$.cards[0].score") { value(0.75) }
        }.andReturn().response.contentAsString
        System.getenv("MEMORY_CONTRACT_OUTPUT")?.let { java.io.File(it).writeText(response) }
    }
}
