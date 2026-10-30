package com.sagomungchi.learning.judgment.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.judgment.domain.CorrectionCommand
import com.sagomungchi.learning.judgment.domain.JudgmentCorrection
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.judgment.service.JudgmentService
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestHeader
import org.springframework.web.bind.annotation.RestController
import java.time.Instant
import java.util.UUID

/** 정정 요청 (api-spec 4.1). reportId는 core error_report ID */
data class CorrectionRequest(
    val reportId: UUID,
    val reason: String,
    val corrected: JudgmentResult,
)

/**
 * 파생 결과 반영 확인 (core #46 계약). learning 수치 집계는 판정 결과를 쓰지 않아 바꿀 것이 없으므로 NOT_APPLIED,
 * 대화(ai)·리포트(report)는 learning이 확인할 수 없어 UNKNOWN
 */
data class CorrectionImpact(
    val conversation: String = "UNKNOWN",
    val aggregation: String = "NOT_APPLIED",
    val report: String = "UNKNOWN",
)

/** 200 응답 (api-spec 4.1). 같은 키 재요청이면 저장된 행으로 처음 응답을 그대로 */
data class CorrectionResponse(
    val correctionId: UUID,
    val previousResult: JudgmentResult,
    val corrected: JudgmentResult,
    val createdAt: Instant,
    val impact: CorrectionImpact = CorrectionImpact(),
) {
    companion object {
        fun from(correction: JudgmentCorrection) =
            CorrectionResponse(correction.id, correction.previous, correction.corrected, correction.createdAt)
    }
}

/** 신고 정정 내부 API (api-spec 4.1, FN-SUP-03). core #46 관리자 정정이 호출 */
@RestController
class CorrectionController(
    private val judgmentService: JudgmentService,
) {
    /** 관리자(ADMIN)이고 범위에 판정 학생 1명만. 정정한 관리자 ID(X-User-Id)와 Idempotency-Key는 UUID */
    @PostMapping("/internal/judgments/{judgmentId}/corrections")
    fun correct(
        @PathVariable judgmentId: UUID,
        @RequestHeader(IDEMPOTENCY_KEY) idempotencyKey: String,
        @RequestBody request: CorrectionRequest,
    ): CorrectionResponse {
        val context = UserContextHolder.current()
        if (context.role != ADMIN_ROLE || context.studentScope.size != 1) {
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "정정 권한이 없습니다.")
        }
        val admin = uuid(context.userId, "X-User-Id는 UUID여야 함")
        val key = uuid(idempotencyKey, "Idempotency-Key는 UUID여야 함")
        if (request.reason.isBlank()) invalid("reason은 비울 수 없음")
        val command = CorrectionCommand(request.reportId, request.reason, request.corrected, admin)
        return CorrectionResponse.from(judgmentService.correct(judgmentId, command, key))
    }

    private fun uuid(value: String?, detail: String): UUID =
        value?.let { runCatching { UUID.fromString(it) }.getOrNull() } ?: invalid(detail)

    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", detail)

    companion object {
        const val IDEMPOTENCY_KEY = "Idempotency-Key"
        private const val ADMIN_ROLE = "ADMIN"
    }
}
