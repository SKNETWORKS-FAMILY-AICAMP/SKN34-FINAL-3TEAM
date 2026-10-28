package com.sagomungchi.core.usage.domain

import java.math.BigDecimal

enum class CallType { JUDGMENT, FOLLOWUP, ANALYSIS, REPORT_NARRATIVE, M2, M1 }

data class UsageSummary(
    val callType: String,
    val calls: Long,
    val failures: Long,
    val latencyMs: BigDecimal,
    val inputTokens: Long?,
    val outputTokens: Long?,
    val costUsd: BigDecimal?,
    val unpricedCalls: Long,
)
