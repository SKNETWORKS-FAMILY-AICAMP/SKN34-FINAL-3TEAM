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
import com.sagomungchi.learning.judgment.domain.ElementSource
import com.sagomungchi.learning.judgment.domain.ElementView
import com.sagomungchi.learning.judgment.domain.FeedbackResult
import com.sagomungchi.learning.judgment.domain.FollowupSource
import com.sagomungchi.learning.judgment.domain.FollowupType
import com.sagomungchi.learning.judgment.domain.FollowupView
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.judgment.domain.JudgmentView
import com.sagomungchi.learning.judgment.domain.NextAction
import com.sagomungchi.learning.judgment.domain.ProcessStatus
import com.sagomungchi.learning.judgment.domain.TimelineAnswer
import com.sagomungchi.learning.judgment.domain.Versions
import com.sagomungchi.learning.mission.domain.InputType
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

    private fun detail(
        draft: AttemptDraft = AttemptDraft.empty(attempt.id, now),
        answers: List<TimelineAnswer> = emptyList(),
        feedbacks: Map<UUID, FeedbackResult> = answers.associate { it.answerId to FeedbackResult.inProgress(it.processStatus) },
    ) = AttemptDetail(attempt, mission, draft, helped = false, answers = answers, feedbacks = feedbacks)

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
    fun `시도 상세는 ETag와 저장된 초안, 제출 답변과 판정 처리 상태`() {
        val saved = AttemptDraft.empty(attempt.id, now).update(DraftContent(mapOf("text" to "답"), "메모"), now)
        val answer = TimelineAnswer(
            UUID.randomUUID(), 1, now, InputType.NARRATIVE, "제출한 답", null, null, mapOf("text" to "제출한 답"), ProcessStatus.PENDING,
        )
        given(service.get(attempt.id)).willReturn(detail(saved, listOf(answer)))

        mockMvc.get("/internal/attempts/${attempt.id}") { asStudent() }.andExpect {
            status { isOk() }
            header { string("ETag", "\"1\"") }
            jsonPath("$.draft.content.answer.text") { value("답") }
            jsonPath("$.draft.content.memo") { value("메모") }
            jsonPath("$.draft.savedAt") { value("2026-10-27T01:00:00Z") }
            jsonPath("$.answers[0].answerId") { value(answer.answerId.toString()) }
            jsonPath("$.answers[0].version") { value(1) }
            jsonPath("$.answers[0].text") { value("제출한 답") }
            jsonPath("$.answers[0].content.text") { value("제출한 답") }
            jsonPath("$.answers[0].followupId") { value(null) }
            jsonPath("$.answers[0].feedback.status") { value("PENDING") }
            jsonPath("$.nextActions.length()") { value(0) }
        }
    }

    @Test
    fun `판정이 끝난 답변은 판정·되묻기와 다음 행동, 시도의 다음 행동은 마지막 답변 기준`() {
        val answer = TimelineAnswer(UUID.randomUUID(), 1, now, InputType.NARRATIVE, "답", null, null, mapOf("text" to "답"), ProcessStatus.DONE)
        val elementId = UUID.randomUUID()
        val followupId = UUID.randomUUID()
        val done = FeedbackResult(
            status = ProcessStatus.DONE,
            judgment = JudgmentView(JudgmentResult.PARTIAL, true, listOf(ElementView(elementId, "주장", true, "답", ElementSource.AI_OBSERVATION)), null),
            followup = FollowupView(followupId, FollowupType.TELL_MORE, "왜 그렇게 생각했나요?", FollowupSource.LLM),
            nextActions = listOf(NextAction.ANSWER_FOLLOWUP, NextAction.FINISH),
            versions = Versions("M@1", "M@1", "gpt", "judge@2"),
        )
        given(service.get(attempt.id)).willReturn(detail(answers = listOf(answer), feedbacks = mapOf(answer.answerId to done)))

        mockMvc.get("/internal/attempts/${attempt.id}") { asStudent() }.andExpect {
            status { isOk() }
            jsonPath("$.answers[0].feedback.judgment.result") { value("PARTIAL") }
            jsonPath("$.answers[0].feedback.judgment.elements[0].elementId") { value(elementId.toString()) }
            jsonPath("$.answers[0].feedback.judgment.elements[0].sourceType") { value("AI_OBSERVATION") }
            jsonPath("$.answers[0].feedback.followup.followupId") { value(followupId.toString()) }
            jsonPath("$.answers[0].feedback.versions.prompt") { value("judge@2") }
            jsonPath("$.nextActions[0]") { value("ANSWER_FOLLOWUP") }
            jsonPath("$.nextActions[1]") { value("FINISH") }
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
