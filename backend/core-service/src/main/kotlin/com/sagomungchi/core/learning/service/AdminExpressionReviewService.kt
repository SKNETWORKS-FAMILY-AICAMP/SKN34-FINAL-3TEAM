package com.sagomungchi.core.learning.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.admin.service.ExpressionReviewAuditService
import com.sagomungchi.core.learning.client.LearningExpressionReviewClient
import com.sagomungchi.core.learning.domain.ExpressionReview
import com.sagomungchi.core.learning.domain.ExpressionReviewLabel
import com.sagomungchi.core.learning.domain.ExpressionReviewPage
import com.sagomungchi.core.learning.domain.ExpressionReviewSource
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

/**
 * 관리자 표현 검토 (FN-ADM-24, api-spec 2.8·4.1.5, #728·#907). learning 호출과 응답 해석은 [LearningExpressionReviewClient],
 * 감사는 [ExpressionReviewAuditService]. SERVICE_OPS 검사는 인증 필터(경로 기본값).
 * - 목록: client가 허용한 칸만 담은 항목을 받고, 보여 줄 항목 ID를 `EXPRESSION_REVIEW_VIEW`로 감사한 뒤 돌려준다.
 *   감사를 남기지 못하면 글을 돌려주지 않는다(P07)
 * - 라벨: `EXPRESSION_REVIEW_LABEL` 감사를 남긴 뒤 learning에 한 번 전달(api-spec 4.1.5). 감사를 남기지 못하면 전달하지 않는다.
 *   응답 모양 오류(502)와 결과 모름(503)에는 감사 ID(확인 번호)를 붙인다
 */
@Service
class AdminExpressionReviewService(private val client: LearningExpressionReviewClient,
                                   private val audits: ExpressionReviewAuditService) {
    fun list(labeled: Boolean, source: ExpressionReviewSource?, page: Int, size: Int): ExpressionReviewPage {
        val actor = actor()
        val found = client.list(labeled, source, page, size)
        try {
            audits.viewed(actor, found.items.map { it.id }, labeled, source?.name, page, size)
        } catch (_: RuntimeException) {
            throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "EXPRESSION_REVIEW_AUDIT_UNAVAILABLE", "열람 감사 기록을 남기지 못했습니다.")
        }
        return found
    }

    fun label(id: UUID, label: ExpressionReviewLabel): ExpressionReview {
        val actor = actor()
        val operation = UUID.randomUUID()
        try {
            audits.labeled(operation, actor, id, label.name)
        } catch (_: RuntimeException) { auditUnavailable(operation) }
        val saved = try {
            client.label(id, label)
        } catch (error: BusinessException) {
            when {
                error.status.is4xxClientError -> throw error // learning이 거절해 저장되지 않음
                error.status == HttpStatus.BAD_GATEWAY -> unconfirmed(operation, error.status, error.code)
                else -> unknown(operation)
            }
        } catch (_: RuntimeException) { unknown(operation) }
        if (saved.id != id || saved.label != label) unknown(operation)
        return saved
    }

    private fun actor(): UUID {
        val context = UserContextHolder.currentOrNull()
        return (if (context?.role == "ADMIN") runCatching { UUID.fromString(context.userId) }.getOrNull() else null)
            ?: throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 관리자 세션이 필요합니다.")
    }

    private fun unknown(operation: UUID): Nothing = unconfirmed(operation, HttpStatus.SERVICE_UNAVAILABLE, "LEARNING_UNAVAILABLE")
    private fun unconfirmed(operation: UUID, status: HttpStatus, code: String): Nothing = throw BusinessException(status, code,
        "라벨 저장 결과를 확인하지 못했습니다.", "확인 번호: $operation. 다시 보내기 전에 목록에서 라벨을 확인하세요.")
    private fun auditUnavailable(operation: UUID): Nothing = throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,
        "EXPRESSION_REVIEW_AUDIT_UNAVAILABLE", "감사 기록을 남기지 못했습니다.", "확인 번호: $operation.")
}
