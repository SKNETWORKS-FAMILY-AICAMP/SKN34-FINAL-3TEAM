package com.sagomungchi.core.usage.domain

import java.math.BigDecimal

enum class CallType { JUDGMENT, FOLLOWUP, ANALYSIS, REPORT_NARRATIVE, MISSION_DRAFT, THEME_DRAFT, THEME_IMAGE, REPORT_EXPLANATION, M2, M1 }

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

/** 월 예산 경보용 누적: 단가가 있는 호출만 합산하고 미산정 호출 수는 따로 센다 (FN-ADM-19, P13) */
data class MonthToDateCost(val pricedUsd: BigDecimal, val unpricedCalls: Long)
