package com.sagomungchi.core.usage.domain

import java.time.OffsetDateTime

/** contracts/events/llm.usage.recorded.v1.schema.json */
data class LlmUsageRecorded(
    val service: String,
    val callType: String,
    val model: String,
    val promptVersion: String?,
    val inputTokens: Int?,
    val outputTokens: Int?,
    val latencyMs: Int,
    val success: Boolean,
    val errorCode: String?,
    val occurredAt: OffsetDateTime,
)
