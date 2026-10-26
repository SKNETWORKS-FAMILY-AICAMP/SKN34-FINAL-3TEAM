package com.sagomungchi.core.usage.repository

import org.apache.ibatis.annotations.Mapper
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
    val success: Boolean,
    val errorCode: String?,
    val occurredAt: OffsetDateTime,
)

@Mapper
interface LlmUsageRepository {
    fun insertIfAbsent(usage: LlmUsage): Int
}
