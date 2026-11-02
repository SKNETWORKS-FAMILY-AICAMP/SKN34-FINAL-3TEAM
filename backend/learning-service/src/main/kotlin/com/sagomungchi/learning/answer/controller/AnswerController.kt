package com.sagomungchi.learning.answer.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.Answer
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.domain.Assignment
import com.sagomungchi.learning.answer.domain.Essay
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.mission.domain.InputType
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestHeader
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.ResponseStatus
import org.springframework.web.bind.annotation.RestController
import java.time.Instant
import java.util.UUID

/** 답변 제출 요청 (api-spec 3.1·3.8). 메모는 받지 않음 (P05) */
data class SubmitRequest(
    val inputType: InputType,
    val text: String? = null,
    val finalAnswer: String? = null,
    val steps: List<String>? = null,
    val essay: Essay? = null,
    val choiceIds: List<String>? = null,
    val assignments: List<Assignment>? = null,
    val dictatedByGuardian: Boolean = false,
    val followupId: UUID? = null,
) {
    fun toCommand() = SubmitCommand(
        inputType = inputType,
        content = AnswerContent(text, finalAnswer, steps, essay, choiceIds, assignments),
        dictatedByGuardian = dictatedByGuardian,
        followupId = followupId,
    )
}

/** 201 응답 (api-spec 3.1). 판정은 피드백 요청 전이라 PENDING */
data class AnswerCreated(
    val answerId: UUID,
    val attemptId: UUID,
    val version: Int,
    val followupId: UUID?,
    val submittedAt: Instant,
    val feedback: Map<String, String>,
) {
    companion object {
        fun from(answer: Answer) = AnswerCreated(
            answerId = answer.id,
            attemptId = answer.attemptId,
            version = answer.version,
            followupId = answer.followupId,
            submittedAt = answer.submittedAt,
            feedback = mapOf("status" to "PENDING"),
        )
    }
}

@RestController
@RequestMapping("/internal/attempts/{attemptId}/answers")
class AnswerController(
    private val answerService: AnswerService,
) {
    /** 같은 Idempotency-Key 재요청은 최초 결과를 그대로 201로 (api-spec 1.4) */
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    fun submit(
        @PathVariable attemptId: UUID,
        @RequestHeader(IDEMPOTENCY_KEY) idempotencyKey: String,
        @RequestBody request: SubmitRequest,
    ): AnswerCreated {
        UserContextHolder.current().requireSelfStudent()
        val key = runCatching { UUID.fromString(idempotencyKey) }.getOrNull()
            ?: throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "Idempotency-Key는 UUID여야 함")
        return AnswerCreated.from(answerService.submit(attemptId, key, request.toCommand()))
    }

    companion object {
        const val IDEMPOTENCY_KEY = "Idempotency-Key"
    }
}
