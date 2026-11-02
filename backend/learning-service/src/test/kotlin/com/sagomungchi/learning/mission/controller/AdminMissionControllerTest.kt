package com.sagomungchi.learning.mission.controller

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning.mission.domain.AdminMission
import com.sagomungchi.learning.mission.domain.AdminMissionFilter
import com.sagomungchi.learning.mission.domain.AdminMissionPage
import com.sagomungchi.learning.mission.domain.Choice
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.Mission
import com.sagomungchi.learning.mission.domain.MissionCommand
import com.sagomungchi.learning.mission.domain.MissionPublishIncompleteException
import com.sagomungchi.learning.mission.domain.MissionStatus
import com.sagomungchi.learning.mission.domain.ReviewResult
import com.sagomungchi.learning.mission.domain.StatusCount
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.mission.service.MissionService
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.BDDMockito.willThrow
import org.mockito.Mockito.verify
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
import java.util.UUID

/** 관리자 미션 내부 API (api-spec 4.1, #145): core 프록시 조건(ADMIN·X-User-Id·JSON 객체)과 오류 모양 */
@WebMvcTest(AdminMissionController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(properties = ["app.internal.token=test-token", "app.internal.connect-timeout=1s", "app.internal.read-timeout=1s"])
class AdminMissionControllerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var service: MissionService

    private val admin = UUID.randomUUID()
    private val missionId = UUID.randomUUID()
    private val mission = AdminMission(missionId, "M-1", MissionStatus.DRAFT, false, 1, null, null, null, emptyList(), emptyList(), emptyList())
    private val body = """{"title":"미션","subject":"과학","gradeMin":5,"gradeMax":5,"thinkingType":"ANALYZE","inputType":"CHOICE",
        "question":"질문","achievementStandards":["[6과07-02]"],"choices":[{"id":"c1","label":"물"}],"demoOnly":false}"""

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
    fun `작성은 201과 미션 전체, 작성자는 X-User-Id`() {
        val command = MissionCommand(admin, "미션", "과학", 5, 5, ThinkingType.ANALYZE, InputType.CHOICE, "질문", null, null, null,
            listOf("[6과07-02]"), listOf(Choice("c1", "물")), emptyList(), null, emptyList(), false)
        given(service.create(command)).willReturn(Mission(missionId, MissionStatus.DRAFT, 1, null, null, null))
        given(service.getForAdmin(missionId)).willReturn(mission)

        mockMvc.post("/internal/admin/missions") { asAdmin(content = body) }.andExpect {
            status { isCreated() }
            jsonPath("$.missionId") { value(missionId.toString()) }
            jsonPath("$.status") { value("DRAFT") }
            jsonPath("$.currentVersion") { value(1) }
            jsonPath("$.publishedVersion") { value(null) }
        }
    }

    @Test
    fun `목록은 필터를 넘기고 counts가 있는 봉투`() {
        val filter = AdminMissionFilter(MissionStatus.DRAFT, 3, ThinkingType.CREATE, 1, 10)
        given(service.listForAdmin(filter)).willReturn(AdminMissionPage(listOf(mission), 1, 10, 11, MissionStatus.entries.map { StatusCount(it, 1) }))

        mockMvc.get("/internal/admin/missions?status=DRAFT&grade=3&thinkingType=CREATE&page=1&size=10") { asAdmin() }.andExpect {
            status { isOk() }
            jsonPath("$.items[0].missionId") { value(missionId.toString()) }
            jsonPath("$.totalElements") { value(11) }
            jsonPath("$.counts.length()") { value(4) }
        }
    }

    @Test
    fun `게시 필수 누락은 422와 영문 missingFields, 게시·중단 본문은 빈 객체`() {
        willThrow(MissionPublishIncompleteException(listOf("rubric.elements", "review"))).given(service).publish(missionId)

        mockMvc.post("/internal/admin/missions/$missionId/publish") { asAdmin(content = "{}") }.andExpect {
            status { isUnprocessableEntity() }
            jsonPath("$.code") { value("MISSION_PUBLISH_INCOMPLETE") }
            jsonPath("$.missingFields[0]") { value("rubric.elements") }
            jsonPath("$.missingFields[1]") { value("review") }
        }
    }

    @Test
    fun `검토는 버전·결과를 넘기고 검토자는 X-User-Id`() {
        given(service.getForAdmin(missionId)).willReturn(mission)

        mockMvc.post("/internal/admin/missions/$missionId/review") {
            asAdmin(content = """{"missionVersion":2,"rubricVersion":1,"result":"APPROVED","comment":"좋아요"}""")
        }.andExpect { status { isOk() } }

        verify(service).review(missionId, admin, 2, 1, ReviewResult.APPROVED, "좋아요")
    }

    @Test
    fun `관리자가 아니면 403, X-User-Id가 없거나 UUID가 아니면 400`() {
        mockMvc.get("/internal/admin/missions") { asAdmin(role = "STUDENT") }.andExpect {
            status { isForbidden() }
            jsonPath("$.code") { value("FORBIDDEN") }
        }
        listOf(null, "admin").forEach { userId ->
            mockMvc.post("/internal/admin/missions") { asAdmin(userId = userId, content = body) }.andExpect {
                status { isBadRequest() }
                jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
        verifyNoInteractions(service)
    }

    @Test
    fun `필수 칸·형식이 틀리면 400`() {
        listOf(
            "/internal/admin/missions" to """{"subject":"과학","gradeMin":5,"gradeMax":5,"thinkingType":"ANALYZE","inputType":"CHOICE","question":"q","demoOnly":false}""",
            "/internal/admin/missions" to body.replace("\"CHOICE\"", "\"DRAWING\""),
            "/internal/admin/missions" to body.replace("""[{"id":"c1","label":"물"}]""", """[{"id":"c1","label":"물"},{"id":"c1","label":"불"}]"""),
            "/internal/admin/missions/$missionId/review-request" to """{"missionVersion":1}""",
        ).forEach { (path, content) ->
            mockMvc.post(path) { asAdmin(content = content) }.andExpect {
                status { isBadRequest() }
                jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
        listOf(
            """{"elements":[{"code":"e1","label":"요소","points":0}]}""",
            """{"elements":[{"code":"e1","label":" ","points":1}]}""",
            """{"elements":[{"code":"e1","label":"가","points":1},{"code":"e1","label":"나","points":1}]}""",
            """{"answerKey":"c1"}""",
        ).forEach { content ->
            mockMvc.put("/internal/admin/missions/$missionId/rubric") { asAdmin(content = content) }.andExpect {
                status { isBadRequest() }
                jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
        verifyNoInteractions(service)
    }
}
