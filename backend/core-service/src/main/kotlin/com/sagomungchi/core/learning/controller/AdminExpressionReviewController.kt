package com.sagomungchi.core.learning.controller

import com.fasterxml.jackson.annotation.JsonAnySetter
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.web.invalidOperations
import com.sagomungchi.core._common.web.operationPage
import com.sagomungchi.core.learning.domain.ExpressionReviewLabel
import com.sagomungchi.core.learning.domain.ExpressionReviewPage
import com.sagomungchi.core.learning.domain.ExpressionReviewSource
import com.sagomungchi.core.learning.service.AdminExpressionReviewService
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.*
import java.util.UUID

/** 관리자 표현 검토 (FN-ADM-24, api-spec 2.8, #728). SERVICE_OPS(인증 필터 경로 기본값) */
@RestController
@RequestMapping("/api/v1/admin/expression-reviews")
class AdminExpressionReviewController(private val service: AdminExpressionReviewService) {
    @GetMapping
    fun list(@RequestParam(defaultValue = "false") labeled: Boolean, @RequestParam(required = false) source: String?,
             @RequestParam(defaultValue = "0") page: Int, @RequestParam(defaultValue = "20") size: Int): ExpressionReviewPage {
        operationPage(page, size)
        val filter = source?.let { value -> ExpressionReviewSource.entries.find { it.name == value } ?: invalidOperations() }
        return service.list(labeled, filter, page, size)
    }

    @PutMapping("/{reviewId}/label")
    fun label(@PathVariable reviewId: UUID, @RequestBody body: ExpressionReviewLabelRequest) = service.label(reviewId, body.toLabel())
}

/** `{label}`만 받는다(api-spec 2.8). enum으로 바로 받으면 Jackson이 순번 숫자도 받아 문자열로 받는다 */
data class ExpressionReviewLabelRequest(val label: String) {
    @JsonAnySetter fun unknown(name: String, value: Any?) { throw IllegalArgumentException("Unknown expression review field: $name") }
    fun toLabel(): ExpressionReviewLabel = ExpressionReviewLabel.entries.find { it.name == label }
        ?: throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 값을 확인해 주세요.")
}
