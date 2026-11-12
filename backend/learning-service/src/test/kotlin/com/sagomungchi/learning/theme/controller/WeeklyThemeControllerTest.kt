package com.sagomungchi.learning.theme.controller

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.theme.domain.AnswerPickResult
import com.sagomungchi.learning.theme.domain.AnswerPickView
import com.sagomungchi.learning.theme.domain.DayState
import com.sagomungchi.learning.theme.domain.ThemeEndingState
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeStoryKind
import com.sagomungchi.learning.theme.domain.StoryViewResult
import com.sagomungchi.learning.theme.domain.ReviewViewResult
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDayView
import com.sagomungchi.learning.theme.domain.ThemeReview
import com.sagomungchi.learning.theme.domain.ThemeReviewMission
import com.sagomungchi.learning.theme.domain.ThemeSummaryState
import com.sagomungchi.learning.theme.domain.WeeklyThemeSummary
import com.sagomungchi.learning.theme.domain.WeeklyThemeView
import com.sagomungchi.learning.theme.service.WeeklyThemeService
import org.hamcrest.Matchers
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
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import java.time.LocalDate
import java.util.UUID

/** 학생 주간 테마 내부 API (#385, api-spec 2.11·4.1): core 프록시 조건(학생 본인·학년·날짜)과 응답 모양 */
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
        given(service.current(student, ThemeGrade.G3, monday)).willReturn(
            WeeklyThemeView(
                themeId, monday, "물의 여행", "소개", false,
                listOf(ThemeDayView(ThemeDay.MON, mission, "첫 문제", ThinkingType.ANALYZE, DayState.OPEN, "NOT_STARTED")),
                ThemeReview(false, listOf(ThemeReviewMission(mission, "첫 문제", completed = false, missed = false))),
                completed = false,
            ),
        )

        mockMvc.get("$base?grade=G3&date=2026-11-09") { as_() }.andExpect {
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
            jsonPath("$.answerPick") { value(Matchers.nullValue()) }
        }
    }

    @Test
    fun `고른 큰 질문 정답은 answerPick {pick, correct}로 돌려줌 (#590)`() {
        val friday = monday.plusDays(4)
        given(service.current(student, ThemeGrade.G3, friday)).willReturn(
            WeeklyThemeView(
                themeId, monday, "물의 여행", "소개", false, emptyList(), ThemeReview(false, emptyList()),
                completed = false, answerPick = AnswerPickView("고양이", false),
            ),
        )

        mockMvc.get("$base?grade=G3&date=2026-11-13") { as_() }.andExpect {
            status { isOk() }
            jsonPath("$.answerPick.pick") { value("고양이") }
            jsonPath("$.answerPick.correct") { value(false) }
            jsonPath("$.ending") { value("NOT_ENDED") }
            jsonPath("$.answer") { value(Matchers.nullValue()) }
        }
    }

    @Test
    fun `되돌아보기 열람은 본문 없이 firstViewThisWeek·completed`() {
        val sunday = monday.plusDays(6)
        given(service.recordReviewView(student, ThemeGrade.G5, sunday)).willReturn(ReviewViewResult(firstViewThisWeek = true, completed = true))

        mockMvc.post("$base/review-views?grade=G5&date=2026-11-15") { as_() }.andExpect {
            status { isOk() }
            jsonPath("$.firstViewThisWeek") { value(true) }
            jsonPath("$.completed") { value(true) }
        }
    }

    @Test
    fun `일요일 허용 값 sundayTheme을 조회·되돌아보기·이야기 열람에 넘기고 없으면 false (#484)`() {
        val sunday = monday.plusDays(6)
        given(service.recordReviewView(student, ThemeGrade.G3, sunday, true)).willReturn(ReviewViewResult(firstViewThisWeek = true, completed = false))
        given(service.recordReviewView(student, ThemeGrade.G3, sunday, false))
            .willThrow(BusinessException(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED", "되돌아보기 기간이 아님"))
        given(service.recordStoryView(student, ThemeGrade.G3, sunday, ThemeStoryKind.INTRO, true))
            .willReturn(StoryViewResult(ThemeStoryKind.INTRO, firstViewThisWeek = true))
        given(service.current(student, ThemeGrade.G3, sunday, true)).willReturn(
            WeeklyThemeView(themeId, monday, "물의 여행", "소개", false, emptyList(), ThemeReview(true, emptyList()), completed = false),
        )

        mockMvc.post("$base/review-views?grade=G3&date=2026-11-15&sundayTheme=true") { as_() }.andExpect { status { isOk() } }
        mockMvc.post("$base/review-views?grade=G3&date=2026-11-15") { as_() }.andExpect { status { isConflict() } }
        mockMvc.post("$base/story-views?grade=G3&date=2026-11-15&sundayTheme=true") {
            as_(); contentType = MediaType.APPLICATION_JSON; content = """{"kind":"INTRO"}"""
        }.andExpect { status { isOk() } }
        mockMvc.get("$base?grade=G3&date=2026-11-15&sundayTheme=true") { as_() }.andExpect { jsonPath("$.review.open") { value(true) } }
    }

    @Test
    fun `학생 본인이 아니거나 학생 역할이 아니면 403, 학년·날짜가 틀리면 400`() {
        mockMvc.get("$base?grade=G3&date=2026-11-09") { as_(scope = UUID.randomUUID()) }.andExpect { status { isForbidden() } }
        mockMvc.get("$base?grade=G3&date=2026-11-09") { as_(role = "PARENT") }.andExpect { status { isForbidden() } }
        mockMvc.get("$base?grade=G1_2&date=2026-11-09") { as_() }.andExpect { status { isBadRequest() } }
        mockMvc.get("$base?grade=G3&date=11-09") { as_() }.andExpect { status { isBadRequest() } }
        mockMvc.get("$base?grade=G3") { as_() }.andExpect { status { isBadRequest() } }
        verifyNoInteractions(service)
    }

    @Test
    fun `이야기 열람은 본문 kind로 서비스에 넘기고 kind가 없거나 모르는 값이면 400 (#438)`() {
        val thursday = monday.plusDays(3)
        given(service.recordStoryView(student, ThemeGrade.G4, thursday, ThemeStoryKind.INTRO))
            .willReturn(StoryViewResult(ThemeStoryKind.INTRO, firstViewThisWeek = true))

        mockMvc.post("$base/story-views?grade=G4&date=2026-11-12") {
            as_(); contentType = MediaType.APPLICATION_JSON; content = """{"kind":"INTRO"}"""
        }.andExpect {
            status { isOk() }
            jsonPath("$.kind") { value("INTRO") }
            jsonPath("$.firstViewThisWeek") { value(true) }
        }
        mockMvc.post("$base/story-views?grade=G4&date=2026-11-12") { as_(); contentType = MediaType.APPLICATION_JSON; content = "{}" }
            .andExpect { status { isBadRequest() } }
        mockMvc.post("$base/story-views?grade=G4&date=2026-11-12") { as_(); contentType = MediaType.APPLICATION_JSON; content = """{"kind":"MIDDLE"}""" }
            .andExpect { status { isBadRequest() } }
        mockMvc.post("$base/story-views?grade=G4&date=2026-11-12") {
            as_(scope = UUID.randomUUID()); contentType = MediaType.APPLICATION_JSON; content = """{"kind":"INTRO"}"""
        }.andExpect { status { isForbidden() } }
    }

    @Test
    fun `정답 고르기는 본문 pick과 sundayTheme을 넘기고 결과를 돌려주며 pick이 없거나 비면 400, 서비스 409는 그대로 (#484)`() {
        val friday = monday.plusDays(4)
        given(service.pickAnswer(student, ThemeGrade.G3, friday, "강아지", false))
            .willReturn(AnswerPickResult(true, ThemeEndingState.ENDED, "강아지"))
        given(service.pickAnswer(student, ThemeGrade.G3, friday, "고양이", false))
            .willThrow(BusinessException(HttpStatus.CONFLICT, "THEME_PICK_NOT_ALLOWED", "정답을 고를 수 없음"))
        fun pick(body: String) = mockMvc.post("$base/answer-picks?grade=G3&date=2026-11-13") {
            as_(); contentType = MediaType.APPLICATION_JSON; content = body
        }

        pick("""{"pick":"강아지"}""").andExpect {
            status { isOk() }
            jsonPath("$.correct") { value(true) }
            jsonPath("$.ending") { value("ENDED") }
            jsonPath("$.answer") { value("강아지") }
        }
        pick("""{"pick":"고양이"}""").andExpect {
            status { isConflict() }
            jsonPath("$.code") { value("THEME_PICK_NOT_ALLOWED") }
        }
        pick("{}").andExpect { status { isBadRequest() } }
        pick("""{"pick":" "}""").andExpect { status { isBadRequest() } }
        mockMvc.post("$base/answer-picks?grade=G3&date=2026-11-13") {
            as_(scope = UUID.randomUUID()); contentType = MediaType.APPLICATION_JSON; content = """{"pick":"강아지"}"""
        }.andExpect { status { isForbidden() } }
    }

    @Test
    fun `전환 기간에는 grade가 없으면 gradeBand를 낮은 학년으로 읽고, grade가 있으면 grade (#438)`() {
        val sunday = monday.plusDays(6)
        given(service.recordReviewView(student, ThemeGrade.G3, sunday)).willReturn(ReviewViewResult(firstViewThisWeek = true, completed = false))
        given(service.recordReviewView(student, ThemeGrade.G5, sunday)).willReturn(ReviewViewResult(firstViewThisWeek = false, completed = false))
        given(service.recordReviewView(student, ThemeGrade.G4, sunday)).willReturn(ReviewViewResult(firstViewThisWeek = false, completed = true))

        mockMvc.post("$base/review-views?gradeBand=G3_4&date=2026-11-15") { as_() }.andExpect { jsonPath("$.firstViewThisWeek") { value(true) } }
        mockMvc.post("$base/review-views?gradeBand=G5_6&date=2026-11-15") { as_() }.andExpect { jsonPath("$.firstViewThisWeek") { value(false) } }
        mockMvc.post("$base/review-views?grade=G4&gradeBand=G3_4&date=2026-11-15") { as_() }.andExpect { jsonPath("$.completed") { value(true) } }
        mockMvc.post("$base/review-views?gradeBand=G1_2&date=2026-11-15") { as_() }.andExpect { status { isBadRequest() } }
        mockMvc.post("$base/review-views?date=2026-11-15") { as_() }.andExpect { status { isBadRequest() } }
    }

    @Test
    fun `서비스 오류 코드는 그대로 (평일 되돌아보기 409)`() {
        given(service.recordReviewView(student, ThemeGrade.G3, monday))
            .willThrow(BusinessException(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED", "되돌아보기 기간이 아님"))

        mockMvc.post("$base/review-views?grade=G3&date=2026-11-09") { as_() }.andExpect {
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
