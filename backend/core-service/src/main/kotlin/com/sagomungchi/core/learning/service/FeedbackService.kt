package com.sagomungchi.core.learning.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.exception.errorInfoOf
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.learning.client.FeedbackClient
import com.sagomungchi.core.learning.client.FeedbackOutcome
import org.springframework.http.HttpStatus
import java.util.UUID

/** 공개 피드백 SSE 이벤트 하나. [data]는 그대로 JSON으로 보낸다. */
data class FeedbackEvent(val name: String, val data: Any)

/**
 * Learning owns judgment state, leases and persistence. Every request reaches learning without a key/cache.
 * 어느 SSE 이벤트를 보낼지만 정한다(#834): `Done` → `result`, `Running` → 진행 중 `status`, `Failed`·업무 예외 → `error`.
 */
class FeedbackService(private val client: FeedbackClient) {
    fun started() = FeedbackEvent("status", RUNNING)

    /** 업무 예외(BusinessException·DomainException)는 `error` 이벤트로 바꾸고, 그 밖의 예외는 그대로 던진다. */
    fun feedback(answerId: UUID): FeedbackEvent = try {
        verifiedStudent()
        when (val outcome = client.feedback(answerId)) {
            is FeedbackOutcome.Done -> FeedbackEvent("result", outcome.document)
            FeedbackOutcome.Running -> started()
            is FeedbackOutcome.Failed -> FeedbackEvent("error", outcome.problem)
        }
    } catch (ex: RuntimeException) {
        val error = errorInfoOf(ex) ?: throw ex
        val status = error.status.value()
        FeedbackEvent("error", mapOf("type" to "about:blank", "title" to error.title, "status" to status,
            "code" to error.code, "retryable" to (status >= 500 || status == 429)))
    }

    private fun verifiedStudent() {
        if (UserContextHolder.currentOrNull()?.let { it.role == "STUDENT" && it.userId != null && it.studentScope.size == 1 } != true)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학생 세션이 필요합니다.")
    }

    private companion object {
        val RUNNING = mapOf("state" to "RUNNING", "message" to "생각을 살펴보는 중")
    }
}
