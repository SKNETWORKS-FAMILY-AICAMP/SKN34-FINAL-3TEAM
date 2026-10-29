package com.sagomungchi.learning.judgment.repository

import com.sagomungchi.learning.judgment.domain.CorrectionTarget
import com.sagomungchi.learning.judgment.domain.JudgmentCorrection
import org.apache.ibatis.annotations.Mapper
import java.util.UUID

@Mapper
interface CorrectionMapper {
    fun lockTarget(judgmentId: UUID): CorrectionTarget?
    fun findByIdempotencyKey(key: UUID): JudgmentCorrection?
    fun existsByReportId(reportId: UUID): Boolean
    fun insert(correction: JudgmentCorrection): Int
}
