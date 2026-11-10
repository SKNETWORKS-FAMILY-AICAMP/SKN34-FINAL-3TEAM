package com.sagomungchi.learning.mission.controller

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.DomainException
import com.sagomungchi.learning._common.exception.ErrorKind
import com.sagomungchi.learning.mission.domain.AchievementStandard
import com.sagomungchi.learning.mission.domain.AdminMission
import com.sagomungchi.learning.mission.domain.DraftInput
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.DraftVersions
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionDraft
import com.sagomungchi.learning.mission.domain.MissionSource
import com.sagomungchi.learning.mission.domain.MissionStatus
import com.sagomungchi.learning.mission.domain.StandardFilter
import com.sagomungchi.learning.mission.domain.StandardPage
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.mission.service.DraftCommand
import com.sagomungchi.learning.mission.service.MissionDraftService
import com.sagomungchi.learning.mission.service.MissionService
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
import java.util.UUID

/** 성취기준 표·미션 초안 내부 API (api-spec 4.1, #353): core 프록시 조건(ADMIN·X-User-Id·JSON 객체)과 응답 모양 */
@WebMvcTest(AdminMissionDraftController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(properties = ["app.internal.token=test-token", "app.internal.connect-timeout=1s", "app.internal.read-timeout=1s"])
class AdminMissionDraftControllerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var drafts: MissionDraftService
    @MockitoBean lateinit var missions: MissionService

    private val admin = UUID.randomUUID()
    private val now = Instant.parse("2026-11-04T00:00:00Z")
    private val input = DraftInput(listOf("6국01-02"), mapOf("6국01-02" to "B"), ThinkingType.EVALUATE, 5, 6, InputType.NARRATIVE)
    private val draft = MissionDraft(UUID.randomUUID(), admin, input, DraftStatus.GENERATING, 0, emptyList(), null, null,
        DraftVersions(null, null), null, null, now, now)
    private val body = """{"standardCodes":["6국01-02"],"achievementLevels":{"6국01-02":"B"},"thinkingType":"EVALUATE","gradeMin":5,"gradeMax":6,"inputType":"NARRATIVE"}"""

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
    fun `초안 요청은 202와 MissionDraft, 요청한 관리자는 X-User-Id`() {
        given(drafts.request(DraftCommand(admin, input))).willReturn(draft)
        given(drafts.maxAttempts).willReturn(3)

        mockMvc.post("/internal/admin/mission-drafts") { asAdmin(content = body) }.andExpect {
            status { isAccepted() }
            jsonPath("$.draftId") { value(draft.id.toString()) }
            jsonPath("$.status") { value("GENERATING") }
            jsonPath("$.attempts") { value(0) }
            jsonPath("$.maxAttempts") { value(3) }
            jsonPath("$.input.achievementLevels.6국01-02") { value("B") }
            jsonPath("$.checkResults") { isEmpty() }
            jsonPath("$.draft") { value(null as Any?) }
            jsonPath("$.versions.prompt") { value(null as Any?) }
            jsonPath("$.requestedBy") { value(admin.toString()) }
        }
    }

    @Test
    fun `성취기준 조회는 필터를 넘기고 봉투, 학년군 값이 틀리면 400`() {
        val row = AchievementStandard("6국01-02", "국어", "초5~6", "듣기·말하기", "주장을 파악하며 듣는다.", 3, null, "2022 개정", "고시", null)
        given(drafts.standards(StandardFilter("국어", "초5~6", "주장", 0, 20))).willReturn(StandardPage(listOf(row), 0, 20, 1))

        mockMvc.get("/internal/admin/achievement-standards?subject=국어&gradeBand=초5~6&q=주장") { asAdmin() }.andExpect {
            status { isOk() }
            jsonPath("$.items[0].code") { value("6국01-02") }
            jsonPath("$.items[0].levelScale") { value(3) }
            jsonPath("$.items[0].levels") { value(null as Any?) }
            jsonPath("$.totalElements") { value(1) }
        }
        mockMvc.get("/internal/admin/achievement-standards?gradeBand=고1") { asAdmin() }.andExpect { status { isBadRequest() } }
    }

    @Test
    fun `채택은 201과 만든 미션 전체, 상태 충돌은 409`() {
        val missionId = UUID.randomUUID()
        given(drafts.adopt(draft.id, admin)).willReturn(missionId)
        given(missions.getForAdmin(missionId)).willReturn(
            AdminMission(missionId, "M-1", MissionStatus.DRAFT, false, 1, 1, null, null, emptyList(), emptyList(), emptyList(), MissionSource.LLM_DRAFT),
        )

        mockMvc.post("/internal/admin/mission-drafts/${draft.id}/adopt") { asAdmin(content = "{}") }.andExpect {
            status { isCreated() }
            jsonPath("$.missionId") { value(missionId.toString()) }
            jsonPath("$.source") { value("LLM_DRAFT") }
        }
        willThrow(DomainException(ErrorKind.CONFLICT, "CONFLICT", "초안 상태 충돌")).given(drafts).discard(draft.id)
        mockMvc.post("/internal/admin/mission-drafts/${draft.id}/discard") { asAdmin(content = "{}") }.andExpect {
            status { isConflict() }
            jsonPath("$.code") { value("CONFLICT") }
        }
    }

    @Test
    fun `관리자가 아니면 403, 필수 칸이 빠지면 400이고 서비스를 부르지 않음`() {
        mockMvc.get("/internal/admin/mission-drafts") { asAdmin(role = "STUDENT") }.andExpect { status { isForbidden() } }
        listOf(
            body.replace(""""standardCodes":["6국01-02"],""", ""),
            body.replace(""""gradeMin":5,""", ""),
            body.replace("\"NARRATIVE\"", "\"DRAWING\""),
        ).forEach { content ->
            mockMvc.post("/internal/admin/mission-drafts") { asAdmin(content = content) }.andExpect {
                status { isBadRequest() }
                jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
        mockMvc.get("/internal/admin/mission-drafts?size=101") { asAdmin() }.andExpect { status { isBadRequest() } }
        verifyNoInteractions(drafts)
    }
}
