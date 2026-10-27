package com.sagomungchi.learning.judgment.controller

import com.sagomungchi.learning._common.config.AppProperties
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
import com.sagomungchi.learning.judgment.domain.Versions
import com.sagomungchi.learning.judgment.facade.AiUnavailableException
import com.sagomungchi.learning.judgment.facade.FeedbackFacade
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
import org.springframework.test.web.servlet.post
import java.util.UUID

@WebMvcTest(FeedbackController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(
    properties = [
        "app.internal.token=test-token",
        "app.internal.connect-timeout=1s",
        "app.internal.read-timeout=1s",
    ],
)
class FeedbackControllerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var facade: FeedbackFacade

    private val student = UUID.randomUUID()
    private val answerId = UUID.randomUUID()

    private fun MockHttpServletRequestDsl.asStudent(role: String = "STUDENT") {
        header("X-Internal-Token", "test-token")
        header("X-User-Role", role)
        header("X-Student-Scope", student.toString())
    }

    @Test
    fun `판정이 끝나면 판정·요소·되묻기·다음 행동·버전 (api-spec 3·2)`() {
        val elementId = UUID.randomUUID()
        val followupId = UUID.randomUUID()
        given(facade.feedback(answerId)).willReturn(
            FeedbackResult(
                status = ProcessStatus.DONE,
                judgment = JudgmentView(JudgmentResult.HELD, true, emptyList(), "TOO_SHORT"),
                followup = FollowupView(followupId, FollowupType.TELL_MORE, "조금 더 말해 줄래요?", FollowupSource.BANK),
                nextActions = listOf(NextAction.ANSWER_FOLLOWUP, NextAction.FINISH),
                versions = Versions("DEMO-01@1", "DEMO-01@1", "gpt", "judge@2"),
            ),
        )

        mockMvc.post("/internal/answers/$answerId/feedback") { asStudent() }.andExpect {
            status { isOk() }
            jsonPath("$.status") { value("DONE") }
            jsonPath("$.judgment.result") { value("HELD") }
            jsonPath("$.judgment.heldReason") { value("TOO_SHORT") }
            jsonPath("$.judgment.trial") { value(true) }
            jsonPath("$.followup.followupId") { value(followupId.toString()) }
            jsonPath("$.followup.source") { value("BANK") }
            jsonPath("$.nextActions[0]") { value("ANSWER_FOLLOWUP") }
            jsonPath("$.versions.mission") { value("DEMO-01@1") }
        }

        given(facade.feedback(answerId)).willReturn(
            FeedbackResult(
                ProcessStatus.DONE,
                JudgmentView(JudgmentResult.CORRECT, false, listOf(ElementView(elementId, "원인", true, "물", ElementSource.ANSWER_KEY)), null),
                null,
                listOf(NextAction.FINISH),
                Versions("DEMO-01@1", "DEMO-01@1", null, null),
            ),
        )
        mockMvc.post("/internal/answers/$answerId/feedback") { asStudent() }.andExpect {
            jsonPath("$.judgment.elements[0].sourceType") { value("ANSWER_KEY") }
            jsonPath("$.followup") { value(null) }
            jsonPath("$.versions.model") { value(null) }
        }
    }

    @Test
    fun `다른 요청이 처리 중이면 200 status RUNNING`() {
        given(facade.feedback(answerId)).willReturn(FeedbackResult.inProgress(ProcessStatus.RUNNING))

        mockMvc.post("/internal/answers/$answerId/feedback") { asStudent() }.andExpect {
            status { isOk() }
            jsonPath("$.status") { value("RUNNING") }
            jsonPath("$.nextActions.length()") { value(0) }
        }
    }

    @Test
    fun `ai 실패는 503 AI_UNAVAILABLE과 retryable`() {
        given(facade.feedback(answerId)).willThrow(AiUnavailableException(retryable = true))

        mockMvc.post("/internal/answers/$answerId/feedback") { asStudent() }.andExpect {
            status { isServiceUnavailable() }
            jsonPath("$.code") { value("AI_UNAVAILABLE") }
            jsonPath("$.retryable") { value(true) }
        }
    }

    @Test
    fun `answerId가 UUID 형식이 아니면 400`() {
        mockMvc.post("/internal/answers/not-a-uuid/feedback") { asStudent() }.andExpect {
            status { isBadRequest() }
            jsonPath("$.code") { value("VALIDATION_FAILED") }
        }
        verifyNoInteractions(facade)
    }

    @Test
    fun `학생이 아니면 403`() {
        mockMvc.post("/internal/answers/$answerId/feedback") { asStudent(role = "PARENT") }.andExpect {
            status { isForbidden() }
        }
        verifyNoInteractions(facade)
    }
}
