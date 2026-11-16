package com.sagomungchi.learning.judgment.controller

import com.sagomungchi.learning._common.web.FeedbackResponse
import com.sagomungchi.learning._common.web.JudgmentResponse
import com.sagomungchi.learning._common.web.ElementResponse
import com.sagomungchi.learning._common.web.FollowupResponse
import com.sagomungchi.learning._common.web.FeedbackVersions

import com.sagomungchi.learning._common.exception.Problems
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.judgment.domain.FeedbackResult
import com.sagomungchi.learning.judgment.facade.AiUnavailableException
import com.sagomungchi.learning.judgment.facade.FeedbackFacade
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.ProblemDetail
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RestController
import java.util.UUID

/**
 * 피드백 내부 API (api-spec 4.1). core가 SSE로 바꿔 학생에게 전달 (sequence-diagram 3.2).
 * DONE이면 판정·되묻기·다음 행동·버전, 다른 요청이 처리 중이면 200 `{status:"RUNNING", nextActions:[]}`(나머지 null)
 */
@RestController
class FeedbackController(
    private val feedbackFacade: FeedbackFacade,
) {
    @PostMapping("/internal/answers/{answerId}/feedback")
    fun feedback(@PathVariable answerId: UUID): FeedbackResponse {
        UserContextHolder.current().requireSelfStudent()
        return feedbackFacade.feedback(answerId).toResponse()
    }

    /** api-spec 3.2 `{"code":"AI_UNAVAILABLE","retryable":true}` */
    @ExceptionHandler(AiUnavailableException::class)
    fun unavailable(error: AiUnavailableException, request: HttpServletRequest): ProblemDetail =
        Problems.of(error.status, error.code, error.title, error.detail, request).apply { setProperty("retryable", error.retryable) }
}

internal fun FeedbackResult.toResponse() = FeedbackResponse(
    status.name,
    judgment?.let { j -> JudgmentResponse(
        j.judgmentId, j.result.name, j.trial,
        j.elements.map { e -> ElementResponse(
            e.elementId, e.label, e.code, e.goodThought, e.satisfied, e.quote, e.sourceType?.name,
        ) }, j.heldReason, j.corrected, j.modelScores, j.m2Notices,
    ) },
    followup?.let { FollowupResponse(it.followupId, it.type.name, it.question, it.source.name) },
    nextActions.map { it.name },
    versions?.let { FeedbackVersions(it.mission, it.rubric, it.model, it.prompt) },
)
