package com.sagomungchi.core.learning.controller

import com.sagomungchi.core._common.web.invalidOperations
import com.sagomungchi.core._common.web.operationPage
import com.sagomungchi.core.learning.service.AdminExpressionReviewService
import org.springframework.web.bind.annotation.*
import java.util.UUID

/** 관리자 표현 검토 (FN-ADM-24, api-spec 2.8, #728). SERVICE_OPS(인증 필터 경로 기본값) */
@RestController
@RequestMapping("/api/v1/admin/expression-reviews")
class AdminExpressionReviewController(private val service: AdminExpressionReviewService) {
    @GetMapping
    fun list(@RequestParam(defaultValue = "false") labeled: Boolean, @RequestParam(required = false) source: String?,
             @RequestParam(defaultValue = "0") page: Int, @RequestParam(defaultValue = "20") size: Int): Map<String, Any?> {
        operationPage(page, size)
        if (source != null && source !in setOf("GRAY_ZONE", "COMMUNITY_REPORT")) invalidOperations()
        return service.list(labeled, source, page, size)
    }

    @PutMapping("/{reviewId}/label")
    fun label(@PathVariable reviewId: UUID, @RequestBody body: ByteArray) = service.label(reviewId, body)
}
