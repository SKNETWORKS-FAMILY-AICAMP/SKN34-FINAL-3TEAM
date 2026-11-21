package com.sagomungchi.learning.answer.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.ExpressionReviewExport
import com.sagomungchi.learning.answer.domain.ExpressionReviewLabelCount
import com.sagomungchi.learning.answer.service.ExpressionReviewService
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import java.time.Instant
import java.time.OffsetDateTime
import java.time.format.DateTimeParseException

/**
 * 표현 분류 재학습 작업 내부 API (ops 토큰, SYSTEM, api-spec 4.1.5, #727). core 프록시 없음.
 * 응답에 학생·답변 ID·시각이 없는 글·라벨만 (NFR-SEC-05)
 */
@RestController
@RequestMapping("/internal/expression-reviews")
class ExpressionReviewExportController(private val service: ExpressionReviewService) {
    @GetMapping("/label-count")
    fun labelCount(@RequestParam(required = false) since: String?): ExpressionReviewLabelCount {
        requireSystem()
        return service.labelCount(since?.let { instant("since", it) })
    }

    @GetMapping("/export")
    fun export(@RequestParam(required = false) since: String?, @RequestParam(required = false) until: String?): ExpressionReviewExport {
        requireSystem()
        val end = instant("until", until ?: invalid("until은 필수"))
        if (end.isAfter(Instant.now())) invalid("until은 지금 이전이어야 함")
        val start = since?.let { instant("since", it) }
        if (start != null && start.isAfter(end)) invalid("since는 until 이전이어야 함")
        return service.export(start, end)
    }

    private fun requireSystem() {
        if (UserContextHolder.current().role != SYSTEM_ROLE) {
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "재학습 데이터는 SYSTEM 역할만 허용합니다.")
        }
    }

    /** ISO-8601 시각(오프셋 포함, 예: 2026-11-20T03:00:00Z) */
    private fun instant(name: String, value: String): Instant =
        try {
            OffsetDateTime.parse(value).toInstant()
        } catch (error: DateTimeParseException) {
            invalid("$name 은 ISO-8601 시각(오프셋 포함)")
        }

    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", detail)

    companion object {
        private const val SYSTEM_ROLE = "SYSTEM"
    }
}
