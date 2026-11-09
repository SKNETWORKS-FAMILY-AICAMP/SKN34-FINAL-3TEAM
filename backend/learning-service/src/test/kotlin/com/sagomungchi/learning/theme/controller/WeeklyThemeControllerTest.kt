package com.sagomungchi.learning.theme.controller

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.theme.domain.DayState
import com.sagomungchi.learning.theme.domain.GradeBand
import com.sagomungchi.learning.theme.domain.ReviewViewResult
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDayView
import com.sagomungchi.learning.theme.domain.ThemeReview
import com.sagomungchi.learning.theme.domain.ThemeReviewMission
import com.sagomungchi.learning.theme.domain.ThemeSummaryState
import com.sagomungchi.learning.theme.domain.WeeklyThemeSummary
import com.sagomungchi.learning.theme.domain.WeeklyThemeView
import com.sagomungchi.learning.theme.service.WeeklyThemeService
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.http.HttpStatus
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import java.time.LocalDate
import java.util.UUID

/** 학생 주간 테마 내부 API (#385, api-spec 2.11·4.1): core 프록시 조건(학생 본인·학년군·날짜)과 응답 모양 */
@WebMvcTest(WeeklyThemeController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(properties = ["app.internal.token=test-token", "app.internal.connect-timeout=1s", "app.internal.read-timeout=1s"])
class WeeklyThemeControllerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var service: WeeklyThemeService
    @MockitoBean lateinit var reports: com.sagomungchi.learning.theme.service.WeeklyThemeReportService

    private val student = UUID.randomUUID()
    private val mission = UUID.randomUUID()
    private val themeId = UUID.randomUUID()
    private val monday = LocalDate.of(2026, 11, 9)
    private val base = "/internal/students/$student/weekly-theme"

    private fun MockHttpServletRequestDsl.as_(role: String = "STUDENT", scope: UUID = student) {
        header("X-Internal-Token", "test-token")
        header("X-User-Role", role)
        header("X-Student-Scope", scope.toString())
    }

    @Test
    fun `이번 주 테마는 요일·상태·되돌아보기를 그대로 돌려줌`() {
        given(service.current(student, GradeBand.G3_4, monday)).willReturn(
            WeeklyThemeView(
                themeId, monday, "물의 여행", "소개", false,
                listOf(ThemeDayView(ThemeDay.MON, mission, "첫 문제", ThinkingType.ANALYZE, DayState.OPEN, "NOT_STARTED")),
                ThemeReview(false, listOf(ThemeReviewMission(mission, "첫 문제", completed = false, missed = false))),
                completed = false,
            ),
        )

        mockMvc.get("$base?gradeBand=G3_4&date=2026-11-09") { as_() }.andExpect {
            status { isOk() }
            jsonPath("$.themeId") { value(themeId.toString()) }
            jsonPath("$.weekStart") { value("2026-11-09") }
            jsonPath("$.intro") { value("소개") }
            jsonPath("$.reused") { value(false) }
            jsonPath("$.days[0].day") { value("MON") }
            jsonPath("$.days[0].thinkingType") { value("ANALYZE") }
            jsonPath("$.days[0].state") { value("OPEN") }
            jsonPath("$.days[0].attemptStatus") { value("NOT_STARTED") }
            jsonPath("$.review.open") { value(false) }
            jsonPath("$.review.missions[0].missed") { value(false) }
            jsonPath("$.completed") { value(false) }
        }
    }

    @Test
    fun `되돌아보기 열람은 본문 없이 firstViewThisWeek·completed`() {
        val sunday = monday.plusDays(6)
        given(service.recordReviewView(student, GradeBand.G5_6, sunday)).willReturn(ReviewViewResult(firstViewThisWeek = true, completed = true))

        mockMvc.post("$base/review-views?gradeBand=G5_6&date=2026-11-15") { as_() }.andExpect {
            status { isOk() }
            jsonPath("$.firstViewThisWeek") { value(true) }
            jsonPath("$.completed") { value(true) }
        }
    }

    @Test
    fun `학생 본인이 아니거나 학생 역할이 아니면 403, 학년군·날짜가 틀리면 400`() {
        mockMvc.get("$base?gradeBand=G3_4&date=2026-11-09") { as_(scope = UUID.randomUUID()) }.andExpect { status { isForbidden() } }
        mockMvc.get("$base?gradeBand=G3_4&date=2026-11-09") { as_(role = "PARENT") }.andExpect { status { isForbidden() } }
        mockMvc.get("$base?gradeBand=G1_2&date=2026-11-09") { as_() }.andExpect { status { isBadRequest() } }
        mockMvc.get("$base?gradeBand=G3_4&date=11-09") { as_() }.andExpect { status { isBadRequest() } }
        mockMvc.get("$base?gradeBand=G3_4") { as_() }.andExpect { status { isBadRequest() } }
        verifyNoInteractions(service)
    }

    @Test
    fun `서비스 오류 코드는 그대로 (평일 되돌아보기 409)`() {
        given(service.recordReviewView(student, GradeBand.G3_4, monday))
            .willThrow(BusinessException(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED", "되돌아보기 기간이 아님"))

        mockMvc.post("$base/review-views?gradeBand=G3_4&date=2026-11-09") { as_() }.andExpect {
            status { isConflict() }
            jsonPath("$.code") { value("THEME_REVIEW_NOT_ALLOWED") }
        }
    }

    @Test
    fun `주간 요약은 학부모·학생·시스템이 범위 학생만, 월요일이 아니면 400`() {
        given(reports.summary(student, monday)).willReturn(
            WeeklyThemeSummary(student, monday, ThemeSummaryState.NO_RECORD, null, null, emptyList(), false, emptyList()),
        )

        listOf("SYSTEM", "PARENT", "STUDENT").forEach { role ->
            mockMvc.get("$base/summary?weekStart=2026-11-09") { as_(role = role) }.andExpect {
                status { isOk() }
                jsonPath("$.state") { value("NO_RECORD") }
                jsonPath("$.themeId") { value(null) }
                jsonPath("$.days.length()") { value(0) }
            }
        }
        mockMvc.get("$base/summary?weekStart=2026-11-09") { as_(role = "ADMIN") }.andExpect { status { isForbidden() } }
        mockMvc.get("$base/summary?weekStart=2026-11-09") { as_(role = "SYSTEM", scope = UUID.randomUUID()) }.andExpect { status { isForbidden() } }
        mockMvc.get("$base/summary?weekStart=2026-11-10") { as_(role = "SYSTEM") }.andExpect {
            status { isBadRequest() }
            jsonPath("$.code") { value("VALIDATION_FAILED") }
        }
    }
}
