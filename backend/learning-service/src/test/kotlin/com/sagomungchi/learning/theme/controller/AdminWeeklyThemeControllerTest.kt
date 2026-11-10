package com.sagomungchi.learning.theme.controller

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.DomainException
import com.sagomungchi.learning._common.exception.ErrorKind
import com.sagomungchi.learning.theme.domain.AdminWeeklyTheme
import com.sagomungchi.learning.theme.domain.AdminWeeklyThemePage
import com.sagomungchi.learning.theme.domain.GradeBand
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDayMission
import com.sagomungchi.learning.theme.domain.ThemePublishError
import com.sagomungchi.learning.theme.domain.WeeklyThemePublishIncompleteException
import com.sagomungchi.learning.theme.domain.WeeklyThemeStatus
import com.sagomungchi.learning.theme.domain.ThemeContent
import com.sagomungchi.learning.theme.service.WeeklyThemeAdminService
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
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import org.springframework.test.web.servlet.put
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

/** 관리자 주간 테마 내부 API (#385, api-spec 2.8·4.1): core 프록시 조건(ADMIN·X-User-Id·JSON 객체)과 오류 모양 */
@WebMvcTest(AdminWeeklyThemeController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(properties = ["app.internal.token=test-token", "app.internal.connect-timeout=1s", "app.internal.read-timeout=1s"])
class AdminWeeklyThemeControllerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var service: WeeklyThemeAdminService

    private val admin = UUID.randomUUID()
    private val themeId = UUID.randomUUID()
    private val mission = UUID.randomUUID()
    private val monday = LocalDate.of(2026, 11, 9)
    private val now = Instant.parse("2026-11-08T01:00:00Z")
    private val theme = AdminWeeklyTheme(
        themeId, GradeBand.G3_4, monday, WeeklyThemeStatus.DRAFT, 1, null, false, "물의 여행", "소개",
        listOf(ThemeDayMission(ThemeDay.MON, mission)), null, now, now,
    )
    private val body = """{"gradeBand":"G3_4","weekStart":"2026-11-09","title":"물의 여행","intro":"소개","days":[{"day":"MON","missionId":"$mission"}]}"""

    private fun MockHttpServletRequestDsl.asAdmin(role: String = "ADMIN", userId: String? = admin.toString(), content: String? = null) {
        header("X-Internal-Token", "test-token")
        header("X-User-Role", role)
        userId?.let { header("X-User-Id", it) }
        content?.let {
            contentType = MediaType.APPLICATION_JSON
            this.content = it
        }
    }

    @Test
    fun `작성은 201과 테마 전체, 작성자는 X-User-Id`() {
        val content = ThemeContent(GradeBand.G3_4, monday, "물의 여행", "소개", listOf(ThemeDayMission(ThemeDay.MON, mission)))
        given(service.create(admin, content)).willReturn(theme)

        mockMvc.post("/internal/admin/weekly-themes") { asAdmin(content = body) }.andExpect {
            status { isCreated() }
            jsonPath("$.themeId") { value(themeId.toString()) }
            jsonPath("$.gradeBand") { value("G3_4") }
            jsonPath("$.weekStart") { value("2026-11-09") }
            jsonPath("$.status") { value("DRAFT") }
            jsonPath("$.version") { value(1) }
            jsonPath("$.publishedVersion") { value(null) }
            jsonPath("$.reviewRequested") { value(false) }
            jsonPath("$.days[0].day") { value("MON") }
            jsonPath("$.days[0].missionId") { value(mission.toString()) }
        }
    }

    @Test
    fun `목록은 필터를 넘기고 items·page·size·totalElements 봉투`() {
        given(service.list(GradeBand.G5_6, monday, WeeklyThemeStatus.PUBLISHED, 1, 10)).willReturn(AdminWeeklyThemePage(listOf(theme), 1, 10, 11))

        mockMvc.get("/internal/admin/weekly-themes?gradeBand=G5_6&weekStart=2026-11-09&status=PUBLISHED&page=1&size=10") { asAdmin() }.andExpect {
            status { isOk() }
            jsonPath("$.items[0].themeId") { value(themeId.toString()) }
            jsonPath("$.totalElements") { value(11) }
        }
    }

    @Test
    fun `수정·검토 요청·중단은 테마 전체를 돌려줌`() {
        val content = ThemeContent(GradeBand.G3_4, monday, "물의 여행", "소개", listOf(ThemeDayMission(ThemeDay.MON, mission)))
        given(service.update(themeId, admin, content)).willReturn(theme)
        given(service.requestReview(themeId)).willReturn(theme)
        given(service.unpublish(themeId)).willReturn(theme)

        mockMvc.put("/internal/admin/weekly-themes/$themeId") { asAdmin(content = body) }.andExpect { status { isOk() } }
        mockMvc.post("/internal/admin/weekly-themes/$themeId/review-request") { asAdmin(content = "{}") }.andExpect { status { isOk() } }
        mockMvc.post("/internal/admin/weekly-themes/$themeId/unpublish") { asAdmin(content = "{}") }.andExpect {
            status { isOk() }
            jsonPath("$.themeId") { value(themeId.toString()) }
        }
    }

    @Test
    fun `게시 검사 실패는 422와 errors code·message`() {
        given(service.publish(themeId)).willThrow(
            WeeklyThemePublishIncompleteException(listOf(ThemePublishError("THINKING_TYPES", "다섯 생각 유형이 하나씩 있어야 해요"))),
        )

        mockMvc.post("/internal/admin/weekly-themes/$themeId/publish") { asAdmin(content = "{}") }.andExpect {
            status { isUnprocessableEntity() }
            jsonPath("$.code") { value("WEEKLY_THEME_PUBLISH_INCOMPLETE") }
            jsonPath("$.errors[0].code") { value("THINKING_TYPES") }
            jsonPath("$.errors[0].message") { value("다섯 생각 유형이 하나씩 있어야 해요") }
        }
    }

    @Test
    fun `허용 안 되는 전이는 409 CONFLICT`() {
        given(service.publish(themeId)).willThrow(DomainException(ErrorKind.CONFLICT, "CONFLICT", "주간 테마 상태 충돌"))

        mockMvc.post("/internal/admin/weekly-themes/$themeId/publish") { asAdmin(content = "{}") }.andExpect {
            status { isConflict() }
            jsonPath("$.code") { value("CONFLICT") }
        }
    }

    @Test
    fun `관리자가 아니거나 작성자가 UUID가 아니면 거부, 본문이 틀리면 400`() {
        mockMvc.get("/internal/admin/weekly-themes") { asAdmin(role = "PARENT") }.andExpect { status { isForbidden() } }
        mockMvc.post("/internal/admin/weekly-themes") { asAdmin(userId = "not-uuid", content = body) }.andExpect { status { isBadRequest() } }
        listOf(
            body.replace("2026-11-09", "2026-11-10"),
            body.replace("\"G3_4\"", "\"G1_2\""),
            body.replace("\"물의 여행\"", "\"  \""),
            body.replace(""""intro":"소개",""", ""),
            body.replace("""[{"day":"MON","missionId":"$mission"}]""", """[{"day":"MON","missionId":"$mission"},{"day":"MON","missionId":"${UUID.randomUUID()}"}]"""),
            body.replace("""[{"day":"MON","missionId":"$mission"}]""", """[{"day":"MON","missionId":"$mission"},{"day":"TUE","missionId":"$mission"}]"""),
            body.replace("\"MON\"", "\"SAT\""),
        ).forEach { wrong ->
            mockMvc.post("/internal/admin/weekly-themes") { asAdmin(content = wrong) }.andExpect {
                status { isBadRequest() }
            }
        }
        mockMvc.get("/internal/admin/weekly-themes?weekStart=2026-11-10") { asAdmin() }.andExpect { status { isBadRequest() } }
        mockMvc.get("/internal/admin/weekly-themes?size=0") { asAdmin() }.andExpect { status { isBadRequest() } }
        verifyNoInteractions(service)
    }
}
