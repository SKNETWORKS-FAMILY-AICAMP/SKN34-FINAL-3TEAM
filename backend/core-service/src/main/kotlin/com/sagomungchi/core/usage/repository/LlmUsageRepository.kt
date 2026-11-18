package com.sagomungchi.core.usage.repository

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import com.sagomungchi.core.usage.domain.MonthToDateCost
import com.sagomungchi.core.usage.domain.UsageSummary
import java.math.BigDecimal
import java.time.OffsetDateTime
import java.util.UUID

/** 학생 ID·답변 원문 없음 (NFR-PRF-02) */
data class LlmUsage(
    val id: UUID,
    val eventId: UUID,
    val service: String,
    val callType: String,
    val model: String,
    val promptVersion: String?,
    val inputTokens: Int?,
    val outputTokens: Int?,
    val latencyMs: Int,
    val costUsd: BigDecimal?,
    /** 단가 없이 서비스 밖에서 청구되는 호출 (#764). costUsd는 null이고 미산정으로 세지 않는다 */
    val billedExternally: Boolean,
    val success: Boolean,
    val errorCode: String?,
    val occurredAt: OffsetDateTime,
)

@Mapper
interface LlmUsageRepository {
    fun insertIfAbsent(usage: LlmUsage): Int
    fun summarize(@Param("from") from: OffsetDateTime, @Param("until") until: OffsetDateTime,
                  @Param("callType") callType: String?): List<UsageSummary>
    fun monthToDate(@Param("from") from: OffsetDateTime, @Param("until") until: OffsetDateTime): MonthToDateCost
}
