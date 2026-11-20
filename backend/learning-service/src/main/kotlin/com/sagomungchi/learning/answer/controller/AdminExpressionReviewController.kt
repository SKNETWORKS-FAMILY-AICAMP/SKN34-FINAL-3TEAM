package com.sagomungchi.learning.answer.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.ExpressionReviewItem
import com.sagomungchi.learning.answer.domain.ExpressionReviewLabel
import com.sagomungchi.learning.answer.domain.ExpressionReviewPage
import com.sagomungchi.learning.answer.domain.ExpressionReviewSource
import com.sagomungchi.learning.answer.service.ExpressionReviewService
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PutMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import java.util.UUID

/** 라벨 저장 본문 */
data class ExpressionReviewLabelRequest(val label: String? = null)

/**
 * 표현 검토 대기 관리자 내부 API (FN-ADM-24, api-spec 4.1.5, #727). core(#728)가 SERVICE_OPS 권한·감사 기록을 처리하고
 * ADMIN + X-User-Id(라벨한 운영자) + 빈 학생 범위로 부름. 응답에 학생·답변 ID 없음
 */
@RestController
@RequestMapping("/internal/admin/expression-reviews")
class AdminExpressionReviewController(private val service: ExpressionReviewService) {
    @GetMapping
    fun list(
        @RequestParam(defaultValue = "false") labeled: Boolean,
        @RequestParam(required = false) source: String?,
        @RequestParam(defaultValue = "0") page: Int,
        @RequestParam(defaultValue = "20") size: Int,
    ): ExpressionReviewPage {
        requireAdmin()
        if (page < 0 || size !in 1..MAX_SIZE) invalid("page는 0 이상, size는 1~$MAX_SIZE")
        val parsed = source?.let { value -> ExpressionReviewSource.entries.firstOrNull { it.name == value } ?: invalid("source는 GRAY_ZONE·COMMUNITY_REPORT") }
        return service.list(labeled, parsed, page, size)
    }

    @PutMapping("/{reviewId}/label")
    fun label(@PathVariable reviewId: UUID, @RequestBody request: ExpressionReviewLabelRequest): ExpressionReviewItem {
        val operator = requireAdmin()
        val label = ExpressionReviewLabel.entries.firstOrNull { it.name == request.label } ?: invalid("label은 OFFENSIVE·CLEAN·SKIP")
        return service.label(reviewId, label, operator)
    }

    /** ADMIN만. 라벨한 사람으로 저장할 운영자 ID(X-User-Id)는 UUID */
    private fun requireAdmin(): UUID {
        val context = UserContextHolder.current()
        if (context.role != ADMIN_ROLE) throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "관리자 권한이 없습니다.")
        return context.userId?.let { runCatching { UUID.fromString(it) }.getOrNull() } ?: invalid("X-User-Id는 UUID여야 함")
    }

    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", detail)

    companion object {
        private const val ADMIN_ROLE = "ADMIN"
        private const val MAX_SIZE = 100
    }
}
