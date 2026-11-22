package com.sagomungchi.learning.theme.controller

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.DomainException
import com.sagomungchi.learning._common.exception.ErrorKind
import com.sagomungchi.learning.theme.domain.AdminThemeDay
import com.sagomungchi.learning.theme.domain.AdminWeeklyTheme
import com.sagomungchi.learning.theme.domain.AdminWeeklyThemePage
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDayMission
import com.sagomungchi.learning.theme.domain.ThemeFeature
import com.sagomungchi.learning.theme.domain.ThemeFeatureValue
import com.sagomungchi.learning.theme.domain.ThemeStory
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
    @MockitoBean lateinit var planner: com.sagomungchi.learning.theme.service.ThemeWeekPlanner

    private val admin = UUID.randomUUID()
    private val themeId = UUID.randomUUID()
    private val mission = UUID.randomUUID()
    private val monday = LocalDate.of(2026, 11, 9)
    private val now = Instant.parse("2026-11-08T01:00:00Z")
    private val theme = AdminWeeklyTheme(
        themeId, ThemeGrade.G3, monday, WeeklyThemeStatus.DRAFT, 1, null, false, "물의 여행", "소개",
        listOf(AdminThemeDay(ThemeDay.MON, mission)), null, now, now,
    )
    private val body = """{"grade":"G3","weekStart":"2026-11-09","title":"물의 여행","intro":"소개","days":[{"day":"MON","missionId":"$mission"}]}"""

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
        val content = ThemeContent(ThemeGrade.G3, monday, "물의 여행", "소개", listOf(ThemeDayMission(ThemeDay.MON, mission)))
        given(service.create(admin, content)).willReturn(theme)

        mockMvc.post("/internal/admin/weekly-themes") { asAdmin(content = body) }.andExpect {
            status { isCreated() }
            jsonPath("$.themeId") { value(themeId.toString()) }
            jsonPath("$.grade") { value("G3") }
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
    fun `특징 표와 요일 특징 이름을 본문에서 읽어 서비스에 넘기고 응답에 담음 (#647)`() {
        val features = listOf(ThemeFeature("털", listOf(ThemeFeatureValue("고양이", "짧은"), ThemeFeatureValue("강아지", "긴"))))
        val content = ThemeContent(ThemeGrade.G3, monday, "물의 여행", "소개", listOf(ThemeDayMission(ThemeDay.MON, mission, clueFeature = "털")),
            ThemeStory(features = features))
        given(service.create(admin, content)).willReturn(
            theme.copy(days = listOf(AdminThemeDay(ThemeDay.MON, mission, clueFeature = "털")), features = features),
        )
        val withFeatures = body.replace("\"missionId\":\"$mission\"", "\"missionId\":\"$mission\",\"clueFeature\":\"털\"")
            .replace("}]}", "}],\"features\":[{\"name\":\"털\",\"values\":[{\"candidate\":\"고양이\",\"value\":\"짧은\"},{\"candidate\":\"강아지\",\"value\":\"긴\"}]}]}")

        mockMvc.post("/internal/admin/weekly-themes") { asAdmin(content = withFeatures) }.andExpect {
            status { isCreated() }
            jsonPath("$.days[0].clueFeature") { value("털") }
            jsonPath("$.features[0].name") { value("털") }
            jsonPath("$.features[0].values[1].value") { value("긴") }
        }
    }

    @Test
    fun `목록은 필터를 넘기고 items·page·size·totalElements 봉투`() {
        given(service.list(ThemeGrade.G5, monday, WeeklyThemeStatus.PUBLISHED, 1, 10)).willReturn(AdminWeeklyThemePage(listOf(theme), 1, 10, 11))

        mockMvc.get("/internal/admin/weekly-themes?grade=G5&weekStart=2026-11-09&status=PUBLISHED&page=1&size=10") { asAdmin() }.andExpect {
            status { isOk() }
            jsonPath("$.items[0].themeId") { value(themeId.toString()) }
            jsonPath("$.totalElements") { value(11) }
        }
    }

    @Test
    fun `편성 보드와 주차 변경은 관리자 권한을 검사한다`() {
        val route="/internal/admin/weekly-themes/planner"
        val board=com.sagomungchi.learning.theme.service.WeekBoard(ThemeGrade.G3,monday,emptyList(),emptyList())
        given(planner.board(ThemeGrade.G3,monday)).willReturn(board)
        mockMvc.get(route+"?grade=G3&weekStart="+monday) { asAdmin() }.andExpect {
            status { isOk() }; jsonPath("$.weekStart") { value(monday.toString()) }
        }
        val change="""{"grade":"G3","draftId":"$themeId","expectedWeek":null,"targetWeek":"$monday","expectedTargetDraftId":null}"""
        mockMvc.put(route) { asAdmin(role="PARENT",content=change) }.andExpect { status { isForbidden() } }
        val command=com.sagomungchi.learning.theme.service.PlanChange(ThemeGrade.G3,themeId,null,monday,null)
        given(planner.change(command)).willReturn(com.sagomungchi.learning.theme.service.PlanResult(themeId,ThemeGrade.G3,monday,null))
        mockMvc.put(route) { asAdmin(content=change) }.andExpect {
            status { isOk() }; jsonPath("$.plannedWeek") { value(monday.toString()) }
        }
    }

    @Test
    fun `수정·검토 요청은 테마 전체를 돌려주며 확정 후 중단은 409`() {
        val content = ThemeContent(ThemeGrade.G3, monday, "물의 여행", "소개", listOf(ThemeDayMission(ThemeDay.MON, mission)))
        given(service.update(themeId, admin, content)).willReturn(theme)
        given(service.requestReview(themeId)).willReturn(theme)
        given(service.unpublish(themeId)).willThrow(com.sagomungchi.learning._common.exception.BusinessException(
            org.springframework.http.HttpStatus.CONFLICT,"WEEK_LOCKED","이미 게시가 확정된 주차입니다."))

        mockMvc.put("/internal/admin/weekly-themes/$themeId") { asAdmin(content = body) }.andExpect { status { isOk() } }
        mockMvc.post("/internal/admin/weekly-themes/$themeId/review-request") { asAdmin(content = "{}") }.andExpect { status { isOk() } }
        mockMvc.post("/internal/admin/weekly-themes/$themeId/unpublish") { asAdmin(content = "{}") }.andExpect {
            status { isConflict() }
            jsonPath("$.code") { value("WEEK_LOCKED") }
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
            body.replace("\"G3\"", "\"G1_2\""),
            body.replace("\"물의 여행\"", "\"  \""),
            body.replace(""""intro":"소개",""", ""),
            body.replace("""[{"day":"MON","missionId":"$mission"}]""", """[{"day":"MON","missionId":"$mission"},{"day":"MON","missionId":"${UUID.randomUUID()}"}]"""),
            body.replace("""[{"day":"MON","missionId":"$mission"}]""", """[{"day":"MON","missionId":"$mission"},{"day":"TUE","missionId":"$mission"}]"""),
            body.replace("\"MON\"", "\"SAT\""),
            // #647 특징 표 상한: 특징 11개, 특징 이름 101자, 요일 특징 이름 101자
            body.replace("}]}", "}],\"features\":[${(1..11).joinToString(",") { "{\"name\":\"특징$it\",\"values\":[]}" }}]}"),
            body.replace("}]}", "}],\"features\":[{\"name\":\"${"가".repeat(101)}\",\"values\":[]}]}"),
            body.replace("\"missionId\":\"$mission\"", "\"missionId\":\"$mission\",\"clueFeature\":\"${"가".repeat(101)}\""),
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
