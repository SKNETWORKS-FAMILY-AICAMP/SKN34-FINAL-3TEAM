package com.sagomungchi.learning.answer.repository

import com.sagomungchi.learning.answer.domain.ExpressionReviewRow
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.Instant
import java.util.UUID

@Mapper
interface ExpressionReviewMapper {
    fun insertGrayZone(
        @Param("id") id: UUID,
        @Param("answerId") answerId: UUID,
        @Param("modelVersion") modelVersion: String,
        @Param("now") now: Instant,
    ): Int

    fun insertReported(@Param("id") id: UUID, @Param("answerId") answerId: UUID, @Param("now") now: Instant): Int

    fun upsertAutoLabel(
        @Param("id") id: UUID,
        @Param("answerId") answerId: UUID,
        @Param("label") label: String,
        @Param("now") now: Instant,
    ): Int

    fun findPage(
        @Param("labeled") labeled: Boolean,
        @Param("source") source: String?,
        @Param("offset") offset: Long,
        @Param("limit") limit: Int,
    ): List<ExpressionReviewRow>

    fun count(@Param("labeled") labeled: Boolean, @Param("source") source: String?): Long

    fun findById(id: UUID): ExpressionReviewRow?

    fun countLabeledSince(@Param("since") since: Instant?): Long

    fun latestLabeledSince(@Param("since") since: Instant?): Instant?

    fun findExport(@Param("since") since: Instant?, @Param("until") until: Instant): List<ExpressionReviewRow>

    fun deleteByStudent(studentId: UUID): Int

    fun updateLabel(
        @Param("id") id: UUID,
        @Param("label") label: String,
        @Param("labeledBy") labeledBy: UUID,
        @Param("now") now: Instant,
    ): Int
}
