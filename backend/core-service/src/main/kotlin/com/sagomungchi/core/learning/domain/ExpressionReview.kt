package com.sagomungchi.core.learning.domain

import java.util.UUID

/** 표현 검토 대기 출처 (api-spec 4.1.5) */
enum class ExpressionReviewSource { GRAY_ZONE, COMMUNITY_REPORT }

/** 운영자 라벨 (api-spec 4.1.5) */
enum class ExpressionReviewLabel { OFFENSIVE, CLEAN, SKIP }

/**
 * 관리자 표현 검토 항목(api-spec 2.8·4.1.5 공개 칸 그대로). 학생 이름·ID·답변 ID는 담을 칸이 없다.
 * 시각은 client가 date-time으로 읽히는 것을 확인한 learning 문자열 그대로다(#907).
 */
data class ExpressionReview(
    val id: UUID,
    val source: ExpressionReviewSource,
    val text: String,
    val modelVersion: String?,
    val label: ExpressionReviewLabel?,
    val labeledAt: String?,
    val createdAt: String,
)

data class ExpressionReviewPage(val items: List<ExpressionReview>, val page: Long, val size: Long, val totalElements: Long)
