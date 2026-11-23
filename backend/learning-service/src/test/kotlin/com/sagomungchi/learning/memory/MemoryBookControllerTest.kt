package com.sagomungchi.learning.memory

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.security.InternalCallerPolicy
import com.sagomungchi.learning.memory.controller.MemoryBookController
import com.sagomungchi.learning.memory.domain.MemoryBookEnding
import com.sagomungchi.learning.memory.domain.MemoryBookRound
import com.sagomungchi.learning.memory.domain.RoundKey
import com.sagomungchi.learning.memory.service.MemoryBookService
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import java.time.LocalDate
import java.util.UUID
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** 추억 그림책 회차 조립 내부 API (docs/proposals/memory-book.md 7.2): SYSTEM 역할·학생 범위·월요일 검사, report-worker 경로 허용 */
@WebMvcTest(MemoryBookController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(properties = ["app.internal.token=test-token", "app.internal.connect-timeout=1s", "app.internal.read-timeout=1s"])
class MemoryBookControllerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var service: MemoryBookService

    private val student = UUID.randomUUID()
    private val themeId = UUID.randomUUID()
    private val week = LocalDate.of(2026, 11, 2)
    private val path = "/internal/students/$student/memory-book/$themeId/$week"

    private fun MockHttpServletRequestDsl.as_(role: String = "SYSTEM", scope: UUID = student) {
        header("X-Internal-Token", "test-token")
        header("X-User-Role", role)
        header("X-Student-Scope", scope.toString())
    }

    @Test
    fun `SYSTEM 역할과 경로 학생 범위면 회차 조립 결과를 그대로`() {
        given(service.round(student, RoundKey(themeId, week))).willReturn(
            MemoryBookRound(themeId, week, UUID.randomUUID(), "등대 불빛", "소개", null, null, emptyList(),
                MemoryBookEnding(false, null, null, null)),
        )
        mockMvc.get(path) { as_() }.andExpect {
            status { isOk() }
            jsonPath("$.title") { value("등대 불빛") }
            jsonPath("$.ending.seen") { value(false) }
            jsonPath("$.ending.outroImage") { value(null) }
        }
    }

    @Test
    fun `학생·학부모 역할, 다른 학생 범위는 403이고 서비스를 부르지 않음`() {
        mockMvc.get(path) { as_(role = "STUDENT") }.andExpect { status { isForbidden() } }
        mockMvc.get(path) { as_(role = "PARENT") }.andExpect { status { isForbidden() } }
        mockMvc.get(path) { as_(scope = UUID.randomUUID()) }.andExpect { status { isForbidden() } }
        verifyNoInteractions(service)
    }

    @Test
    fun `월요일이 아닌 weekStart는 400`() {
        mockMvc.get("/internal/students/$student/memory-book/$themeId/${week.plusDays(1)}") { as_() }
            .andExpect { status { isBadRequest() } }
        verifyNoInteractions(service)
    }

    @Test
    fun `report-worker는 그림책 경로를 부를 수 있고 report-api는 못 부름`() {
        assertTrue(InternalCallerPolicy.permits("report-worker", path))
        assertFalse(InternalCallerPolicy.permits("report-api", path))
        assertFalse(InternalCallerPolicy.permits("report-worker", "/internal/students/$student/memory-book/$themeId/../album"))
    }
}
