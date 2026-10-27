package com.sagomungchi.learning.judgment.controller

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
 * DONE이면 판정·되묻기·다음 행동·버전, 다른 요청이 처리 중이면 200 `{status:"RUNNING"}`
 */
@RestController
class FeedbackController(
    private val feedbackFacade: FeedbackFacade,
) {
    @PostMapping("/internal/answers/{answerId}/feedback")
    fun feedback(@PathVariable answerId: UUID): FeedbackResult {
        UserContextHolder.current().requireSelfStudent()
        return feedbackFacade.feedback(answerId)
    }

    /** api-spec 3.2 `{"code":"AI_UNAVAILABLE","retryable":true}` */
    @ExceptionHandler(AiUnavailableException::class)
    fun unavailable(error: AiUnavailableException, request: HttpServletRequest): ProblemDetail =
        Problems.of(error.status, error.code, error.title, error.detail, request).apply { setProperty("retryable", error.retryable) }
}
