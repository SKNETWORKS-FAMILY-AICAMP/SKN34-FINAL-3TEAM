package com.sagomungchi.learning.answer.domain

import java.time.Instant
import java.util.UUID

/** 표현 검토 대기 출처 (ERD 4.3.2) */
enum class ExpressionReviewSource { GRAY_ZONE, COMMUNITY_REPORT }

/** 표현 검토 대기 한 행과 그 답변 내용 (조회용). 학생·답변 ID는 담지 않음 */
data class ExpressionReviewRow(
    val id: UUID,
    val source: ExpressionReviewSource,
    val content: AnswerContent,
    val modelVersion: String?,
    val label: ExpressionReviewLabel?,
    val labeledAt: Instant?,
    val createdAt: Instant,
)

/** 관리자 검토 목록 항목 (api-spec 4.1.5). text는 학생이 쓴 칸을 줄바꿈으로 이은 글 */
data class ExpressionReviewItem(
    val id: UUID,
    val source: ExpressionReviewSource,
    val text: String,
    val modelVersion: String?,
    val label: ExpressionReviewLabel?,
    val labeledAt: Instant?,
    val createdAt: Instant,
) {
    companion object {
        fun of(row: ExpressionReviewRow) = ExpressionReviewItem(
            row.id, row.source, row.content.writtenTexts().joinToString("\n"), row.modelVersion, row.label, row.labeledAt, row.createdAt,
        )
    }
}

/** 재학습 새 라벨 수 (api-spec 4.1.5). latestLabeledAt은 센 행 중 가장 늦은 라벨 시각, 없으면 null */
data class ExpressionReviewLabelCount(val count: Long, val latestLabeledAt: Instant?)

/** 재학습 학습 데이터 한 줄: 글과 라벨만, 학생·답변 ID·시각 없음 (api-spec 4.1.5) */
data class ExpressionReviewExportItem(val text: String, val label: ExpressionReviewLabel) {
    companion object {
        /** api-spec 4.3.4와 같은 앞 1,500자. scoring(Python len)과 같게 코드포인트로 셈 */
        const val MAX_CHARS = 1500

        fun of(row: ExpressionReviewRow): ExpressionReviewExportItem {
            val text = row.content.writtenTexts().joinToString("\n")
            val cut = if (text.codePointCount(0, text.length) <= MAX_CHARS) text else text.substring(0, text.offsetByCodePoints(0, MAX_CHARS))
            return ExpressionReviewExportItem(cut, checkNotNull(row.label))
        }
    }
}

data class ExpressionReviewExport(val items: List<ExpressionReviewExportItem>)

data class ExpressionReviewPage(
    val items: List<ExpressionReviewItem>,
    val page: Int,
    val size: Int,
    val totalElements: Long,
)
