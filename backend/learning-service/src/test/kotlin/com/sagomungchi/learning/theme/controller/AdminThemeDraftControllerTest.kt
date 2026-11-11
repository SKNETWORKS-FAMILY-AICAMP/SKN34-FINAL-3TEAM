package com.sagomungchi.learning.theme.controller

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.DomainException
import com.sagomungchi.learning._common.exception.ErrorKind
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.DraftVersions
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.theme.ThemeDraftFixtures
import com.sagomungchi.learning.theme.domain.AdminThemeDay
import com.sagomungchi.learning.theme.domain.AdminWeeklyTheme
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDraft
import com.sagomungchi.learning.theme.domain.ThemeDraftContent
import com.sagomungchi.learning.theme.domain.ThemeDraftScene
import com.sagomungchi.learning.theme.domain.ThemeDraftSource
import com.sagomungchi.learning.theme.domain.ThemeDraftView
import com.sagomungchi.learning.theme.domain.ThemeDraftViewPage
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeMissionInput
import com.sagomungchi.learning.theme.domain.WeeklyThemeStatus
import com.sagomungchi.learning.theme.service.ThemeDraftCommand
import com.sagomungchi.learning.theme.service.ThemeDraftService
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.BDDMockito.willThrow
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
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

/** 테마 초안 내부 API (api-spec 4.1, #438): core 프록시 조건(ADMIN·X-User-Id·JSON 객체 본문), 경로 6개와 응답 모양 */
@WebMvcTest(AdminThemeDraftController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(properties = ["app.internal.token=test-token", "app.internal.connect-timeout=1s", "app.internal.read-timeout=1s"])
class AdminThemeDraftControllerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var service: ThemeDraftService

    private val admin = UUID.randomUUID()
    private val now = Instant.parse("2026-11-11T00:00:00Z")
    private val week = LocalDate.of(2026, 11, 16)
    private val input = ThemeDraftFixtures.input()
    private val draft = ThemeDraft.requested(UUID.randomUUID(), ThemeGrade.G5, week, ThemeDraftSource.ADMIN, admin, input, now)
    private val output = ThemeDraftFixtures.output(input)
    private val view = ThemeDraftView(
        draft.id, DraftStatus.READY, ThemeDraftSource.ADMIN, ThemeGrade.G5, week, 1, 3, input, emptyList(),
        ThemeDraftContent(output.theme, output.missions, output.dialogues, output.warnings),
        listOf(ThemeDraftScene("INTRO", "https://assets/intro.png?sig", null, mapOf("zoom" to 1.1))),
        null, DraftVersions("theme-draft@1", "m"), null, admin, now, now,
    )
    private val body = """{"grade":"G5","weekStart":"2026-11-16","topic":"도서관",
        "missions":[{"thinkingType":"EVALUATE","standardCodes":["6국01-02"],"inputType":"ESSAY"}]}"""

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
    fun `초안 요청은 202와 ThemeDraft, 요청한 관리자는 X-User-Id, 미션은 고른 유형만 넘김`() {
        val command = ThemeDraftCommand(admin, ThemeGrade.G5, week, "도서관",
            listOf(ThemeMissionInput(ThinkingType.EVALUATE, InputType.ESSAY, listOf("6국01-02"))))
        given(service.request(command)).willReturn(draft)
        given(service.view(draft)).willReturn(view)

        mockMvc.post("/internal/admin/theme-drafts") { asAdmin(content = body) }.andExpect {
            status { isAccepted() }
            jsonPath("$.draftId") { value(draft.id.toString()) }
            jsonPath("$.status") { value("READY") }
            jsonPath("$.source") { value("ADMIN") }
            jsonPath("$.grade") { value("G5") }
            jsonPath("$.weekStart") { value("2026-11-16") }
            jsonPath("$.maxAttempts") { value(3) }
            jsonPath("$.input.missions.length()") { value(5) }
            jsonPath("$.input.missions[1].thinkingType") { value("EVALUATE") }
            jsonPath("$.draft.theme.answer") { value(ThemeDraftFixtures.ANSWER) }
            jsonPath("$.draft.missions[0].day") { value("MON") }
            jsonPath("$.draft.dialogues[0].lines[0].speaker") { value("뭉치") }
            jsonPath("$.draft.warnings[0].stage") { value("REVIEW") }
            jsonPath("$.draft.images") { doesNotExist() }
            jsonPath("$.scenes[0].scene") { value("INTRO") }
            jsonPath("$.scenes[0].imageUrl") { value("https://assets/intro.png?sig") }
            jsonPath("$.scenes[0].motion.zoom") { value(1.1) }
            jsonPath("$.themeId") { value(null as Any?) }
            jsonPath("$.requestedBy") { value(admin.toString()) }
        }
        // 미션을 고르지 않아도 됨
        given(service.request(command.copy(topic = null, missions = emptyList()))).willReturn(draft)
        mockMvc.post("/internal/admin/theme-drafts") { asAdmin(content = """{"grade":"G5","weekStart":"2026-11-16"}""") }.andExpect {
            status { isAccepted() }
        }
    }

    @Test
    fun `목록은 상태·출처 필터와 봉투, 상세는 ThemeDraft`() {
        given(service.list(DraftStatus.READY, ThemeDraftSource.AUTO, 1, 5)).willReturn(ThemeDraftViewPage(listOf(view), 1, 5, 6))
        given(service.get(draft.id)).willReturn(draft)
        given(service.view(draft)).willReturn(view)

        mockMvc.get("/internal/admin/theme-drafts?status=READY&source=AUTO&page=1&size=5") { asAdmin() }.andExpect {
            status { isOk() }
            jsonPath("$.items[0].draftId") { value(draft.id.toString()) }
            jsonPath("$.totalElements") { value(6) }
        }
        mockMvc.get("/internal/admin/theme-drafts/${draft.id}") { asAdmin() }.andExpect {
            status { isOk() }
            jsonPath("$.checkResults") { isEmpty() }
        }
    }

    @Test
    fun `채택은 201과 만든 테마, 버리기는 ThemeDraft, 다시 생성은 202와 새 초안, 상태 충돌은 409`() {
        val themeId = UUID.randomUUID()
        given(service.adopt(draft.id, admin)).willReturn(
            AdminWeeklyTheme(themeId, ThemeGrade.G5, week, WeeklyThemeStatus.DRAFT, 1, null, false, "사라진 강아지", "소개",
                listOf(AdminThemeDay(ThemeDay.MON, UUID.randomUUID())), null, now, now),
        )
        mockMvc.post("/internal/admin/theme-drafts/${draft.id}/adopt") { asAdmin(content = "{}") }.andExpect {
            status { isCreated() }
            jsonPath("$.themeId") { value(themeId.toString()) }
            jsonPath("$.status") { value("DRAFT") }
        }

        given(service.discard(draft.id)).willReturn(draft)
        given(service.view(draft)).willReturn(view)
        mockMvc.post("/internal/admin/theme-drafts/${draft.id}/discard") { asAdmin(content = "{}") }.andExpect { status { isOk() } }

        val copy = ThemeDraft.requested(UUID.randomUUID(), ThemeGrade.G5, week, ThemeDraftSource.ADMIN, admin, input, now)
        given(service.regenerate(draft.id, admin)).willReturn(copy)
        given(service.view(copy)).willReturn(view.copy(draftId = copy.id, status = DraftStatus.GENERATING))
        mockMvc.post("/internal/admin/theme-drafts/${draft.id}/regenerate") { asAdmin(content = "{}") }.andExpect {
            status { isAccepted() }
            jsonPath("$.draftId") { value(copy.id.toString()) }
            jsonPath("$.status") { value("GENERATING") }
        }

        willThrow(DomainException(ErrorKind.CONFLICT, "CONFLICT", "초안 상태 충돌")).given(service).regenerate(copy.id, admin)
        mockMvc.post("/internal/admin/theme-drafts/${copy.id}/regenerate") { asAdmin(content = "{}") }.andExpect {
            status { isConflict() }
            jsonPath("$.code") { value("CONFLICT") }
        }
    }

    @Test
    fun `관리자가 아니거나 X-User-Id가 UUID가 아니면 거절, 필수 칸·값이 틀리면 400이고 서비스를 부르지 않음`() {
        mockMvc.get("/internal/admin/theme-drafts") { asAdmin(role = "STUDENT") }.andExpect { status { isForbidden() } }
        mockMvc.post("/internal/admin/theme-drafts") { asAdmin(userId = "admin", content = body) }.andExpect { status { isBadRequest() } }
        listOf(
            body.replace(""""grade":"G5",""", ""),
            body.replace(""""weekStart":"2026-11-16",""", ""),
            body.replace("\"G5\"", "\"G5_6\""),
            body.replace(""""inputType":"ESSAY"""", """"inputType":"DRAWING""""),
            body.replace(""""standardCodes":["6국01-02"],""", ""),
        ).forEach { content ->
            mockMvc.post("/internal/admin/theme-drafts") { asAdmin(content = content) }.andExpect {
                status { isBadRequest() }
                jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
        mockMvc.get("/internal/admin/theme-drafts?size=101") { asAdmin() }.andExpect { status { isBadRequest() } }
        mockMvc.get("/internal/admin/theme-drafts?source=MANUAL") { asAdmin() }.andExpect { status { isBadRequest() } }
        verifyNoInteractions(service)
    }
}
