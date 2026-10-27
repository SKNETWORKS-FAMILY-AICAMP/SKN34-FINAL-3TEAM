package com.sagomungchi.learning.attempt.controller

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.domain.AttemptDraft
import com.sagomungchi.learning.attempt.domain.DraftContent
import com.sagomungchi.learning.attempt.domain.HintOpened
import com.sagomungchi.learning.attempt.service.AttemptDetail
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.attempt.service.AttemptStart
import com.sagomungchi.learning.attempt.service.DraftConflictException
import com.sagomungchi.learning.mission.domain.HintQuestion
import com.sagomungchi.learning.mission.domain.MissionSnapshot
import com.sagomungchi.learning.mission.missionView
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.Mockito.verify
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.http.MediaType
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import org.springframework.test.web.servlet.put
import java.time.Instant
import java.util.UUID

@WebMvcTest(AttemptController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(
    properties = [
        "app.internal.token=test-token",
        "app.internal.connect-timeout=1s",
        "app.internal.read-timeout=1s",
    ],
)
class AttemptControllerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var service: AttemptService

    private val student = UUID.randomUUID()
    private val mission = missionView(grade = 3)
    private val now = Instant.parse("2026-10-27T01:00:00Z")
    private val attempt = Attempt.start(student, mission.id, MissionSnapshot(UUID.randomUUID(), UUID.randomUUID()), 3, now)

    private fun detail(draft: AttemptDraft = AttemptDraft.empty(attempt.id, now)) =
        AttemptDetail(attempt, mission, draft, helped = false)

    private fun MockHttpServletRequestDsl.asStudent(role: String = "STUDENT") {
        header("X-Internal-Token", "test-token")
        header("X-User-Role", role)
        header("X-Student-Scope", student.toString())
    }

    @Test
    fun `새 시도는 201, 진행 중 시도는 200이고 초안 버전을 ETag로`() {
        given(service.start(student, mission.id, 3, false)).willReturn(AttemptStart(attempt, created = true))
        given(service.get(attempt.id)).willReturn(detail())

        mockMvc.post("/internal/missions/${mission.id}/attempts?grade=3") { asStudent() }.andExpect {
            status { isCreated() }
            header { string("ETag", "\"0\"") }
            jsonPath("$.attemptId") { value(attempt.id.toString()) }
            jsonPath("$.mission.id") { value(mission.id.toString()) }
            jsonPath("$.status") { value("IN_PROGRESS") }
            jsonPath("$.answers.length()") { value(0) }
            jsonPath("$.draft.version") { value(0) }
            jsonPath("$.draft.savedAt") { value(null) }
            jsonPath("$.helped") { value(false) }
        }

        given(service.start(student, mission.id, 3, true)).willReturn(AttemptStart(attempt, created = false))
        mockMvc.post("/internal/missions/${mission.id}/attempts?grade=3&demo=true") { asStudent() }.andExpect {
            status { isOk() }
        }
    }

    @Test
    fun `시도 상세는 ETag와 저장된 초안`() {
        val saved = AttemptDraft.empty(attempt.id, now).update(DraftContent(mapOf("text" to "답"), "메모"), now)
        given(service.get(attempt.id)).willReturn(detail(saved))

        mockMvc.get("/internal/attempts/${attempt.id}") { asStudent() }.andExpect {
            status { isOk() }
            header { string("ETag", "\"1\"") }
            jsonPath("$.draft.content.answer.text") { value("답") }
            jsonPath("$.draft.content.memo") { value("메모") }
            jsonPath("$.draft.savedAt") { value("2026-10-27T01:00:00Z") }
        }
    }

    @Test
    fun `초안 저장은 If-Match 버전을 넘기고 새 ETag`() {
        val draftContent = DraftContent(mapOf("text" to "답"), "메모")
        given(service.saveDraft(attempt.id, 3, draftContent))
            .willReturn(AttemptDraft(attempt.id, 4, draftContent, now))

        listOf("\"3\"", "3", "W/\"3\"").forEach { ifMatch ->
            mockMvc.put("/internal/attempts/${attempt.id}/draft") {
                asStudent()
                header("If-Match", ifMatch)
                contentType = MediaType.APPLICATION_JSON
                content = """{"content":{"answer":{"text":"답"},"memo":"메모"}}"""
            }.andExpect {
                status { isOk() }
                header { string("ETag", "\"4\"") }
                jsonPath("$.version") { value(4) }
            }
        }
    }

    @Test
    fun `If-Match가 없거나 버전이 아니면 400`() {
        listOf(null, "\"abc\"", "-1").forEach { ifMatch ->
            mockMvc.put("/internal/attempts/${attempt.id}/draft") {
                asStudent()
                ifMatch?.let { header("If-Match", it) }
                contentType = MediaType.APPLICATION_JSON
                content = """{"content":{"answer":{},"memo":""}}"""
            }.andExpect {
                status { isBadRequest() }
                jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
    }

    @Test
    fun `초안 충돌은 409와 최신 초안 (api-spec 3·6)`() {
        val mine = DraftContent(mapOf("text" to "다른 화면"), "")
        val latest = AttemptDraft(attempt.id, 8, DraftContent(mapOf("text" to "최신"), "메모"), now)
        given(service.saveDraft(attempt.id, 7, mine)).willThrow(DraftConflictException(latest))

        mockMvc.put("/internal/attempts/${attempt.id}/draft") {
            asStudent()
            header("If-Match", "\"7\"")
            contentType = MediaType.APPLICATION_JSON
            content = """{"content":{"answer":{"text":"다른 화면"},"memo":""}}"""
        }.andExpect {
            status { isConflict() }
            header { string("ETag", "\"8\"") }
            jsonPath("$.code") { value("ATTEMPT_DRAFT_CONFLICT") }
            jsonPath("$.latest.version") { value(8) }
            jsonPath("$.latest.content.answer.text") { value("최신") }
            jsonPath("$.latest.savedAt") { exists() }
        }
    }

    @Test
    fun `생각 열기는 질문과 순서`() {
        val question = HintQuestion(UUID.randomUUID(), 2, "둘째 질문")
        given(service.openHint(attempt.id)).willReturn(HintOpened(question, total = 2))

        mockMvc.post("/internal/attempts/${attempt.id}/hints") { asStudent() }.andExpect {
            status { isOk() }
            jsonPath("$.question") { value("둘째 질문") }
            jsonPath("$.seq") { value(2) }
            jsonPath("$.total") { value(2) }
        }
        verify(service).openHint(attempt.id)
    }

    @Test
    fun `학생이 아니면 403`() {
        mockMvc.get("/internal/attempts/${attempt.id}") { asStudent(role = "PARENT") }.andExpect {
            status { isForbidden() }
            jsonPath("$.code") { value("FORBIDDEN") }
        }
        mockMvc.post("/internal/missions/${mission.id}/attempts?grade=3") { asStudent(role = "PARENT") }.andExpect {
            status { isForbidden() }
        }
    }
}
